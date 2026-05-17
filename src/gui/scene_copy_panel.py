import os
import re
import shutil
import subprocess
import threading
import unicodedata
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QFrame,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QGroupBox, QStyle, QStyleOptionButton,
)
from PyQt6.QtCore import Qt, QObject, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QIcon, QPixmap

from ..models import BookEntry

_ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "icons")


def _icon_btn(filename: str) -> QIcon:
    return QIcon(os.path.join(_ICONS_DIR, filename))


_SMALL_BTN = "padding: 2px;"

_LANG_MAP = {
    "FR": "FRENCH", "EN": "ENGLISH", "ES": "SPANISH",
    "DE": "GERMAN", "IT": "ITALIAN", "PT": "PORTUGUESE",
    "NL": "DUTCH", "JA": "JAPANESE", "RU": "RUSSIAN",
}

_TEMPLATE_HELP = (
    "Template fichier — variables : "
    "{author}  {series}  {volume}  {integrale}  {title}  {year}  "
    "{lang}  {format}  {bitrate}  {codec}  {group}\n"
    "Template dossier — variables supplémentaires : "
    "{author_raw}  {series_raw}  {tag_album}  {book_folder}  {series_release}  {book_release}\n"
    "{book_folder} = '{series} - {volume} - {title}' pour les tomes, '{series}' pour les intégrales.\n"
    "Les segments vides sont supprimés automatiquement."
)

_TOGGLE_STYLE = """
QPushButton {
    text-align: left; padding: 5px 10px;
    background: #252525; border: 1px solid #3a3a3a;
    border-radius: 4px; font-weight: bold; color: #ccc;
}
QPushButton:hover { background: #2e2e2e; }
"""

_FILTER_STYLE = """
QPushButton {
    padding: 3px 12px; border: 1px solid #555;
    background: #2a2a2a; border-radius: 3px; color: #ccc;
}
QPushButton:checked { background: #0067c0; border-color: #0067c0; color: white; }
QPushButton:hover:!checked { background: #333; }
"""


# ── Helpers de nommage ────────────────────────────────────────────────

def _title_matches_series(title: str, series: str) -> bool:
    """True si le titre correspond au nom de série (avec ou sans suffixe numérique de tome)."""
    title_base = re.sub(
        r"[\s._]+(?:t|tome|vol\.?|volume)?\s*\d+$", "", title, flags=re.IGNORECASE
    ).strip()
    return _scene_name(title_base).lower() == _scene_name(series).lower()


def _all_series_titles_match(series: str, all_books: list) -> bool:
    """True si TOUS les livres de la série ont un titre qui correspond au nom de série."""
    series_books = [
        b for b in all_books
        if (b.config.series or "").strip().lower() == series.strip().lower()
        and (b.config.title or b.detected_title or "").strip()
    ]
    if not series_books:
        return False
    return all(
        _title_matches_series(b.config.title or b.detected_title or "", series)
        for b in series_books
    )


def _vol_number(volume: str) -> int:
    m = re.search(r'\d+', volume)
    return int(m.group(0)) if m else 0


def _scene_name(s: str) -> str:
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    parts = re.split(r"[\s']+", s)
    cleaned = [p if '.' in p else p.capitalize() for p in parts if p]
    result = ".".join(cleaned)
    result = re.sub(r"[^A-Za-z0-9.\-]", "", result)
    return re.sub(r"\.{2,}", ".", result).strip(".")


def _normalize_bitrate(kbps: int) -> str:
    for std in (64, 128):
        if abs(kbps - std) <= 10:
            return f"{std}kbps"
    return f"{kbps}kbps"


def _raw_bitrate_kbps(book: BookEntry) -> int:
    info = book.output_m4b_info or book.selected_source
    if info and info.bitrate_kbps:
        return info.bitrate_kbps
    raw = (book.config.bitrate or "128k").lower().strip()
    if raw.endswith("kbps"):
        return int(raw[:-4]) if raw[:-4].isdigit() else 128
    if raw.endswith("k"):
        return int(raw[:-1]) if raw[:-1].isdigit() else 128
    return int(raw) if raw.isdigit() else 128


def _vol_label(vol_num: int, series_name: str, all_books: List[BookEntry]) -> str:
    max_vol = vol_num
    if all_books and series_name:
        sn_low = series_name.lower()
        for b in all_books:
            sn = (b.config.series or b.detected_series or "").lower()
            if sn == sn_low and b.config.volume:
                v = _vol_number(b.config.volume)
                if v > max_vol:
                    max_vol = v
    return f"T{vol_num:03d}" if max_vol >= 100 else f"T{vol_num:02d}"


def _build_context(book: BookEntry, all_books: List[BookEntry],
                   group: str, include_codec: bool, include_bitrate: bool,
                   fmt: str, series_mode: bool = False) -> Dict[str, str]:
    cfg = book.config
    in_series   = bool(cfg.series and cfg.volume)
    is_integrale = bool(cfg.series and not cfg.volume)
    lang         = _LANG_MAP.get((cfg.language or "FR").upper(), "FRENCH")
    author_raw   = cfg.author or book.detected_author or ""
    author       = _scene_name(author_raw.split(",")[0].strip())
    series       = _scene_name(cfg.series or "")
    kbps         = _raw_bitrate_kbps(book)
    bitrate      = _normalize_bitrate(kbps) if include_bitrate else ""

    if include_codec:
        if fmt == "MP3":
            codec = ""  # format=MP3 already implies codec; avoids "MP3.128kbps.AAC-"
        else:
            _info = book.output_m4b_info or book.selected_source
            _raw  = (_info.codec or "aac").lower() if _info else "aac"
            _map  = {"aac": "AAC", "mp3": "MP3", "opus": "Opus", "flac": "FLAC"}
            codec = _map.get(_raw, _raw.upper())
    else:
        codec = ""

    src_info   = book.selected_source
    m4b_info   = book.output_m4b_info
    tag_album  = (
        (src_info.tag_album  if src_info  and src_info.tag_album  else None)
        or (m4b_info.tag_album if m4b_info and m4b_info.tag_album else None)
        or cfg.title or book.detected_title or ""
    )
    series_raw   = cfg.series or ""
    parent_series = cfg.parent_series or ""

    if series_mode:
        vol_str   = ""
        integrale = "Integrale" if cfg.series else ""
        title     = ""
        year      = ""
    else:
        vol_str   = _vol_label(_vol_number(cfg.volume), cfg.series or "", all_books) if cfg.volume else ""
        integrale = "Integrale" if is_integrale else ""
        raw_title = cfg.title or book.detected_title or ""
        title     = _scene_name(raw_title)
        # Supprimer le titre quand il est redondant avec la série :
        # uniquement si TOUS les tomes de la série suivent ce pattern.
        if (cfg.series and title
                and _title_matches_series(raw_title, cfg.series)
                and _all_series_titles_match(cfg.series, all_books)):
            title = ""
        year      = cfg.year or ""

    if series_mode:
        book_folder = series if series else title
    elif in_series:
        book_folder = " - ".join(p for p in [series, vol_str, title] if p)
    elif is_integrale:
        book_folder = series
    else:
        book_folder = title or tag_album

    return {
        "author_raw": author_raw,
        "author":     author,
        "title":      title,
        "series":     series,
        "series_raw":    series_raw,
        "parent_series": parent_series,
        "volume":     vol_str,
        "integrale":  integrale,
        "year":       year,
        "lang":       lang,
        "format":     fmt,
        "bitrate":    bitrate,
        "codec":      codec,
        "group":      group or "",
        "tag_album":  tag_album,
        "book_folder": book_folder,
    }


def _render_release(template: str, ctx: Dict[str, str]) -> str:
    result = template
    for k, v in ctx.items():
        result = result.replace(f"{{{k}}}", v)
    result = re.sub(r'\.{2,}', '.', result).strip('.')
    result = re.sub(r'\.-', '-', result)
    result = re.sub(r'-$', '', result)
    return result


def _render_dir(template: str, ctx: Dict[str, str]) -> str:
    result = template
    for k, v in ctx.items():
        result = result.replace(f"{{{k}}}", v)
    parts = [p for p in result.replace("\\", "/").split("/") if p.strip()]
    return os.path.join(*parts) if parts else ""


def _compute_releases(book: BookEntry, all_books: List[BookEntry],
                      group: str, include_codec: bool, include_bitrate: bool,
                      file_tpl: str, fmt: str):
    cfg          = book.config
    is_integrale = bool(cfg.series and not cfg.volume)
    series_release = ""
    book_release   = ""
    if cfg.series:
        s_ctx = _build_context(book, all_books, group, include_codec, include_bitrate,
                               fmt, series_mode=True)
        series_release = _render_release(file_tpl, s_ctx)
    if not is_integrale:
        b_ctx = _build_context(book, all_books, group, include_codec, include_bitrate,
                               fmt, series_mode=False)
        book_release = _render_release(file_tpl, b_ctx)
    return series_release, book_release


class _CopyBridge(QObject):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int, list)


class _CheckHeaderView(QHeaderView):
    check_toggled = pyqtSignal(bool)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._check_col = _COL_CB
        self._checked = False
        self._partial = False
        self.setSectionsClickable(True)

    def set_state(self, checked: bool, partial: bool = False):
        if self._checked != checked or self._partial != partial:
            self._checked = checked
            self._partial = partial
            self.viewport().update()

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()
        if logicalIndex == self._check_col:
            opt = QStyleOptionButton()
            size = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
            x = rect.x() + (rect.width() - size) // 2
            y = rect.y() + (rect.height() - size) // 2
            opt.rect = QRect(x, y, size, size)
            if self._partial:
                opt.state = (QStyle.StateFlag.State_Enabled
                             | QStyle.StateFlag.State_On
                             | QStyle.StateFlag.State_NoChange)
            elif self._checked:
                opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_On
            else:
                opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Off
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                                       opt, painter)

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.pos()) == self._check_col:
            self.check_toggled.emit(not self._checked)
            return
        super().mousePressEvent(event)


# ── Colonnes du tableau ───────────────────────────────────────────────
_COL_CB   = 0
_COL_TITLE = 1
_COL_AUTHOR = 2
_COL_M4B  = 3
_COL_MP3  = 4
_COL_DEST = 5


class SceneCopyPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._books: List[BookEntry] = []
        self._populating = False
        self._bridge: Optional[_CopyBridge] = None
        self._thread: Optional[threading.Thread] = None
        self._sort_col: int = -1
        self._sort_asc: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(6)

        # ── En-tête rétractable ───────────────────────────────────────
        self._toggle_btn = QPushButton("▼  Destination & nommage")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setStyleSheet(_TOGGLE_STYLE)
        self._toggle_btn.toggled.connect(self._on_settings_toggled)
        layout.addWidget(self._toggle_btn)

        self._settings_widget = self._build_settings_content()
        layout.addWidget(self._settings_widget)

        layout.addWidget(self._build_table_box(), 1)
        layout.addWidget(self._build_action_bar())

        self._update_preview()

    # ── Rétraction ─────────────────────────────────────────────────────

    def _on_settings_toggled(self, expanded: bool):
        self._settings_widget.setVisible(expanded)
        self._toggle_btn.setText(
            "▼  Destination & nommage" if expanded else "▶  Destination & nommage")

    # ── Contenu des réglages ───────────────────────────────────────────

    def _build_settings_content(self) -> QFrame:
        cfg = self.app.config_manager.app_config
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        _align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)

        # Row 0 : Dossier M4B
        grid.addWidget(QLabel("Dossier M4B :"), 0, 0, _align)
        self._dest_m4b_le = QLineEdit(cfg.scene_copy_dest_m4b)
        self._dest_m4b_le.setPlaceholderText("Dossier de destination pour les M4B…")
        self._dest_m4b_le.editingFinished.connect(self._save_settings)
        grid.addWidget(self._dest_m4b_le, 0, 1)
        b_m4b = QPushButton(); b_m4b.setFixedWidth(30)
        b_m4b.setIcon(_icon_btn("folder.ico")); b_m4b.setIconSize(QSize(20, 20))
        b_m4b.setStyleSheet(_SMALL_BTN)
        b_m4b.clicked.connect(lambda: self._browse_dest(self._dest_m4b_le))
        grid.addWidget(b_m4b, 0, 2)

        # Row 1 : Dossier MP3
        grid.addWidget(QLabel("Dossier MP3 :"), 1, 0, _align)
        self._dest_mp3_le = QLineEdit(cfg.scene_copy_dest_mp3)
        self._dest_mp3_le.setPlaceholderText("Dossier de destination pour les MP3…")
        self._dest_mp3_le.editingFinished.connect(self._save_settings)
        grid.addWidget(self._dest_mp3_le, 1, 1)
        b_mp3 = QPushButton(); b_mp3.setFixedWidth(30)
        b_mp3.setIcon(_icon_btn("folder.ico")); b_mp3.setIconSize(QSize(20, 20))
        b_mp3.setStyleSheet(_SMALL_BTN)
        b_mp3.clicked.connect(lambda: self._browse_dest(self._dest_mp3_le))
        grid.addWidget(b_mp3, 1, 2)

        # Row 2 : Groupe / tag + checkboxes
        grid.addWidget(QLabel("Groupe / tag :"), 2, 0, _align)
        grp_w = QWidget()
        grp_h = QHBoxLayout(grp_w)
        grp_h.setContentsMargins(0, 0, 0, 0)
        grp_h.setSpacing(10)
        self._group_le = QLineEdit(cfg.scene_copy_group)
        self._group_le.setMaximumWidth(220)
        self._group_le.editingFinished.connect(self._save_settings)
        self._group_le.textChanged.connect(self._on_options_changed)
        grp_h.addWidget(self._group_le)
        self._codec_cb = QCheckBox("Inclure codec")
        self._codec_cb.setChecked(cfg.scene_copy_include_codec)
        self._codec_cb.toggled.connect(self._on_options_changed)
        grp_h.addWidget(self._codec_cb)
        self._bitrate_cb = QCheckBox("Inclure bitrate")
        self._bitrate_cb.setChecked(cfg.scene_copy_include_bitrate)
        self._bitrate_cb.toggled.connect(self._on_options_changed)
        grp_h.addWidget(self._bitrate_cb)
        grp_h.addStretch()
        grid.addWidget(grp_w, 2, 1, 1, 2)

        # Row 3 : Template dossier
        grid.addWidget(QLabel("Template dossier :"), 3, 0, _align)
        self._dir_tpl_le = QLineEdit(cfg.scene_copy_dir_template)
        self._dir_tpl_le.editingFinished.connect(self._save_settings)
        self._dir_tpl_le.textChanged.connect(self._on_options_changed)
        grid.addWidget(self._dir_tpl_le, 3, 1, 1, 2)

        # Row 4 : Template fichier
        grid.addWidget(QLabel("Template fichier  :"), 4, 0, _align)
        self._file_tpl_le = QLineEdit(cfg.scene_copy_file_template)
        self._file_tpl_le.editingFinished.connect(self._save_settings)
        self._file_tpl_le.textChanged.connect(self._on_options_changed)
        grid.addWidget(self._file_tpl_le, 4, 1, 1, 2)

        outer.addLayout(grid)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_btn = QPushButton("  Réinitialiser les templates")
        reset_btn.setIcon(_icon_btn("Réinitialiser.ico")); reset_btn.setIconSize(QSize(16, 16))
        reset_btn.clicked.connect(self._reset_templates)
        reset_row.addWidget(reset_btn)
        outer.addLayout(reset_row)

        help_lbl = QLabel(_TEMPLATE_HELP)
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #888; font-size: 8.5pt;")
        outer.addWidget(help_lbl)

        self._preview_lbl = QLabel("")
        self._preview_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._preview_lbl.setStyleSheet(
            "color: #b0d8ff; font-family: Consolas, monospace; font-size: 9pt;"
            "background: #1a1a1a; padding: 6px; border-radius: 4px;")
        self._preview_lbl.setWordWrap(True)
        outer.addWidget(self._preview_lbl)

        return frame

    # ── Table box ──────────────────────────────────────────────────────

    def _build_table_box(self) -> QGroupBox:
        box = QGroupBox("Livres à copier")
        vl = QVBoxLayout(box)

        bar = QHBoxLayout()
        bar.addSpacing(36)  # aligne avec le début de la colonne Titre
        bar.addWidget(QLabel("🔍"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher…")
        self._search.setMaximumWidth(220)
        self._search.textChanged.connect(self._refresh_filter)
        bar.addWidget(self._search)

        self._filter_m4b_btn = QPushButton("M4B")
        self._filter_m4b_btn.setCheckable(True)
        self._filter_m4b_btn.setStyleSheet(_FILTER_STYLE)
        self._filter_m4b_btn.setToolTip("Filtrer les livres avec M4B disponible · Copier uniquement en M4B")
        self._filter_m4b_btn.toggled.connect(self._refresh_filter)
        bar.addWidget(self._filter_m4b_btn)

        self._filter_mp3_btn = QPushButton("MP3")
        self._filter_mp3_btn.setCheckable(True)
        self._filter_mp3_btn.setStyleSheet(_FILTER_STYLE)
        self._filter_mp3_btn.setToolTip("Filtrer les livres avec MP3 disponible · Copier uniquement en MP3")
        self._filter_mp3_btn.toggled.connect(self._refresh_filter)
        bar.addWidget(self._filter_mp3_btn)

        bar.addStretch()
        vl.addLayout(bar)

        self._table = QTableWidget(0, 6)
        check_header = _CheckHeaderView(Qt.Orientation.Horizontal, self._table)
        self._check_header = check_header
        self._table.setHorizontalHeader(check_header)
        self._table.setHorizontalHeaderLabels(
            ["", "Titre", "Auteur", "M4B", "MP3", "Destination M4B prévue"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        check_header.setHighlightSections(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(_COL_CB,     QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CB,  32)
        hh.setSectionResizeMode(_COL_TITLE,  QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_TITLE, 220)
        hh.setSectionResizeMode(_COL_AUTHOR, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_AUTHOR, 150)
        hh.setSectionResizeMode(_COL_M4B,   QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_M4B, 45)
        hh.setSectionResizeMode(_COL_MP3,   QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_MP3, 45)
        hh.setSectionResizeMode(_COL_DEST,  QHeaderView.ResizeMode.Stretch)
        check_header.check_toggled.connect(self._on_check_header_toggled)
        check_header.sectionClicked.connect(self._sort_by)
        check_header.setSortIndicatorShown(True)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.currentItemChanged.connect(lambda *_: self._update_preview())
        vl.addWidget(self._table, 1)

        return box

    # ── Action bar ─────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        w = QWidget()
        bl = QHBoxLayout(w)
        bl.setContentsMargins(0, 0, 0, 0)

        self._copy_btn = QPushButton("  Copier la sélection")
        self._copy_btn.setIcon(_icon_btn("exportation.ico")); self._copy_btn.setIconSize(QSize(18, 18))
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

        open_m4b = QPushButton("  M4B")
        open_m4b.setIcon(_icon_btn("folder.ico"))
        open_m4b.setIconSize(QSize(18, 18))
        open_m4b.setToolTip("Ouvrir le dossier M4B")
        open_m4b.clicked.connect(lambda: self._open_dest(self._dest_m4b_le))
        bl.addWidget(open_m4b)

        open_mp3 = QPushButton("  MP3")
        open_mp3.setIcon(_icon_btn("folder.ico"))
        open_mp3.setIconSize(QSize(18, 18))
        open_mp3.setToolTip("Ouvrir le dossier MP3")
        open_mp3.clicked.connect(lambda: self._open_dest(self._dest_mp3_le))
        bl.addWidget(open_mp3)

        bl.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        bl.addWidget(self._status_lbl)
        return w

    # ── Public API ─────────────────────────────────────────────────────

    def refresh_books(self):
        self._books = list(self.app.scanner.load_last_books() or [])
        self._fill_table()
        self._update_preview()

    # ── Settings ───────────────────────────────────────────────────────

    def _save_settings(self):
        cfg = self.app.config_manager.app_config
        cfg.scene_copy_dest_m4b        = self._dest_m4b_le.text().strip()
        cfg.scene_copy_dest_mp3        = self._dest_mp3_le.text().strip()
        cfg.scene_copy_dir_template    = self._dir_tpl_le.text().strip()
        cfg.scene_copy_file_template   = self._file_tpl_le.text().strip()
        cfg.scene_copy_group           = self._group_le.text().strip() or ""
        cfg.scene_copy_include_codec   = self._codec_cb.isChecked()
        cfg.scene_copy_include_bitrate = self._bitrate_cb.isChecked()
        self.app.config_manager.save_config()

    def _on_options_changed(self):
        self._save_settings()
        self._update_preview()
        self._fill_destination_column()

    def _reset_templates(self):
        from ..config_manager import (DEFAULT_SCENE_COPY_DIR_TEMPLATE,
                                       DEFAULT_SCENE_COPY_FILE_TEMPLATE)
        self._dir_tpl_le.setText(DEFAULT_SCENE_COPY_DIR_TEMPLATE)
        self._file_tpl_le.setText(DEFAULT_SCENE_COPY_FILE_TEMPLATE)
        self._save_settings()
        self._on_options_changed()

    def _browse_dest(self, line_edit: QLineEdit):
        start = line_edit.text() or self.app.config_manager.app_config.output_m4b
        path = QFileDialog.getExistingDirectory(self, "Dossier de destination", start)
        if path:
            line_edit.setText(path)
            self._save_settings()

    def _open_dest(self, line_edit: QLineEdit):
        dest = line_edit.text().strip()
        if not dest:
            return
        if not os.path.isdir(dest):
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError:
                return
        subprocess.Popen(["explorer", os.path.normpath(dest)])

    # ── Table ──────────────────────────────────────────────────────────

    def _has_m4b(self, book: BookEntry) -> bool:
        return bool(book.output_m4b_path and os.path.exists(book.output_m4b_path))

    def _has_mp3(self, book: BookEntry) -> bool:
        return bool(book.output_mp3_dir and os.path.isdir(book.output_mp3_dir))

    def _has_export(self, book: BookEntry) -> bool:
        return self._has_m4b(book) or self._has_mp3(book)

    def _fill_table(self):
        self._populating = True
        try:
            self._table.setRowCount(0)
            for book in self._sorted_filtered_books():
                row = self._table.rowCount()
                self._table.insertRow(row)

                # Col 0 — checkbox
                cb_item = QTableWidgetItem("")
                cb_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                                 | Qt.ItemFlag.ItemIsUserCheckable)
                cb_item.setCheckState(Qt.CheckState.Unchecked)
                cb_item.setData(Qt.ItemDataRole.UserRole, book.id)
                self._table.setItem(row, _COL_CB, cb_item)

                # Col 1 — titre
                ti = QTableWidgetItem(book.display_title)
                ti.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, _COL_TITLE, ti)

                # Col 2 — auteur
                ai = QTableWidgetItem(book.display_author)
                ai.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, _COL_AUTHOR, ai)

                # Col 3 — M4B dispo
                has_m4b = self._has_m4b(book)
                m4b_item = QTableWidgetItem("✓" if has_m4b else "✗")
                m4b_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                m4b_item.setForeground(QColor("#4caf50") if has_m4b else QColor("#f44336"))
                m4b_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, _COL_M4B, m4b_item)

                # Col 4 — MP3 dispo
                has_mp3 = self._has_mp3(book)
                mp3_item = QTableWidgetItem("✓" if has_mp3 else "✗")
                mp3_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                mp3_item.setForeground(QColor("#4caf50") if has_mp3 else QColor("#f44336"))
                mp3_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, _COL_MP3, mp3_item)

                # Col 5 — destination prévue
                di = QTableWidgetItem("")
                di.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._table.setItem(row, _COL_DEST, di)
        finally:
            self._populating = False
        self._fill_destination_column()
        self._update_check_header()
        self._update_status_lbl()

    def _sorted_filtered_books(self) -> List[BookEntry]:
        query = self._search.text().lower().strip()
        f_m4b = self._filter_m4b_btn.isChecked()
        f_mp3 = self._filter_mp3_btn.isChecked()

        def _keep(b):
            if f_m4b and not self._has_m4b(b):
                return False
            if f_mp3 and not self._has_mp3(b):
                return False
            if query and query not in b.display_title.lower() \
                    and query not in b.display_author.lower():
                return False
            return True

        books = [b for b in self._books if _keep(b)]
        if self._sort_col == _COL_TITLE:
            books.sort(key=lambda b: b.display_title.lower(), reverse=not self._sort_asc)
        elif self._sort_col == _COL_AUTHOR:
            books.sort(key=lambda b: b.display_author.lower(), reverse=not self._sort_asc)
        else:
            books.sort(key=lambda b: (b.display_author.lower(), b.display_title.lower()))
        return books

    def _refresh_filter(self):
        self._fill_table()

    def _set_all_checked(self, checked: bool):
        self._populating = True
        try:
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for row in range(self._table.rowCount()):
                it = self._table.item(row, _COL_CB)
                if it:
                    it.setCheckState(state)
        finally:
            self._populating = False
        self._update_check_header()
        self._update_status_lbl()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._populating or item is None or item.column() != _COL_CB:
            return
        self._update_check_header()
        self._update_status_lbl()

    def _on_check_header_toggled(self, checked: bool):
        self._set_all_checked(checked)

    def _update_check_header(self):
        n = self._table.rowCount()
        checked_count = sum(
            1 for row in range(n)
            if (cb := self._table.item(row, _COL_CB))
            and cb.checkState() == Qt.CheckState.Checked
        )
        self._check_header.set_state(checked_count == n and n > 0, 0 < checked_count < n)

    _SORTABLE_COLS = {_COL_TITLE, _COL_AUTHOR}

    def _sort_by(self, col: int):
        if col not in self._SORTABLE_COLS:
            return
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        order = Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder
        self._check_header.setSortIndicator(col, order)
        self._rebuild_table()

    def _rebuild_table(self):
        checked_ids = {
            self._table.item(r, _COL_CB).data(Qt.ItemDataRole.UserRole)
            for r in range(self._table.rowCount())
            if (it := self._table.item(r, _COL_CB))
            and it.checkState() == Qt.CheckState.Checked
        }
        self._fill_table()
        if checked_ids:
            self._populating = True
            try:
                for r in range(self._table.rowCount()):
                    it = self._table.item(r, _COL_CB)
                    if it and it.data(Qt.ItemDataRole.UserRole) in checked_ids:
                        it.setCheckState(Qt.CheckState.Checked)
            finally:
                self._populating = False
            self._update_check_header()
            self._update_status_lbl()

    def _checked_books(self) -> List[BookEntry]:
        out = []
        by_id = {b.id: b for b in self._books}
        for row in range(self._table.rowCount()):
            it = self._table.item(row, _COL_CB)
            if it and it.checkState() == Qt.CheckState.Checked:
                b = by_id.get(it.data(Qt.ItemDataRole.UserRole))
                if b:
                    out.append(b)
        return out

    def _fill_destination_column(self):
        for row in range(self._table.rowCount()):
            cb = self._table.item(row, _COL_CB)
            if not cb:
                continue
            book = next((b for b in self._books
                         if b.id == cb.data(Qt.ItemDataRole.UserRole)), None)
            di = self._table.item(row, _COL_DEST)
            if di is None or book is None:
                continue
            rel = self._render_for(book, "M4B")
            di.setText(rel)
            if not self._has_export(book):
                di.setForeground(QColor("#888"))
                di.setToolTip("Aucun export disponible")
            else:
                di.setForeground(QColor("#cfcfcf"))
                di.setToolTip("")

    def _render_for(self, book: BookEntry, fmt: str = "M4B") -> str:
        group          = self._group_le.text().strip() or ""
        include_codec  = self._codec_cb.isChecked()
        include_bitrate = self._bitrate_cb.isChecked()
        file_tpl       = self._file_tpl_le.text()
        dir_tpl        = self._dir_tpl_le.text()

        series_release, book_release = _compute_releases(
            book, self._books, group, include_codec, include_bitrate, file_tpl, fmt)

        is_integrale = bool(book.config.series and not book.config.volume)
        stem = series_release if is_integrale else book_release
        ext  = ".m4b" if fmt == "M4B" else ""

        # Contexte complet : toutes les variables du template fichier + variables dossier
        full_ctx = _build_context(book, self._books, group, include_codec, include_bitrate, fmt)
        dir_ctx = {**full_ctx, "series_release": series_release, "book_release": book_release}
        if fmt == "MP3":
            dir_ctx["tag_album"] = stem
            return _render_dir(dir_tpl, dir_ctx)
        return os.path.join(_render_dir(dir_tpl, dir_ctx), stem + ext)

    def _update_preview(self):
        sample = None
        row = self._table.currentRow()
        if row >= 0:
            cb = self._table.item(row, _COL_CB)
            if cb:
                bid = cb.data(Qt.ItemDataRole.UserRole)
                sample = next((b for b in self._books if b.id == bid), None)
        if sample is None:
            sample = next((b for b in self._books if self._has_export(b)), None) \
                     or (self._books[0] if self._books else None)
        if sample is None:
            self._preview_lbl.setText("Aperçu : (aucun livre disponible)")
            return
        dest_m4b = self._dest_m4b_le.text().strip() or "<dest M4B>"
        dest_mp3 = self._dest_mp3_le.text().strip() or "<dest MP3>"
        lines = [f"Aperçu — {sample.display_title}"]
        lines.append(f"  M4B → {os.path.join(dest_m4b, self._render_for(sample, 'M4B'))}")
        lines.append(f"  MP3 → {os.path.join(dest_mp3, self._render_for(sample, 'MP3'))}")
        self._preview_lbl.setText("\n".join(lines))

    def _update_status_lbl(self):
        n = sum(1 for r in range(self._table.rowCount())
                if (it := self._table.item(r, _COL_CB))
                and it.checkState() == Qt.CheckState.Checked)
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
        dest_m4b = self._dest_m4b_le.text().strip()
        dest_mp3 = self._dest_mp3_le.text().strip()
        if not dest_m4b and not dest_mp3:
            QMessageBox.warning(self, "Destination requise",
                                "Renseigne au moins un dossier de destination.")
            return

        # Les boutons filtre contrôlent aussi les formats à copier.
        # Si aucun n'est coché : copier les deux formats (comportement par défaut).
        f_m4b = self._filter_m4b_btn.isChecked()
        f_mp3 = self._filter_mp3_btn.isChecked()
        copy_m4b = (not f_m4b and not f_mp3) or f_m4b
        copy_mp3 = (not f_m4b and not f_mp3) or f_mp3

        valid   = [b for b in books if self._has_export(b)]
        skipped = len(books) - len(valid)
        if not valid:
            QMessageBox.warning(self, "Aucune source",
                                "Les livres cochés n'ont aucun export disponible.")
            return

        for d in ((dest_m4b if copy_m4b else None), (dest_mp3 if copy_mp3 else None)):
            if d:
                os.makedirs(d, exist_ok=True)

        self._copy_btn.setEnabled(False)
        bridge = _CopyBridge()
        self._bridge = bridge
        bridge.progress.connect(self._on_copy_progress)
        bridge.finished.connect(self._on_copy_finished)

        console = getattr(self.app, "console_panel", None)
        if console:
            console.log_action(f"📋  Copie scène : {len(valid)} livre(s)", "start")
            if copy_m4b and dest_m4b:
                console.log_action(f"   M4B → {dest_m4b}", "info")
            if copy_mp3 and dest_mp3:
                console.log_action(f"   MP3 → {dest_mp3}", "info")
            if skipped:
                console.log_action(f"   ({skipped} ignoré(s) — aucun export)", "info")

        group           = self._group_le.text().strip() or ""
        include_codec   = self._codec_cb.isChecked()
        include_bitrate = self._bitrate_cb.isChecked()
        dir_tpl         = self._dir_tpl_le.text()
        file_tpl        = self._file_tpl_le.text()
        all_books       = list(self._books)

        self._thread = threading.Thread(
            target=self._copy_worker,
            args=(valid, dest_m4b, dest_mp3, bridge,
                  group, include_codec, include_bitrate, dir_tpl, file_tpl, all_books,
                  copy_m4b, copy_mp3),
            daemon=True)
        self._thread.start()

    def _copy_worker(self, books: List[BookEntry],
                     dest_m4b: str, dest_mp3: str,
                     bridge: _CopyBridge,
                     group: str, include_codec: bool, include_bitrate: bool,
                     dir_tpl: str, file_tpl: str,
                     all_books: List[BookEntry],
                     copy_m4b: bool = True, copy_mp3: bool = True):
        from ..nfo import write_m4b_nfo, write_mp3_nfo
        ok    = 0
        fail  = 0
        errors: list = []
        copied_paths: list = []
        total = len(books)

        def get_paths(book: BookEntry, fmt: str):
            series_rel, book_rel = _compute_releases(
                book, all_books, group, include_codec, include_bitrate, file_tpl, fmt)
            is_integrale = bool(book.config.series and not book.config.volume)
            stem = series_rel if is_integrale else book_rel
            full_ctx = _build_context(book, all_books, group, include_codec, include_bitrate, fmt)
            dir_ctx = {**full_ctx, "series_release": series_rel, "book_release": book_rel}
            if fmt == "MP3":
                dir_ctx["tag_album"] = stem
            return _render_dir(dir_tpl, dir_ctx), stem, series_rel

        # Copie livre par livre
        for i, book in enumerate(books, start=1):
            bridge.progress.emit(i - 1, total, book.display_title)

            # M4B
            if copy_m4b and dest_m4b and book.output_m4b_path and os.path.exists(book.output_m4b_path):
                folder, stem, _ = get_paths(book, "M4B")
                target = os.path.join(dest_m4b, folder, stem + ".m4b")
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copy2(book.output_m4b_path, target)
                    copied_paths.append(target)
                    book.config.scene_m4b_path = target
                    self.app.config_manager.save_book(book)
                    try:
                        write_m4b_nfo(book, target)
                    except Exception as e:
                        errors.append(f"{book.display_title} (NFO M4B): {e}")
                    ok += 1
                except Exception as e:
                    fail += 1
                    errors.append(f"{book.display_title} (M4B): {e}")

            # MP3
            if copy_mp3 and dest_mp3 and book.output_mp3_dir and os.path.isdir(book.output_mp3_dir):
                folder, stem, _ = get_paths(book, "MP3")
                book_folder = os.path.join(dest_mp3, folder)
                try:
                    os.makedirs(book_folder, exist_ok=True)
                    mp3_files = [f for f in os.listdir(book.output_mp3_dir)
                                 if f.lower().endswith(".mp3")]
                    for fname in mp3_files:
                        shutil.copy2(os.path.join(book.output_mp3_dir, fname),
                                     os.path.join(book_folder, fname))
                    nfo_path = os.path.join(book_folder, stem + ".nfo")
                    try:
                        write_mp3_nfo(book, nfo_path, book.output_mp3_dir)
                    except Exception as e:
                        errors.append(f"{book.display_title} (NFO MP3): {e}")
                    if mp3_files:
                        book.config.scene_mp3_path = book_folder
                        self.app.config_manager.save_book(book)
                        ok += 1
                    else:
                        errors.append(f"{book.display_title} (MP3): dossier source vide")
                except Exception as e:
                    fail += 1
                    errors.append(f"{book.display_title} (MP3): {e}")

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
            console.log_action(msg, "ok" if not fail else "error")
            for e in errors[:5]:
                console.log_action(f"   {e}", "error")
        if fail:
            QMessageBox.warning(self, "Copies terminées avec erreurs",
                                msg + "\n\n" + "\n".join(errors[:8]))
