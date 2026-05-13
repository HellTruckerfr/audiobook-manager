import os
import re
import shutil
import subprocess
import threading
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QGroupBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor

from ..models import BookEntry


_LANG_MAP = {
    "FR": "FRENCH", "EN": "ENGLISH", "ES": "SPANISH",
    "DE": "GERMAN", "IT": "ITALIAN", "PT": "PORTUGUESE",
    "NL": "DUTCH", "JA": "JAPANESE", "RU": "RUSSIAN",
}

_TEMPLATE_HELP = (
    "Variables disponibles : "
    "{author} {title} {series} {volume} {year} {lang} "
    "{format} {codec} {bitrate} {group}\n"
    "Le template dossier accepte des / pour créer plusieurs niveaux "
    "(ex. {author}/{series}/{volume}/release). "
    "Les segments dont toutes les variables sont vides sont automatiquement supprimés.\n"
    "Les espaces sont remplacés par des points. {bitrate} et {codec} ne sont "
    "écrits que si la case correspondante est cochée."
)


def _dot(s: str) -> str:
    return re.sub(r'\.{2,}', '.', s.replace(" ", ".")).strip(".")


def _clean(s: str) -> str:
    """Supprime les caractères interdits dans les noms Windows."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip(" .")


def _vol_number(volume: str) -> int:
    m = re.search(r'\d+', volume)
    return int(m.group(0)) if m else 0


def _bitrate_label(book: BookEntry) -> str:
    """Retourne ex. '128kbps' depuis un BookConfig.bitrate '128k' ou un AudioInfo."""
    raw = (book.config.bitrate or "").lower().strip()
    if raw.endswith("kbps"):
        return raw
    if raw.endswith("k"):
        return raw[:-1] + "kbps"
    if raw.isdigit():
        return raw + "kbps"
    src = book.selected_source
    if src and src.bitrate_kbps:
        return f"{src.bitrate_kbps}kbps"
    return raw or "?"


def _codec_label(book: BookEntry) -> str:
    src = book.selected_source
    if src and src.codec:
        # M4B contient toujours de l'AAC ; on standardise.
        c = src.codec.lower()
        if c in ("aac", "alac", "mp3", "flac", "opus", "vorbis"):
            return c.upper()
        return c.upper()
    # Sortie M4B = AAC par convention
    return "AAC"


def _format_label(book: BookEntry) -> str:
    p = book.output_m4b_path or ""
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    return ext.upper() if ext else "M4B"


def _build_context(book: BookEntry, group: str,
                   include_codec: bool, include_bitrate: bool) -> Dict[str, str]:
    cfg = book.config
    lang = (cfg.language or "FR").upper()
    author_raw = cfg.author or book.detected_author or ""
    first_author = author_raw.split(",")[0].strip()
    return {
        "author":  _dot(_clean(first_author)),
        "title":   _dot(_clean(cfg.title  or book.detected_title)),
        "series":  _dot(_clean(cfg.series or book.detected_series)),
        "volume":  f"T{_vol_number(cfg.volume):02d}" if cfg.volume else "",
        "year":    cfg.year or "",
        "lang":    _LANG_MAP.get(lang, lang),
        "format":  _format_label(book),
        "codec":   _codec_label(book) if include_codec else "",
        "bitrate": _bitrate_label(book) if include_bitrate else "",
        "group":   group or "HellTrucker",
    }


def _render_segment(template: str, ctx: Dict[str, str]) -> str:
    """Rend un seul segment (sans /). Si toutes les variables {x} étaient vides,
    le résultat sera vide aussi → l'appelant peut le filtrer."""
    placeholders = re.findall(r'\{([a-z_]+)\}', template)
    has_var = bool(placeholders)
    any_filled = any(ctx.get(k, "") for k in placeholders)
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", v)
    out = re.sub(r'\.{2,}', '.', out)
    out = re.sub(r'\.-', '-', out)
    out = re.sub(r'-\.+', '-', out)
    out = out.strip(". -")
    if has_var and not any_filled:
        return ""
    return out


def _render_path_template(template: str, ctx: Dict[str, str]) -> str:
    """Rend un template multi-niveaux (peut contenir / ou \\). Les segments vides
    après rendu sont retirés. Renvoie un chemin relatif joint avec os.sep."""
    parts = re.split(r'[\\/]+', template.strip("/\\ "))
    rendered = [_render_segment(p, ctx) for p in parts]
    rendered = [r for r in rendered if r]
    return os.path.join(*rendered) if rendered else ""


class _CopyBridge(QObject):
    progress = pyqtSignal(int, int, str)  # done, total, current_name
    finished = pyqtSignal(int, int, list)  # ok, fail, errors


class SceneCopyPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._books: List[BookEntry] = []
        self._populating = False
        self._bridge: Optional[_CopyBridge] = None
        self._thread: Optional[threading.Thread] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_settings_box())
        layout.addWidget(self._build_table_box(), 1)
        layout.addWidget(self._build_action_bar())

        self._update_preview()

    # ── Settings box ───────────────────────────────────────────────────

    def _build_settings_box(self) -> QGroupBox:
        cfg = self.app.config_manager.app_config
        box = QGroupBox("Destination & nommage")
        outer = QVBoxLayout(box)
        outer.setSpacing(8)

        # Destination
        row = QHBoxLayout()
        row.addWidget(QLabel("Dossier de copie :"))
        self._dest_le = QLineEdit(cfg.scene_copy_dest)
        self._dest_le.setPlaceholderText("Choisir un dossier de destination…")
        self._dest_le.editingFinished.connect(self._save_settings)
        row.addWidget(self._dest_le, 1)
        browse = QPushButton("…")
        browse.setMaximumWidth(30)
        browse.clicked.connect(self._browse_dest)
        row.addWidget(browse)
        outer.addLayout(row)

        # Group
        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("Groupe / tag :"))
        self._group_le = QLineEdit(cfg.scene_copy_group)
        self._group_le.setMaximumWidth(220)
        self._group_le.editingFinished.connect(self._save_settings)
        self._group_le.textChanged.connect(self._update_preview)
        grp_row.addWidget(self._group_le)

        self._codec_cb = QCheckBox("Inclure {codec}")
        self._codec_cb.setChecked(cfg.scene_copy_include_codec)
        self._codec_cb.toggled.connect(self._on_toggle_codec_bitrate)
        grp_row.addWidget(self._codec_cb)

        self._bitrate_cb = QCheckBox("Inclure {bitrate}")
        self._bitrate_cb.setChecked(cfg.scene_copy_include_bitrate)
        self._bitrate_cb.toggled.connect(self._on_toggle_codec_bitrate)
        grp_row.addWidget(self._bitrate_cb)
        grp_row.addStretch()
        outer.addLayout(grp_row)

        # Templates
        form = QFormLayout()
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._dir_tpl_le  = QLineEdit(cfg.scene_copy_dir_template)
        self._file_tpl_le = QLineEdit(cfg.scene_copy_file_template)
        for le in (self._dir_tpl_le, self._file_tpl_le):
            le.editingFinished.connect(self._save_settings)
            le.textChanged.connect(self._on_template_changed)
        form.addRow("Template dossier :", self._dir_tpl_le)
        form.addRow("Template fichier :", self._file_tpl_le)
        outer.addLayout(form)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_btn = QPushButton("↺  Réinitialiser les templates")
        reset_btn.setToolTip(
            "Restaure les templates par défaut (arborescence "
            "auteur/série/volume/release).")
        reset_btn.clicked.connect(self._reset_templates)
        reset_row.addWidget(reset_btn)
        outer.addLayout(reset_row)

        help_lbl = QLabel(_TEMPLATE_HELP)
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #888; font-size: 8.5pt;")
        outer.addWidget(help_lbl)

        # Aperçu
        self._preview_lbl = QLabel("")
        self._preview_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._preview_lbl.setStyleSheet(
            "color: #b0d8ff; font-family: Consolas, monospace; font-size: 9pt;"
            "background: #1a1a1a; padding: 6px; border-radius: 4px;")
        self._preview_lbl.setWordWrap(True)
        outer.addWidget(self._preview_lbl)

        return box

    # ── Table box ──────────────────────────────────────────────────────

    def _build_table_box(self) -> QGroupBox:
        box = QGroupBox("Livres à copier")
        vl = QVBoxLayout(box)

        # Toolbar table
        bar = QHBoxLayout()
        bar.addWidget(QLabel("🔍"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher…")
        self._search.setMaximumWidth(220)
        self._search.textChanged.connect(self._refresh_filter)
        bar.addWidget(self._search)

        self._only_existing_cb = QCheckBox("Uniquement les M4B existants")
        self._only_existing_cb.setChecked(True)
        self._only_existing_cb.toggled.connect(self._refresh_filter)
        bar.addWidget(self._only_existing_cb)

        bar.addStretch()
        sel_all = QPushButton("Tout cocher")
        sel_all.clicked.connect(lambda: self._set_all_checked(True))
        bar.addWidget(sel_all)
        sel_none = QPushButton("Tout décocher")
        sel_none.clicked.connect(lambda: self._set_all_checked(False))
        bar.addWidget(sel_none)
        vl.addLayout(bar)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Titre", "Auteur", "Destination prévue"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setHighlightSections(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 32)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(1, 260)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(2, 160)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.itemChanged.connect(self._on_item_changed)
        vl.addWidget(self._table, 1)

        return box

    # ── Action bar ─────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        w = QWidget()
        bl = QHBoxLayout(w)
        bl.setContentsMargins(0, 0, 0, 0)

        self._copy_btn = QPushButton("📋  Copier la sélection")
        self._copy_btn.setStyleSheet("""
            QPushButton {
                background: #0067c0; color: white; border: none;
                padding: 6px 18px; font-weight: bold;
            }
            QPushButton:hover    { background: #0055aa; }
            QPushButton:pressed  { background: #003f88; }
            QPushButton:disabled { background: #444; color: #888; }
        """)
        self._copy_btn.clicked.connect(self._start_copy)
        bl.addWidget(self._copy_btn)

        self._open_dest_btn = QPushButton("📂  Ouvrir destination")
        self._open_dest_btn.clicked.connect(self._open_dest)
        bl.addWidget(self._open_dest_btn)

        bl.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        bl.addWidget(self._status_lbl)
        return w

    # ── Public API ─────────────────────────────────────────────────────

    def refresh_books(self):
        """Recharge la liste depuis la bibliothèque."""
        self._books = list(self.app.scanner.load_last_books() or [])
        self._fill_table()
        self._update_preview()

    # ── Settings ───────────────────────────────────────────────────────

    def _save_settings(self):
        cfg = self.app.config_manager.app_config
        cfg.scene_copy_dest             = self._dest_le.text().strip()
        cfg.scene_copy_group            = self._group_le.text().strip() or "HellTrucker"
        cfg.scene_copy_dir_template     = self._dir_tpl_le.text().strip()
        cfg.scene_copy_file_template    = self._file_tpl_le.text().strip()
        cfg.scene_copy_include_codec    = self._codec_cb.isChecked()
        cfg.scene_copy_include_bitrate  = self._bitrate_cb.isChecked()
        self.app.config_manager.save_config()

    def _on_toggle_codec_bitrate(self):
        self._save_settings()
        self._update_preview()
        self._fill_destination_column()

    def _on_template_changed(self):
        self._update_preview()
        self._fill_destination_column()

    def _reset_templates(self):
        from ..config_manager import (DEFAULT_SCENE_COPY_DIR_TEMPLATE,
                                       DEFAULT_SCENE_COPY_FILE_TEMPLATE)
        self._dir_tpl_le.setText(DEFAULT_SCENE_COPY_DIR_TEMPLATE)
        self._file_tpl_le.setText(DEFAULT_SCENE_COPY_FILE_TEMPLATE)
        self._save_settings()
        self._on_template_changed()

    def _browse_dest(self):
        start = self._dest_le.text() or self.app.config_manager.app_config.output_m4b
        path = QFileDialog.getExistingDirectory(self, "Dossier de destination", start)
        if path:
            self._dest_le.setText(path)
            self._save_settings()

    def _open_dest(self):
        dest = self._dest_le.text().strip()
        if not dest:
            return
        if not os.path.isdir(dest):
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError:
                return
        subprocess.Popen(["explorer", os.path.normpath(dest)])

    # ── Tableau ────────────────────────────────────────────────────────

    def _fill_table(self):
        self._populating = True
        try:
            self._table.setRowCount(0)
            for book in self._sorted_filtered_books():
                row = self._table.rowCount()
                self._table.insertRow(row)
                cb = QTableWidgetItem("")
                cb.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable)
                cb.setCheckState(Qt.CheckState.Unchecked)
                cb.setData(Qt.ItemDataRole.UserRole, book.id)
                self._table.setItem(row, 0, cb)

                title_item = QTableWidgetItem(book.display_title)
                title_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, 1, title_item)

                author_item = QTableWidgetItem(book.display_author)
                author_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, 2, author_item)

                dest_item = QTableWidgetItem("")
                dest_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, 3, dest_item)
        finally:
            self._populating = False
        self._fill_destination_column()

    def _sorted_filtered_books(self) -> List[BookEntry]:
        query = self._search.text().lower().strip()
        only_exist = self._only_existing_cb.isChecked()

        def _keep(b):
            if only_exist and not (b.output_m4b_path
                                   and os.path.exists(b.output_m4b_path)):
                return False
            if query and query not in b.display_title.lower() \
                    and query not in b.display_author.lower():
                return False
            return True

        return sorted([b for b in self._books if _keep(b)],
                      key=lambda b: (b.display_author.lower(),
                                     b.display_title.lower()))

    def _refresh_filter(self):
        self._fill_table()

    def _set_all_checked(self, checked: bool):
        self._populating = True
        try:
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for row in range(self._table.rowCount()):
                it = self._table.item(row, 0)
                if it:
                    it.setCheckState(state)
        finally:
            self._populating = False
        self._update_status_lbl()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._populating or item is None or item.column() != 0:
            return
        self._update_status_lbl()

    def _checked_books(self) -> List[BookEntry]:
        out = []
        by_id = {b.id: b for b in self._books}
        for row in range(self._table.rowCount()):
            it = self._table.item(row, 0)
            if it and it.checkState() == Qt.CheckState.Checked:
                bid = it.data(Qt.ItemDataRole.UserRole)
                b = by_id.get(bid)
                if b:
                    out.append(b)
        return out

    def _fill_destination_column(self):
        """Met à jour la colonne 'Destination prévue' selon les templates courants."""
        for row in range(self._table.rowCount()):
            cb = self._table.item(row, 0)
            if not cb:
                continue
            bid = cb.data(Qt.ItemDataRole.UserRole)
            book = next((b for b in self._books if b.id == bid), None)
            dest_item = self._table.item(row, 3)
            if dest_item is None or book is None:
                continue
            rel = self._render_for(book)
            dest_item.setText(rel)
            if not (book.output_m4b_path and os.path.exists(book.output_m4b_path)):
                dest_item.setForeground(QColor("#888"))
                dest_item.setToolTip("M4B source absent — copie impossible")
            else:
                dest_item.setForeground(QColor("#cfcfcf"))
                dest_item.setToolTip("")

    def _render_for(self, book: BookEntry) -> str:
        ctx = _build_context(book,
                             group=self._group_le.text().strip() or "HellTrucker",
                             include_codec=self._codec_cb.isChecked(),
                             include_bitrate=self._bitrate_cb.isChecked())
        dir_part  = _render_path_template(self._dir_tpl_le.text(),  ctx)
        file_part = _render_segment(self._file_tpl_le.text(), ctx)
        if not file_part:
            file_part = _clean(book.display_title) or "audiobook"
        return os.path.join(dir_part, file_part + ".m4b") if dir_part else file_part + ".m4b"

    def _update_preview(self):
        sample_book = next(
            (b for b in self._books
             if b.output_m4b_path and os.path.exists(b.output_m4b_path)),
            None) or (self._books[0] if self._books else None)
        if sample_book is None:
            self._preview_lbl.setText("Aperçu : (aucun livre disponible)")
            return
        rel = self._render_for(sample_book)
        dest_root = self._dest_le.text().strip() or "<destination>"
        self._preview_lbl.setText(
            f"Aperçu — {sample_book.display_title}\n"
            f"  → {os.path.join(dest_root, rel)}")

    def _update_status_lbl(self):
        n = sum(1 for r in range(self._table.rowCount())
                if (it := self._table.item(r, 0)) and it.checkState() == Qt.CheckState.Checked)
        total = self._table.rowCount()
        self._status_lbl.setText(f"{n} sélectionné{'s' if n != 1 else ''} / {total}")

    # ── Copie ──────────────────────────────────────────────────────────

    def _start_copy(self):
        if self._thread and self._thread.is_alive():
            return
        books = self._checked_books()
        if not books:
            QMessageBox.information(self, "Aucun livre",
                                    "Cochez au moins un livre à copier.")
            return
        dest_root = self._dest_le.text().strip()
        if not dest_root:
            QMessageBox.warning(self, "Destination requise",
                                "Renseigne le dossier de copie d'abord.")
            return
        # Filtre les livres sans M4B source
        valid = [b for b in books if b.output_m4b_path and os.path.exists(b.output_m4b_path)]
        skipped = len(books) - len(valid)
        if not valid:
            QMessageBox.warning(self, "Aucune source disponible",
                                "Les livres cochés n'ont pas de M4B existant.")
            return

        os.makedirs(dest_root, exist_ok=True)

        self._copy_btn.setEnabled(False)
        bridge = _CopyBridge()
        self._bridge = bridge
        bridge.progress.connect(self._on_copy_progress)
        bridge.finished.connect(self._on_copy_finished)

        console = getattr(self.app, "console_panel", None)
        if console:
            console.log(f"📋  Copie scène : {len(valid)} livre(s) → {dest_root}", "start")
            if skipped:
                console.log(f"   ({skipped} ignoré(s) — M4B source manquant)", "info")

        self._thread = threading.Thread(
            target=self._copy_worker, args=(valid, dest_root, bridge), daemon=True)
        self._thread.start()

    def _copy_worker(self, books: List[BookEntry], dest_root: str, bridge: _CopyBridge):
        ok = 0
        fail = 0
        errors: list = []
        copied_paths: list = []
        total = len(books)
        for i, book in enumerate(books, start=1):
            rel = self._render_for(book)
            target = os.path.join(dest_root, rel)
            bridge.progress.emit(i - 1, total, os.path.basename(target))
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(book.output_m4b_path, target)
                copied_paths.append(target)
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"{book.display_title}: {e}")

        # Les fichiers copiés ne doivent jamais être redétectés comme nouveaux livres
        if copied_paths:
            self.app.config_manager.add_ignore_paths(copied_paths)

        bridge.progress.emit(total, total, "")
        bridge.finished.emit(ok, fail, errors)

    def _on_copy_progress(self, done: int, total: int, name: str):
        self._status_lbl.setText(f"Copie {done}/{total}  ·  {name}")

    def _on_copy_finished(self, ok: int, fail: int, errors: list):
        self._copy_btn.setEnabled(True)
        msg = f"✓ {ok} copié{'s' if ok != 1 else ''}"
        if fail:
            msg += f"  ·  ✗ {fail} erreur{'s' if fail != 1 else ''}"
        self._status_lbl.setText(msg)
        console = getattr(self.app, "console_panel", None)
        if console:
            console.log(msg, "ok" if not fail else "error")
            for e in errors[:5]:
                console.log(f"   {e}", "error")
        if fail:
            QMessageBox.warning(self, "Copies terminées avec erreurs",
                                msg + "\n\n" + "\n".join(errors[:8]))
