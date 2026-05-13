import os
import json
import subprocess
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialogButtonBox, QProgressDialog, QApplication, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ..models import BookEntry

TAG_MAPPING = {
    "title":     ["title", "album"],
    "author":    ["artist", "album_artist"],
    "series":    ["grouping", "mvnm", "series"],
    "volume":    ["mvin", "series-part", "tracknumber"],
    "narrator":  ["performer", "composer"],
    "genre":     ["genre"],
    "year":      ["date", "year", "originalyear"],
    "language":  ["language"],
    "asin":      ["asin"],
    "publisher": ["publisher", "organization", "label"],
    # encoded_by est la signature personnelle — jamais importé depuis la source
}

FIELD_LABELS = {
    "title":     "Titre",
    "author":    "Auteur",
    "series":    "Série",
    "volume":    "Volume",
    "narrator":  "Narrateur",
    "genre":     "Genre",
    "year":      "Année",
    "language":  "Langue",
    "asin":      "ASIN",
    "publisher": "Éditeur",
}

COL_CURRENT  = "#2a3a2a"
COL_SELECTED = "#0055a0"
COL_HOVER    = "#2a3a50"
COL_EMPTY    = "#1a1a1a"


def _first_audio(folder: str) -> str:
    exts = {".mp3", ".m4b", ".m4a", ".aac", ".flac"}
    try:
        for fn in sorted(os.listdir(folder)):
            if os.path.splitext(fn)[1].lower() in exts:
                return os.path.join(folder, fn)
    except OSError:
        pass
    return ""


def _fetch_tags_for_source(path: str) -> dict:
    target = path if os.path.isfile(path) else _first_audio(path)
    if not target:
        return {}
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", target],
            capture_output=True, text=True, timeout=30, encoding="utf-8")
        if r.returncode != 0:
            return {}
        raw = {k.lower(): v for k, v in
               (json.loads(r.stdout).get("format", {}).get("tags") or {}).items()}
    except Exception:
        return {}

    result = {}
    for field, keys in TAG_MAPPING.items():
        for k in keys:
            val = raw.get(k, "").strip()
            if val:
                result[field] = val
                break
    return result


class TagImportDialog(QDialog):
    """
    Dialogue de comparaison des métadonnées.
    Affiche côte-à-côte la valeur courante et les tags de chaque source.
    L'utilisateur clique sur la cellule à utiliser pour chaque champ.
    """

    def __init__(self, parent, book: BookEntry, current_values: dict):
        super().__init__(parent)
        self.book           = book
        self.current_values = current_values
        self.result_values  = {}
        self._selected      = {}   # row → col index
        self._result_edits  = {}   # row → QLineEdit

        self.setWindowTitle("Importer les métadonnées — choisir par champ")
        self.resize(960, 460)

        # Récupérer les tags de chaque source (synchrone)
        self._source_tags = []
        progress = QProgressDialog("Lecture des tags…", None, 0,
                                   len(book.sources), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        for i, src in enumerate(book.sources):
            progress.setValue(i)
            QApplication.processEvents()
            self._source_tags.append(_fetch_tags_for_source(src.path))
        progress.setValue(len(book.sources))

        self._build_ui()
        self._init_selection()

    # ── Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        vl = QVBoxLayout(self)
        vl.setSpacing(8)

        hint = QLabel(
            "Cliquez sur la valeur à utiliser pour chaque champ.  "
            "Bleu = sélectionné · Vert foncé = valeur courante.")
        hint.setStyleSheet("color: #888; font-size: 8.5pt;")
        vl.addWidget(hint)

        sources = self.book.sources
        # Colonnes: Champ | Valeur actuelle | Source1 … | Résultat
        col_headers = ["Champ", "Valeur actuelle"] + \
                      [s.folder_label for s in sources] + ["Résultat"]
        n_cols   = len(col_headers)
        res_col  = n_cols - 1
        n_rows   = len(FIELD_LABELS)

        self._table = QTableWidget(n_rows, n_cols)
        self._table.setHorizontalHeaderLabels(col_headers)
        self._table.verticalHeader().hide()
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setAlternatingRowColors(False)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 100)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(1, 200)
        for c in range(2, res_col):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            self._table.setColumnWidth(c, 160)
        hh.setSectionResizeMode(res_col, QHeaderView.ResizeMode.Stretch)

        for row, (field, label) in enumerate(FIELD_LABELS.items()):
            # Colonne 0 : nom du champ
            it = QTableWidgetItem(label)
            it.setForeground(QColor("#aaa"))
            it.setFont(QFont("Segoe UI", 9))
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(row, 0, it)

            # Colonne 1 : valeur actuelle
            current = self.current_values.get(field, "")
            self._table.setItem(row, 1, self._make_item(current, row, 1))

            # Colonnes sources
            for col_offset, src_tags in enumerate(self._source_tags):
                col = 2 + col_offset
                val = src_tags.get(field, "")
                self._table.setItem(row, col, self._make_item(val, row, col))

            # Colonne Résultat : QLineEdit éditable
            le = QLineEdit(current)
            le.setStyleSheet("background: #1e2a1e; border: 1px solid #3a5a3a; padding: 1px 4px;")
            self._table.setCellWidget(row, res_col, le)
            self._result_edits[row] = le

        self._table.cellClicked.connect(self._on_cell_click)
        vl.addWidget(self._table, 1)

        # Boutons "Tout depuis source X"
        if len(self.book.sources) > 0:
            src_row = QHBoxLayout()
            src_row.addWidget(QLabel("Tout sélectionner depuis :"))
            for i, src in enumerate(self.book.sources):
                col = 2 + i
                btn = QPushButton(src.folder_label)
                btn.setMaximumWidth(160)
                btn.clicked.connect(lambda checked=False, c=col: self._select_all_from(c))
                src_row.addWidget(btn)
            src_row.addStretch()
            vl.addLayout(src_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Appliquer la sélection")
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        vl.addWidget(btns)

    def _make_item(self, text: str, row: int, col: int) -> QTableWidgetItem:
        it = QTableWidgetItem(text if text else "—")
        it.setData(Qt.ItemDataRole.UserRole, (row, col))
        if col == 0:
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        else:
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if not text:
            it.setForeground(QColor("#444"))
        return it

    # ── Sélection ──────────────────────────────────────────────────────

    def _init_selection(self):
        """Pré-sélectionne la valeur courante pour chaque champ."""
        for row in range(len(FIELD_LABELS)):
            self._select_cell(row, 1)

    def _on_cell_click(self, row: int, col: int):
        res_col = self._table.columnCount() - 1
        if col == 0 or col == res_col:
            return
        it = self._table.item(row, col)
        if it and it.text() and it.text() != "—":
            self._select_cell(row, col)

    def _select_cell(self, row: int, col: int):
        n_cols  = self._table.columnCount()
        res_col = n_cols - 1
        self._selected[row] = col

        # Rafraîchir les couleurs de la ligne (hors colonne Résultat)
        for c in range(1, res_col):
            it = self._table.item(row, c)
            if it is None:
                continue
            has_val = it.text() and it.text() != "—"
            if c == col:
                it.setBackground(QColor(COL_SELECTED))
                it.setForeground(QColor("#ffffff"))
            elif c == 1:
                it.setBackground(QColor(COL_CURRENT if has_val else COL_EMPTY))
                it.setForeground(QColor("#ccc" if has_val else "#444"))
            else:
                it.setBackground(QColor(COL_EMPTY))
                it.setForeground(QColor("#ccc" if has_val else "#444"))

        # Synchronise le QLineEdit Résultat avec la valeur sélectionnée
        it_sel = self._table.item(row, col)
        if it_sel:
            val = it_sel.text() if it_sel.text() != "—" else ""
            le  = self._result_edits.get(row)
            if le is not None:
                le.setText(val)

    def _select_all_from(self, col: int):
        res_col = self._table.columnCount() - 1
        if col == res_col:
            return
        for row in range(len(FIELD_LABELS)):
            it = self._table.item(row, col)
            if it and it.text() and it.text() != "—":
                self._select_cell(row, col)

    # ── Résultat ───────────────────────────────────────────────────────

    def _apply(self):
        fields = list(FIELD_LABELS.keys())
        for row, field in enumerate(fields):
            le  = self._result_edits.get(row)
            val = le.text().strip() if le is not None else ""
            self.result_values[field] = val
        self.accept()
