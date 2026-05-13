import os
import subprocess
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QLabel, QAbstractItemView, QMenu,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QMessageBox,
    QCheckBox, QPushButton,
)
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QColor

from ..models import BookEntry, AudioInfo

STATUS_COLOR = {"done": "#57cc7a", "pending": "#555", "converting": "#e8a020", "error": "#c94040"}

COL_WIDTHS_KEY    = "library_col_widths"
HIDE_COMPLETE_KEY = "library_hide_complete"
EXTRA_SHOWN_KEY   = "library_shown_extra_cols"

EXTRA_COLS   = ["Série", "Volume", "Narrateur", "Année", "Langue", "Éditeur"]
EXTRA_FIELDS = ["series", "volume", "narrator", "year", "language", "publisher"]
N_EXTRA      = len(EXTRA_COLS)

COL_CHECK   = 0
COL_TITLE   = 1
COL_AUTHOR  = 2
# 3 .. 2+N_EXTRA  → colonnes extra
COL_SOURCE  = 3 + N_EXTRA   # Qualité source (meilleure dispo + sélecteur)
COL_STATUS  = 4 + N_EXTRA   # État
COL_M4B_OUT = 5 + N_EXTRA   # Sortie M4B
COL_MP3_OUT = 6 + N_EXTRA   # Sortie MP3
TOTAL_COLS  = 7 + N_EXTRA


def _quality_cell(src: Optional[AudioInfo]) -> str:
    if src is None:
        return "—"
    if src.bitrate_kbps == 0:
        return src.codec.upper() if src.codec and src.codec != "?" else "?"
    return f"{src.codec.upper()} {src.bitrate_kbps}k"


def _combined_status(book: BookEntry):
    if book.status == "converting":
        return "⟳", STATUS_COLOR["converting"]
    if book.status == "error":
        return "✗", STATUS_COLOR["error"]
    if book.output_m4b_path and os.path.exists(book.output_m4b_path):
        return "✓", STATUS_COLOR["done"]
    return "○", STATUS_COLOR["pending"]


def _make_item(text: str, center: bool = False,
               color: Optional[str] = None, book_id: Optional[str] = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    if center:
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
    if color:
        item.setForeground(QColor(color))
    if book_id is not None:
        item.setData(Qt.ItemDataRole.UserRole, book_id)
    return item


class LibraryPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._books: List[BookEntry]          = []
        self._filtered_books: List[BookEntry] = []
        self._id_to_book: dict                = {}

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._persist_col_widths)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ────────────────────────────────────────────────────
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(8)

        bl.addWidget(QLabel("🔍"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher…")
        self._search.setMaximumWidth(220)
        self._search.textChanged.connect(self._refresh)
        bl.addWidget(self._search)

        bl.addWidget(QLabel("Trier :"))
        self._sort_cb = QComboBox()
        self._sort_cb.addItems(["Titre", "Auteur"])
        self._sort_cb.setMaximumWidth(120)
        self._sort_cb.currentTextChanged.connect(self._refresh)
        bl.addWidget(self._sort_cb)

        self._hide_complete_cb = QCheckBox("Cacher livres complets")
        self._hide_complete_cb.setToolTip(
            "Masque les livres dont les méta requises sont renseignées\n"
            "(ou marqués « ignorer la vérif »). Configurable dans Paramètres › Options.")
        saved_hide = bool(self.app.config_manager.app_config.ui_prefs.get(
            HIDE_COMPLETE_KEY, False))
        self._hide_complete_cb.setChecked(saved_hide)
        self._hide_complete_cb.toggled.connect(self._on_hide_complete_toggled)
        bl.addWidget(self._hide_complete_cb)

        _chk_style = ("QPushButton { background: transparent; color: #aaa; border: 1px solid #444;"
                      " padding: 2px 8px; font-size: 8pt; }"
                      "QPushButton:hover { background: rgba(255,255,255,0.06); color: #f3f3f3; }")
        check_all_btn = QPushButton("☑ Tout")
        check_all_btn.setToolTip("Cocher tous les livres visibles")
        check_all_btn.setStyleSheet(_chk_style)
        check_all_btn.clicked.connect(self._check_all)
        bl.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("☐ Tout")
        uncheck_all_btn.setToolTip("Décocher tous les livres")
        uncheck_all_btn.setStyleSheet(_chk_style)
        uncheck_all_btn.clicked.connect(self._uncheck_all)
        bl.addWidget(uncheck_all_btn)

        bl.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        bl.addWidget(self._count_lbl)
        layout.addWidget(bar)

        # ── Table ──────────────────────────────────────────────────────
        self._populating = False
        self._table = QTableWidget(1, TOTAL_COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_menu)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        hh = self._table.horizontalHeader()
        hh.sectionResized.connect(lambda: self._save_timer.start())
        hh.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hh.customContextMenuRequested.connect(self._show_header_menu)

        self._rebuild_columns()

        # Placeholder initial
        self._table.setItem(0, COL_TITLE, _make_item(
            "Cliquez sur ⟳ Scanner pour charger la bibliothèque", color="#555"))
        self._table.item(0, COL_TITLE).setFlags(Qt.ItemFlag.ItemIsEnabled)
        layout.addWidget(self._table, 1)

    # ── Public API ─────────────────────────────────────────────────────

    def populate(self, books: List[BookEntry]):
        self._books      = books
        self._id_to_book = {b.id: b for b in books}
        self._refresh()

    def get_filtered_books(self) -> List[BookEntry]:
        return self._filtered_books

    def update_status(self, book_id: str, status: str):
        book = self._id_to_book.get(book_id)
        if book:
            book.status = status
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, COL_TITLE)
            if cell and cell.data(Qt.ItemDataRole.UserRole) == book_id:
                icon, color = _combined_status(book) if book else ("○", "#555")
                self._populating = True
                self._table.setItem(row, COL_STATUS, _make_item(icon, True, color))
                self._populating = False
                break

    def refresh_queue_checkboxes(self):
        pass

    # ── Internal ───────────────────────────────────────────────────────

    def _rebuild_columns(self):
        headers = (["▶", "Titre", "Auteur"] + EXTRA_COLS
                   + ["Source", "État", "Sortie M4B", "Sortie MP3"])
        self._table.setColumnCount(TOTAL_COLS)
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeaderItem(COL_CHECK).setToolTip(
            "Cocher pour sélectionner des livres — actions via clic droit")
        self._table.horizontalHeaderItem(COL_TITLE).setToolTip(
            "Clic droit sur l'en-tête pour afficher/masquer les colonnes supplémentaires")
        self._table.horizontalHeaderItem(COL_SOURCE).setToolTip(
            "Meilleure source disponible — clic pour choisir si plusieurs sources")

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(COL_CHECK,  QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_CHECK, 32)
        hh.setSectionResizeMode(COL_TITLE,  QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_TITLE, 300)
        hh.setSectionResizeMode(COL_AUTHOR, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_AUTHOR, 160)
        for i in range(N_EXTRA):
            hh.setSectionResizeMode(3 + i, QHeaderView.ResizeMode.Interactive)
            self._table.setColumnWidth(3 + i, 130)
        hh.setSectionResizeMode(COL_SOURCE,  QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_SOURCE, 140)
        hh.setSectionResizeMode(COL_STATUS,  QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_STATUS, 36)
        hh.setSectionResizeMode(COL_M4B_OUT, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_M4B_OUT, 110)
        hh.setSectionResizeMode(COL_MP3_OUT, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_MP3_OUT, 110)

        saved = self.app.config_manager.get_col_widths(COL_WIDTHS_KEY)
        if len(saved) == TOTAL_COLS:
            for col in range(TOTAL_COLS - 1):
                if saved[col] > 20:
                    self._table.setColumnWidth(col, saved[col])

        shown = set(self.app.config_manager.app_config.ui_prefs.get(EXTRA_SHOWN_KEY, []))
        for i, name in enumerate(EXTRA_COLS):
            hh.setSectionHidden(3 + i, name not in shown)

    def _on_hide_complete_toggled(self, checked: bool):
        self.app.config_manager.app_config.ui_prefs[HIDE_COMPLETE_KEY] = checked
        self.app.config_manager.save_config()
        self._refresh()

    def _show_header_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Colonnes supplémentaires :").setEnabled(False)
        menu.addSeparator()
        shown = set(self.app.config_manager.app_config.ui_prefs.get(EXTRA_SHOWN_KEY, []))
        for i, name in enumerate(EXTRA_COLS):
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name in shown)
            action.triggered.connect(
                lambda checked, n=name, idx=i: self._toggle_extra_col(n, idx, checked))
        menu.exec(self._table.horizontalHeader().mapToGlobal(pos))

    def _toggle_extra_col(self, name: str, extra_idx: int, visible: bool):
        shown = set(self.app.config_manager.app_config.ui_prefs.get(EXTRA_SHOWN_KEY, []))
        if visible:
            shown.add(name)
        else:
            shown.discard(name)
        self.app.config_manager.app_config.ui_prefs[EXTRA_SHOWN_KEY] = list(shown)
        self.app.config_manager.save_config()
        self._table.horizontalHeader().setSectionHidden(3 + extra_idx, not visible)

    def _persist_col_widths(self):
        hh     = self._table.horizontalHeader()
        widths = [hh.sectionSize(i) for i in range(self._table.columnCount())]
        self.app.config_manager.set_col_widths(COL_WIDTHS_KEY, widths)
        self.app.config_manager.save_config()

    def _refresh(self):
        query = self._search.text().lower().strip()
        hide_complete = self._hide_complete_cb.isChecked()
        required = self.app.config_manager.app_config.metadata_required_fields

        def _keep(b):
            if query and query not in b.display_title.lower() \
                    and query not in b.display_author.lower():
                return False
            if hide_complete and b.is_metadata_complete(required):
                return False
            return True

        books = [b for b in self._books if _keep(b)]
        if self._sort_cb.currentText() == "Auteur":
            books.sort(key=lambda b: b.display_author.lower())
        else:
            books.sort(key=lambda b: b.display_title.lower())
        self._filtered_books = books

        self._table.setSortingEnabled(False)
        self._populating = True
        try:
            self._table.setRowCount(len(books))

            prev_checked = set()
            for r in range(self._table.rowCount()):
                cb = self._table.item(r, COL_CHECK)
                ti = self._table.item(r, COL_TITLE)
                if cb and ti and cb.checkState() == Qt.CheckState.Checked:
                    bid = ti.data(Qt.ItemDataRole.UserRole)
                    if bid:
                        prev_checked.add(bid)

            for row, book in enumerate(books):
                icon, color = _combined_status(book)

                cb_item = QTableWidgetItem("")
                cb_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable)
                cb_item.setCheckState(
                    Qt.CheckState.Checked if book.id in prev_checked else Qt.CheckState.Unchecked)
                cb_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, COL_CHECK, cb_item)
                self._table.setItem(row, COL_TITLE,  _make_item(book.display_title, book_id=book.id))
                self._table.setItem(row, COL_AUTHOR, _make_item(book.display_author))

                for i, field in enumerate(EXTRA_FIELDS):
                    val = getattr(book.config, field, "") or ""
                    self._table.setItem(row, 3 + i, _make_item(val))

                # Source : meilleure source + indicateur de sélection possible
                src = book.selected_source
                quality = _quality_cell(src)
                if len(book.sources) > 1:
                    quality += " ▾"
                src_color = None if src and src.bitrate_kbps > 0 else "#888"
                self._table.setItem(row, COL_SOURCE,
                    _make_item(quality, True, src_color))

                self._table.setItem(row, COL_STATUS,
                    _make_item(icon, True, color))

                # Sortie M4B
                self._table.setItem(row, COL_M4B_OUT,
                    _make_item(_quality_cell(book.output_m4b_info), True,
                               None if book.output_m4b_info else "#444"))

                # Sortie MP3
                self._table.setItem(row, COL_MP3_OUT,
                    _make_item(_quality_cell(book.output_mp3_info), True,
                               None if book.output_mp3_info else "#444"))

        finally:
            self._populating = False

        self._table.setSortingEnabled(True)
        n_visible = len(books)
        self._count_lbl.setText(f"{n_visible} livre{'s' if n_visible != 1 else ''}")

    # ── Sélecteur de source ────────────────────────────────────────────

    def _on_cell_clicked(self, row: int, col: int):
        if col != COL_SOURCE:
            return
        title_item = self._table.item(row, COL_TITLE)
        if not title_item:
            return
        book = self._id_to_book.get(title_item.data(Qt.ItemDataRole.UserRole))
        if not book or len(book.sources) <= 1:
            return

        menu = QMenu(self)
        current_path = book.config.selected_source_label
        best = book.selected_source
        for src in book.sources:
            basename = os.path.basename(src.path) if src.path else src.folder_label
            label = f"{src.folder_label}  ·  {basename}  —  {_quality_cell(src)}"
            action = menu.addAction(label)
            action.setCheckable(True)
            is_selected = (src.path == current_path) or (not current_path and src is best)
            action.setChecked(is_selected)
            action.triggered.connect(
                lambda checked=False, p=src.path, b=book:
                    self._select_source(b, p))

        cell_item = self._table.item(row, col)
        if cell_item:
            rect = self._table.visualItemRect(cell_item)
            global_pos = self._table.viewport().mapToGlobal(rect.bottomLeft())
            menu.exec(global_pos)

    def _select_source(self, book: BookEntry, path: str):
        book.config.selected_source_label = path
        self.app.config_manager.save_book(book)
        self._refresh()

    # ── Navigation ─────────────────────────────────────────────────────

    def _on_double_click(self):
        book = self._selected_book()
        if book:
            self.app.on_book_selected(book)

    def _selected_books(self) -> List[BookEntry]:
        rows = {i.row() for i in self._table.selectedItems()}
        books = []
        for row in sorted(rows):
            title_item = self._table.item(row, COL_TITLE)
            if title_item:
                book = self._id_to_book.get(title_item.data(Qt.ItemDataRole.UserRole))
                if book:
                    books.append(book)
        return books

    def _checked_books(self) -> List[BookEntry]:
        books = []
        for row in range(self._table.rowCount()):
            cb = self._table.item(row, COL_CHECK)
            title_item = self._table.item(row, COL_TITLE)
            if (cb and title_item
                    and cb.checkState() == Qt.CheckState.Checked):
                book = self._id_to_book.get(title_item.data(Qt.ItemDataRole.UserRole))
                if book:
                    books.append(book)
        return books

    def _check_all(self):
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb and cb.checkState() == Qt.CheckState.Unchecked:
                    cb.setCheckState(Qt.CheckState.Checked)
        finally:
            self._populating = False

    def _uncheck_all(self):
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb and cb.checkState() == Qt.CheckState.Checked:
                    cb.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._populating = False

    def _on_item_changed(self, item: QTableWidgetItem):
        pass

    def _selected_book(self) -> Optional[BookEntry]:
        books = self._selected_books()
        return books[0] if len(books) == 1 else None

    # ── Édition rapide ─────────────────────────────────────────────────

    def _quick_edit(self, book: BookEntry):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Modifier — {book.display_title[:50]}")
        dlg.resize(460, 200)
        vl = QVBoxLayout(dlg)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        fields = {}
        for key, label, default in [
            ("title",    "Titre",     book.config.title    or book.detected_title),
            ("author",   "Auteur",    book.config.author   or book.detected_author),
            ("series",   "Série",     book.config.series),
            ("volume",   "Volume",    book.config.volume),
            ("narrator", "Narrateur", book.config.narrator),
        ]:
            le = QLineEdit(default)
            fields[key] = le
            form.addRow(f"{label} :", le)

        vl.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            for key, le in fields.items():
                setattr(book.config, key, le.text().strip())
            self.app.config_manager.save_book(book)
            self._refresh()

    # ── Menu contextuel ────────────────────────────────────────────────

    def _show_menu(self, pos: QPoint):
        checked = self._checked_books()
        books = checked if checked else self._selected_books()
        if not books:
            return
        menu = QMenu(self)
        from_checks = bool(checked)

        if len(books) > 1:
            n = len(books)
            if from_checks:
                menu.addAction(f"({n} livres cochés)").setEnabled(False)
                menu.addSeparator()
            menu.addAction(f"▶  Ajouter {n} livres à la file").triggered.connect(
                lambda: [self.app.add_to_queue(b) for b in books])
            menu.addAction(f"⚡  Convertir {n} livres maintenant").triggered.connect(
                lambda: [self.app.convert_now(b) for b in books])
            menu.addAction(f"🎵  Exporter {n} livres en MP3").triggered.connect(
                lambda: [self.app.add_mp3_export(b) for b in books])
            menu.addSeparator()
            menu.addAction(f"Marquer {n} livres comme fait ✓").triggered.connect(
                lambda: [self.update_status(b.id, "done") for b in books])
            all_ignored = all(b.config.ignore_metadata_check for b in books)
            label_meta = (f"☐  Annuler « ignorer méta » sur {n} livres"
                          if all_ignored
                          else f"☑  Marquer méta OK sur {n} livres")
            menu.addAction(label_meta).triggered.connect(
                lambda checked=False, target=not all_ignored:
                self._toggle_ignore_meta(books, target))
            menu.addSeparator()
            menu.addAction(f"🗑  Supprimer {n} livres de la bibliothèque…"
                           ).triggered.connect(
                lambda: self._delete_books(books))
            if from_checks:
                menu.addSeparator()
                menu.addAction("☐  Tout décocher").triggered.connect(self._uncheck_all)
        else:
            book = books[0]
            menu.addAction("✏  Modifier titre / auteur…").triggered.connect(
                lambda: self._quick_edit(book))
            menu.addSeparator()
            menu.addAction("✏  Ouvrir dans l'éditeur complet").triggered.connect(
                lambda: self.app.on_book_selected(book))
            menu.addAction("▶  Ajouter à la file").triggered.connect(
                lambda: self.app.add_to_queue(book))
            menu.addAction("⚡  Convertir maintenant").triggered.connect(
                lambda: self.app.convert_now(book))
            menu.addAction("🎵  Exporter en MP3").triggered.connect(
                lambda: self.app.add_mp3_export(book))
            menu.addSeparator()
            label_meta = ("☐  Méta : revérifier (annuler « ignorer »)"
                          if book.config.ignore_metadata_check
                          else "☑  Méta OK (ignorer la vérif)")
            menu.addAction(label_meta).triggered.connect(
                lambda checked=False, b=book: self._toggle_ignore_meta(
                    [b], not b.config.ignore_metadata_check))
            menu.addSeparator()

            sources_with_path = [s for s in book.sources if s.path]
            if len(sources_with_path) == 1:
                src = sources_with_path[0]
                menu.addAction(
                    f"📂  Ouvrir dans l'Explorateur ({src.folder_label})"
                ).triggered.connect(lambda checked=False, p=src.path: _open_in_explorer(p))
            elif len(sources_with_path) > 1:
                sub = menu.addMenu("📂  Ouvrir dans l'Explorateur")
                for src in sources_with_path:
                    sub.addAction(src.folder_label).triggered.connect(
                        lambda checked=False, p=src.path: _open_in_explorer(p))

            if book.output_m4b_path and os.path.exists(book.output_m4b_path):
                menu.addAction("📂  Ouvrir M4B de sortie").triggered.connect(
                    lambda checked=False, p=book.output_m4b_path: _open_in_explorer(p))

            if book.output_mp3_dir and os.path.isdir(book.output_mp3_dir):
                menu.addAction("📂  Ouvrir dossier MP3").triggered.connect(
                    lambda checked=False, p=book.output_mp3_dir: _open_in_explorer(p))

            menu.addSeparator()
            menu.addAction("Marquer comme fait ✓").triggered.connect(
                lambda: self.update_status(book.id, "done"))
            menu.addSeparator()
            menu.addAction("⛓  Fusionner avec…").triggered.connect(
                lambda: self._merge_dialog(book))
            if book.merged_from:
                menu.addAction("✂  Défusionner…").triggered.connect(
                    lambda: self._unmerge_dialog(book))
            menu.addSeparator()
            menu.addAction("🗑  Supprimer de la bibliothèque…").triggered.connect(
                lambda: self._delete_book(book))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ── Toggle « ignorer la vérif des méta » ───────────────────────────

    def _toggle_ignore_meta(self, books: List[BookEntry], target: bool):
        for b in books:
            b.config.ignore_metadata_check = target
            self.app.config_manager.save_book(b)
        self._refresh()

    # ── Fusion manuelle ────────────────────────────────────────────────

    def _merge_dialog(self, source_book: BookEntry):
        from difflib import SequenceMatcher

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Fusionner « {source_book.display_title[:40]} » avec…")
        dlg.resize(540, 380)
        vl = QVBoxLayout(dlg)

        lbl = QLabel(
            f"Fusionner <b>{source_book.display_title}</b> dans le livre cible<br>"
            "<small style='color:#888'>Les sources seront transférées ; l'entrée source sera supprimée.</small>"
        )
        lbl.setTextFormat(Qt.TextFormat.RichText)
        vl.addWidget(lbl)

        search_le = QLineEdit()
        search_le.setPlaceholderText("Rechercher…")
        vl.addWidget(search_le)

        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        vl.addWidget(lst, 1)

        src_title = source_book.display_title.lower()
        others = sorted(
            [b for b in self._books if b.id != source_book.id],
            key=lambda b: SequenceMatcher(None, src_title, b.display_title.lower()).ratio(),
            reverse=True,
        )

        def _populate(query: str = ""):
            lst.clear()
            for b in others:
                if query and query not in b.display_title.lower() \
                        and query not in b.display_author.lower():
                    continue
                sim = SequenceMatcher(None, src_title, b.display_title.lower()).ratio()
                item = QListWidgetItem(f"{b.display_title}  —  {b.display_author}")
                item.setData(Qt.ItemDataRole.UserRole, b.id)
                if sim > 0.55:
                    item.setForeground(QColor("#57cc7a"))
                lst.addItem(item)

        _populate()
        search_le.textChanged.connect(lambda q: _populate(q.lower().strip()))

        hint = QLabel("En vert : titres proches. Sélectionnez le livre cible puis OK.")
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        vl.addWidget(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            sel = lst.currentItem()
            if sel:
                target = self._id_to_book.get(sel.data(Qt.ItemDataRole.UserRole))
                if target:
                    self._merge_into(source_book, target)

    def _merge_into(self, source: BookEntry, target: BookEntry):
        from ..scanner import _book_snapshot

        existing_paths = {s.path for s in target.sources}
        added_paths = []
        for src in source.sources:
            if src.path not in existing_paths:
                target.sources.append(src)
                added_paths.append(src.path)

        target.merged_from.append({
            "id": source.id,
            "detected_title": source.detected_title,
            "detected_author": source.detected_author,
            "detected_series": source.detected_series,
            "config": source.config.to_dict(),
            "source_paths": added_paths,
        })

        self.app.config_manager.save_book(target)
        self.app.config_manager.delete_book(source.id)

        self._books = [b for b in self._books if b.id != source.id]
        self._id_to_book = {b.id: b for b in self._books}
        self.app.config_manager.save_last_scan(
            [_book_snapshot(b) for b in self._books])

        self._refresh()

    # ── Défusion ─────────────────────────────────────────────────────────

    def _unmerge_dialog(self, book: BookEntry):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Défusionner « {book.display_title[:40]} »")
        dlg.resize(480, 300)
        vl = QVBoxLayout(dlg)

        lbl = QLabel(
            "Sélectionnez le livre à extraire :<br>"
            "<small style='color:#888'>Il sera recréé comme entrée séparée avec ses sources d'origine.</small>"
        )
        lbl.setTextFormat(Qt.TextFormat.RichText)
        vl.addWidget(lbl)

        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        vl.addWidget(lst, 1)

        for snap in book.merged_from:
            title = snap.get("config", {}).get("title") or snap.get("detected_title", "?")
            author = snap.get("config", {}).get("author") or snap.get("detected_author", "")
            n_sources = len(snap.get("source_paths", []))
            label = f"{title}  —  {author}  [{n_sources} source(s)]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, snap)
            lst.addItem(item)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            sel = lst.currentItem()
            if sel:
                self._unmerge_from(book, sel.data(Qt.ItemDataRole.UserRole))

    def _unmerge_from(self, book: BookEntry, snap: dict):
        import uuid
        from ..models import BookConfig
        from ..scanner import _book_snapshot

        paths_to_extract = set(snap.get("source_paths", []))
        extracted = [s for s in book.sources if s.path in paths_to_extract]
        if not extracted:
            return

        book.sources = [s for s in book.sources if s.path not in paths_to_extract]
        book.merged_from = [m for m in book.merged_from if m.get("id") != snap.get("id")]

        new_book = BookEntry(
            id=snap.get("id") or str(uuid.uuid4()),
            detected_author=snap.get("detected_author", ""),
            detected_series=snap.get("detected_series", ""),
            detected_title=snap.get("detected_title", ""),
            sources=extracted,
            chapters=[],
            config=BookConfig.from_dict(snap.get("config", {})),
            status="pending",
        )

        self.app.config_manager.save_book(book)
        self.app.config_manager.save_book(new_book)

        self._books.append(new_book)
        self._id_to_book[new_book.id] = new_book
        self.app.config_manager.save_last_scan(
            [_book_snapshot(b) for b in self._books])

        self._refresh()

    # ── Suppression ──────────────────────────────────────────────────────

    def _delete_book(self, book: BookEntry):
        self._delete_books([book])

    def _delete_books(self, books: List[BookEntry]):
        from ..scanner import _book_snapshot
        n = len(books)
        if n == 0:
            return
        if n == 1:
            msg = (f"Supprimer <b>{books[0].display_title}</b> de la "
                   f"bibliothèque ?<br><br>")
        else:
            preview = "<br>".join(
                f"• {b.display_title}" for b in books[:8])
            extra = (f"<br>… et {n - 8} de plus" if n > 8 else "")
            msg = (f"Supprimer <b>{n} livres</b> de la bibliothèque ?<br><br>"
                   f"<small>{preview}{extra}</small><br><br>")
        reply = QMessageBox.question(
            self,
            "Supprimer de la bibliothèque",
            msg + "<small>Les fichiers audio ne sont pas supprimés.<br>"
                  "Les livres seront redétectés au prochain scan.</small>",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ids = {b.id for b in books}
        for bid in ids:
            self.app.config_manager.delete_book(bid)
        self._books = [b for b in self._books if b.id not in ids]
        self._id_to_book = {b.id: b for b in self._books}
        self.app.config_manager.save_last_scan(
            [_book_snapshot(b) for b in self._books])

        self._refresh()


def _open_in_explorer(path: str):
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif os.path.isdir(path):
        subprocess.Popen(["explorer", os.path.normpath(path)])
