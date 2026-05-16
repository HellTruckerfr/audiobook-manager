import os
import json
import subprocess
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QLabel, QLineEdit, QComboBox, QCheckBox, QCompleter,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFrame, QMenu,
    QTextEdit, QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt, QThread, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QPixmap, QColor
from .icon_utils import get_icon

from ..models import BookEntry, BookConfig, Chapter, AudioInfo
from .tag_import_dialog import TagImportDialog


_COMBO_FIELDS = ("author", "parent_series", "universe_order", "series", "volume", "narrator", "year", "language", "publisher")


class _FetchThread(QThread):
    """Récupère les métadonnées depuis Amazon en arrière-plan."""
    success = pyqtSignal(dict)
    failed  = pyqtSignal()

    def __init__(self, asin: str):
        super().__init__()
        self._asin = asin

    def run(self):
        from ..fetcher import fetch_amazon_meta
        result = fetch_amazon_meta(self._asin)
        if any(result.get(k) for k in ("title", "author", "narrator", "publisher",
                                        "year", "description", "copyright", "cover_url")):
            self.success.emit(result)
        else:
            self.failed.emit()


class _AutoCombo(QComboBox):
    """QComboBox éditable avec autocomplétion, compatible avec l'interface QLineEdit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        c = QCompleter(self)
        c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        c.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(c)

    def text(self) -> str:
        return self.currentText()

    def setText(self, value: str):
        self.lineEdit().setText(value)

    def populate(self, values: list):
        current = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems(values)
        self.lineEdit().setText(current)
        self.blockSignals(False)


def _fmt_duration(s: float) -> str:
    if not s:
        return "—"
    m, sec = divmod(int(s), 60)
    h, m   = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{sec:02d}s"


def _first_audio(folder: str) -> str:
    exts = {".mp3", ".m4b", ".m4a", ".aac", ".flac"}
    try:
        for fn in sorted(os.listdir(folder)):
            if os.path.splitext(fn)[1].lower() in exts:
                return os.path.join(folder, fn)
    except OSError:
        pass
    return ""


class EditorPanel(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, app):
        super().__init__()
        self.app   = app
        self._book: Optional[BookEntry] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_top_area())
        layout.addWidget(self._build_tabs(), 1)
        layout.addWidget(self._build_bottom_bar())
        self._load_title_source("detected")

    # ── Zone supérieure : titre + source / bouton retour ─────────────

    def _build_top_area(self) -> QWidget:
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        # ── Ligne 1 : titre du livre  +  source ──────────────────────
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background: #1e1e1e;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 6, 12, 6)
        hl.setSpacing(12)

        self._title_lbl = QLabel("Aucun livre sélectionné")
        self._title_lbl.setStyleSheet(
            "color: #eee; font-size: 11pt; font-weight: bold; font-family: 'Segoe UI';")
        hl.addWidget(self._title_lbl)
        hl.addStretch()

        hl.addWidget(QLabel("Source :"))
        self._source_cb = QComboBox()
        self._source_cb.setMinimumWidth(260)
        self._source_cb.currentIndexChanged.connect(self._on_source_changed)
        hl.addWidget(self._source_cb)

        self._quality_lbl = QLabel("")
        self._quality_lbl.setStyleSheet("color: #888; font-size: 8pt;")
        hl.addWidget(self._quality_lbl)

        self._tag_status = QLabel("")
        self._tag_status.setStyleSheet("font-size: 9pt;")
        hl.addWidget(self._tag_status)

        wl.addWidget(header)

        # ── Ligne 2 : ← Bibliothèque  +  Importer les tags ───────────
        back_bar = QWidget()
        back_bar.setFixedHeight(40)
        back_bar.setStyleSheet("background: #181818;")
        bl = QHBoxLayout(back_bar)
        bl.setContentsMargins(8, 4, 8, 4)
        bl.setSpacing(8)

        back_btn = QPushButton("←  Bibliothèque")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                color: #4a9eff; font-size: 10pt; font-weight: bold;
                border: 1px solid #2a5a9a; border-radius: 4px;
                padding: 2px 14px; background: #1a2a3a;
            }
            QPushButton:hover   { background: #1e3550; color: #77bbff; }
            QPushButton:pressed { background: #152840; }
        """)
        back_btn.clicked.connect(self.back_requested)
        bl.addWidget(back_btn)

        load_btn = QPushButton("  Importer les tags…")
        load_btn.setIcon(get_icon("importation.ico")); load_btn.setIconSize(QSize(18, 18))
        load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        load_btn.clicked.connect(self._open_tag_import)
        bl.addWidget(load_btn)

        bl.addStretch()

        wl.addWidget(back_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        wl.addWidget(sep)

        return wrapper

    # ── Onglets ───────────────────────────────────────────────────────

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget()

        self._tabs.addTab(self._build_meta_tab(),  "Métadonnées")
        self._tabs.addTab(self._build_chap_tab(),  "Chapitres")
        self._tabs.addTab(self._build_desc_tab(),  "Description")
        self._tabs.addTab(self._build_cover_tab(), "Cover")

        return self._tabs

    def _build_meta_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(12, 12, 12, 12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(6)
        self._vars: dict = {}

        for key, label in [
            ("title",         "Titre"),
            ("author",        "Auteur"),
            ("parent_series", "Univers"),
            ("universe_order", "Rang univers"),
            ("series",        "Série"),
            ("volume",        "Volume"),
            ("narrator",   "Narrateur"),
            ("genre",      "Genre"),
            ("year",       "Année"),
            ("language",   "Langue"),
            ("asin",       "ASIN"),
            ("publisher",  "Éditeur"),
            ("copyright",  "Copyright"),
        ]:
            field_w = _AutoCombo() if key in _COMBO_FIELDS else QLineEdit()
            self._vars[key] = field_w
            form.addRow(f"{label} :", field_w)

        # Bitrate + Sample rate + Watermark + IgnoreCheck — tout sur une ligne alignée
        tech_w = QWidget()
        tl = QHBoxLayout(tech_w)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)

        self._bitrate_cb = QComboBox()
        self._bitrate_cb.addItems(["64k", "96k", "128k", "192k", "256k", "320k"])
        self._bitrate_cb.setCurrentText("128k")
        self._bitrate_cb.setMaximumWidth(90)
        tl.addWidget(self._bitrate_cb)

        tl.addWidget(QLabel("Sample rate :"))
        self._sr_cb = QComboBox()
        self._sr_cb.addItems(["22050", "44100", "48000"])
        self._sr_cb.setCurrentText("44100")
        self._sr_cb.setMaximumWidth(90)
        tl.addWidget(self._sr_cb)

        tl.addSpacing(16)
        self._watermark_cb = QCheckBox("Watermark")
        tl.addWidget(self._watermark_cb)

        self._ignore_meta_cb = QCheckBox("Ignorer vérif méta")
        self._ignore_meta_cb.setToolTip(
            "Cache ce livre quand le filtre « Cacher livres complets » est actif,\n"
            "même si certains champs requis sont vides.")
        tl.addWidget(self._ignore_meta_cb)
        tl.addStretch()
        self._fetch_btn = QPushButton("  Fetch Amazon")
        self._fetch_btn.setIcon(get_icon("fetch.ico")); self._fetch_btn.setIconSize(QSize(18, 18))
        self._fetch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fetch_btn.clicked.connect(self._fetch_from_amazon)
        tl.addWidget(self._fetch_btn)

        form.addRow("Bitrate :", tech_w)

        outer.addLayout(form)
        outer.addStretch()

        return w

    def _build_desc_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(8)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Résumé du livre…")
        vl.addWidget(self._desc_edit, 1)

        return w

    def _build_chap_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(6, 6, 6, 6)

        # Radio buttons — choix de la source de titres
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Titre à utiliser :"))
        self._title_source_group = QButtonGroup(self)
        for value, label in [("detected", "Détecté"), ("normalized", "Normalisé"), ("custom", "Perso")]:
            rb = QRadioButton(label)
            rb.setProperty("title_source_value", value)
            self._title_source_group.addButton(rb)
            source_row.addWidget(rb)
        source_row.addStretch()
        self._title_source_group.buttonClicked.connect(self._on_title_source_changed)
        vl.addLayout(source_row)

        self._chap_table = QTableWidget(0, 5)
        self._chap_table.setHorizontalHeaderLabels(
            ["#", "Titre détecté", "Titre normalisé", "Titre perso", "Durée"])
        self._chap_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._chap_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._chap_table.setShowGrid(False)
        self._chap_table.verticalHeader().hide()
        self._chap_table.horizontalHeader().setHighlightSections(False)

        hh = self._chap_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)
        self._chap_table.setColumnWidth(0, 40)
        self._chap_table.setColumnWidth(1, 220)
        self._chap_table.setColumnWidth(2, 220)
        self._chap_table.setColumnWidth(3, 220)
        self._chap_table.setColumnWidth(4, 70)
        self._chap_table.doubleClicked.connect(self._edit_chapter)
        vl.addWidget(self._chap_table, 1)

        btn_row = QHBoxLayout()
        for icon_f, text, fn in [
            ("Modifier.ico",      "  Modifier titre",     self._edit_chapter),
            ("Réinitialiser.ico", "  Réinitialiser",      self._reset_chapter),
            ("Réinitialiser.ico", "  Tout réinitialiser", self._reset_all_chapters),
        ]:
            b = QPushButton(text)
            b.setIcon(get_icon(icon_f)); b.setIconSize(QSize(16, 16))
            b.clicked.connect(fn)
            btn_row.addWidget(b)
        btn_row.addStretch()
        vl.addLayout(btn_row)

        return w

    def _build_cover_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(0)

        # Créer les boutons d'abord pour mesurer leur largeur naturelle
        self._extract_btn = QPushButton("Extraire depuis source")
        self._extract_btn.clicked.connect(self._extract_cover_menu)
        self._import_btn = QPushButton("Importer image…")
        self._import_btn.clicked.connect(self._import_cover)
        self._delete_btn = QPushButton("Supprimer")
        self._delete_btn.clicked.connect(self._clear_cover)

        btn_w = (self._extract_btn.sizeHint().width()
                 + self._import_btn.sizeHint().width()
                 + self._delete_btn.sizeHint().width()
                 + 2 * 8)   # 2 espacements de 8px

        # Container centré dont la largeur = largeur des boutons = côté de l'image
        container = QWidget()
        container.setFixedWidth(btn_w)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(28)

        # Image carrée 1:1 — même largeur que les boutons, pas de cadre gris
        self._cover_lbl = QLabel("Aucune cover")
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_lbl.setFixedSize(btn_w, btn_w)
        self._cover_lbl.setStyleSheet(
            "border: 1px solid #3a3a3a; color: #888; font-size: 10pt;")
        cl.addWidget(self._cover_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._extract_btn)
        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(self._delete_btn)
        cl.addLayout(btn_row)

        self._cover_path_lbl = QLabel("")
        self._cover_path_lbl.setStyleSheet("color: #888; font-size: 8pt;")
        self._cover_path_lbl.setWordWrap(True)
        cl.addWidget(self._cover_path_lbl)

        outer.addWidget(container, 0,
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        outer.addStretch()

        return w

    # ── Barre du bas ─────────────────────────────────────────────────

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")

        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(8)

        _btn = (
            "QPushButton {"
            "  background: #2a2a2a; color: #ccc; border: 1px solid #444;"
            "  border-radius: 4px; padding: 5px 14px; font-size: 9pt;"
            "}"
            "QPushButton:hover    { background: #383838; color: #f3f3f3; border-color: #666; }"
            "QPushButton:pressed  { background: #1a1a1a; }"
            "QPushButton:disabled { background: #1e1e1e; color: #555; border-color: #333; }"
        )

        # Gauche
        prev_btn = QPushButton("  Livre précédent")
        prev_btn.setIcon(get_icon("Précédent.ico")); prev_btn.setIconSize(QSize(18, 18))
        prev_btn.setToolTip("Livre précédent (sauvegarde automatique)")
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.setStyleSheet(_btn)
        prev_btn.clicked.connect(lambda: self.navigate(-1))
        bl.addWidget(prev_btn)

        bl.addStretch()

        # Centre
        save = QPushButton("  Sauvegarder")
        save.setIcon(get_icon("Sauvegarder.ico")); save.setIconSize(QSize(18, 18))
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setStyleSheet(_btn)
        save.clicked.connect(self._save_config)
        bl.addWidget(save)

        convert_btn = QPushButton("  Convertir maintenant")
        convert_btn.setIcon(get_icon("Conversion.ico")); convert_btn.setIconSize(QSize(18, 18))
        convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        convert_btn.setStyleSheet(_btn)
        convert_btn.clicked.connect(self._convert_now)
        bl.addWidget(convert_btn)

        add_btn = QPushButton("  Ajouter à la file")
        add_btn.setIcon(get_icon("Lancer.ico")); add_btn.setIconSize(QSize(18, 18))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(_btn)
        add_btn.clicked.connect(self._add_to_queue)
        bl.addWidget(add_btn)

        bl.addStretch()

        # Droite
        next_btn = QPushButton("Livre suivant  ")
        next_btn.setIcon(get_icon("Lancer.ico")); next_btn.setIconSize(QSize(18, 18))
        next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        next_btn.setToolTip("Livre suivant (sauvegarde automatique)")
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.setStyleSheet(_btn)
        next_btn.clicked.connect(lambda: self.navigate(1))
        bl.addWidget(next_btn)

        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        wl.addWidget(sep)
        wl.addWidget(bar)
        return wrapper

    # ── Chargement du livre ───────────────────────────────────────────

    def _refresh_combo_items(self):
        cm = self.app.config_manager
        for field in _COMBO_FIELDS:
            self._vars[field].populate(cm.get_referential(field))

    def load_book(self, book: BookEntry):
        self._book = book
        cfg = book.config

        self._title_lbl.setText(book.display_title)
        self._refresh_combo_items()
        for key, le in self._vars.items():
            le.setText(getattr(cfg, key, ""))

        self._bitrate_cb.setCurrentText(cfg.bitrate)
        self._sr_cb.setCurrentText(cfg.sample_rate)
        self._watermark_cb.setChecked(cfg.watermark)
        self._ignore_meta_cb.setChecked(cfg.ignore_metadata_check)
        self._desc_edit.setPlainText(cfg.description)
        self._cover_path_lbl.setText(cfg.cover_path)
        self._tag_status.setText("")

        self._populate_source_cb(book)
        self._load_title_source(cfg.title_source)
        # Chapitres : si rien en cache, lance un ffprobe à la demande
        if not book.chapters and book.sources:
            self._lazy_load_chapters(book)
        self._load_chapters(book)
        self._load_cover(cfg.cover_path)
        self.refresh_queue_state()

    def _lazy_load_chapters(self, book: BookEntry):
        """Charge les chapitres par ffprobe quand ils ne sont pas en cache.
        Met à jour le cache pour éviter de refaire l'opération."""
        from ..scanner import _fingerprint
        try:
            chapters = self.app.scanner.load_chapters(book)
        except Exception:
            chapters = []
        if not chapters:
            return
        book.chapters = chapters
        src = book.selected_source
        if src:
            fp = _fingerprint(src.path)
            self.app.config_manager.set_chapters_cache(
                src.path, fp, [c.to_dict() for c in chapters])
            self.app.config_manager.save_scan_cache()

    def refresh_queue_state(self):
        pass  # checkbox supprimée — gardé pour compatibilité app.py

    def _populate_source_cb(self, book: BookEntry):
        self._source_cb.blockSignals(True)
        self._source_cb.clear()
        for s in book.sources:
            stereo = "Stéréo" if s.channels >= 2 else "Mono"
            self._source_cb.addItem(
                f"{s.folder_label}  —  {s.codec.upper()} {s.bitrate_kbps}k "
                f"{s.sample_rate_hz // 1000 if s.sample_rate_hz else '?'}kHz {stereo}"
            )

        selected = book.selected_source
        if selected:
            for i, s in enumerate(book.sources):
                if s.folder_label == selected.folder_label:
                    self._source_cb.setCurrentIndex(i)
                    self._update_quality_lbl(selected)
                    break
        self._source_cb.blockSignals(False)

    def _on_source_changed(self, idx: int):
        src = self._get_source(idx)
        if src:
            self._update_quality_lbl(src)
            if self._book:
                self._book.config.selected_source_label = src.folder_label

    def _get_source(self, idx: Optional[int] = None) -> Optional[AudioInfo]:
        if not self._book:
            return None
        i = self._source_cb.currentIndex() if idx is None else idx
        if 0 <= i < len(self._book.sources):
            return self._book.sources[i]
        return None

    def _update_quality_lbl(self, src: AudioInfo):
        dur = _fmt_duration(src.duration_s)
        self._quality_lbl.setText(
            f"{src.file_count} fichier{'s' if src.file_count != 1 else ''}  ·  "
            f"{dur}  ·  {src.size_mb} MB"
        )

    # ── Importer les tags (dialogue de comparaison) ───────────────────

    def _open_tag_import(self):
        if not self._book:
            return
        current = {key: le.text() for key, le in self._vars.items()}
        dlg = TagImportDialog(self, self._book, current)
        if dlg.exec() == TagImportDialog.DialogCode.Accepted and dlg.result_values:
            filled = 0
            for key, val in dlg.result_values.items():
                if key in self._vars:
                    self._vars[key].setText(val)
                    if val:
                        filled += 1
            self._tag_status.setText(
                f"✓ {filled} champ{'s' if filled != 1 else ''} importé{'s' if filled != 1 else ''}")
            self._tag_status.setStyleSheet("color: #57cc7a; font-size: 9pt;")

    # ── Charger les tags depuis source (méthode legacy conservée) ─────

    def _load_source_tags(self):
        src = self._get_source()
        if not src:
            return

        target = src.path if os.path.isfile(src.path) else _first_audio(src.path)
        if not target:
            self._tag_status.setText("Aucun fichier trouvé")
            self._tag_status.setStyleSheet("color: #e8a020; font-size: 9pt;")
            return

        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", target],
                capture_output=True, text=True, timeout=30, encoding="utf-8")
            if r.returncode != 0:
                raise RuntimeError("ffprobe failed")
            tags = {k.lower(): v for k, v in
                    (json.loads(r.stdout).get("format", {}).get("tags") or {}).items()}
        except Exception as e:
            self._tag_status.setText(f"Erreur : {e}")
            self._tag_status.setStyleSheet("color: #e8a020; font-size: 9pt;")
            return

        mapping = {
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
        }
        filled = 0
        for field, keys in mapping.items():
            for k in keys:
                val = tags.get(k, "").strip()
                if val:
                    self._vars[field].setText(val)
                    filled += 1
                    break

        self._tag_status.setText(
            f"✓ {filled} champ{'s' if filled != 1 else ''} chargé{'s' if filled != 1 else ''}")
        self._tag_status.setStyleSheet("color: #57cc7a; font-size: 9pt;")

    # ── Chapitres ─────────────────────────────────────────────────────

    def _load_chapters(self, book: BookEntry):
        from ..normalizer import normalize_chapter_title
        self._chap_table.setRowCount(len(book.chapters))
        for row, ch in enumerate(book.chapters):
            for col, text in enumerate([
                str(ch.index),
                ch.detected_title,
                normalize_chapter_title(ch.detected_title),
                ch.custom_title,
                _fmt_duration(ch.duration_s),
            ]):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._chap_table.setItem(row, col, it)

    def _edit_chapter(self):
        if not self._book:
            return
        rows = self._chap_table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        idx     = int(self._chap_table.item(row, 0).text())
        current = self._chap_table.item(row, 3).text() or self._chap_table.item(row, 1).text()

        dlg = QDialog(self)
        dlg.setWindowTitle("Modifier le titre")
        dlg.resize(400, 100)
        vl = QVBoxLayout(dlg)
        vl.addWidget(QLabel("Titre personnalisé :"))
        le = QLineEdit(current)
        vl.addWidget(le)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_title = le.text().strip()
            self._book.config.chapter_custom_titles[idx] = new_title
            for ch in self._book.chapters:
                if ch.index == idx:
                    ch.custom_title = new_title
            self._chap_table.item(row, 3).setText(new_title)

    def _reset_chapter(self):
        if not self._book:
            return
        rows = self._chap_table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        idx = int(self._chap_table.item(row, 0).text())
        self._book.config.chapter_custom_titles.pop(idx, None)
        for ch in self._book.chapters:
            if ch.index == idx:
                ch.custom_title = ""
        self._chap_table.item(row, 3).setText("")

    def _reset_all_chapters(self):
        if not self._book:
            return
        self._book.config.chapter_custom_titles.clear()
        for ch in self._book.chapters:
            ch.custom_title = ""
        self._load_chapters(self._book)

    # ── Cover ─────────────────────────────────────────────────────────

    def _load_cover(self, path: str):
        s = self._cover_lbl.width() or 300
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                px = pixmap.scaled(
                    s, s,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)
                x = (px.width()  - s) // 2
                y = (px.height() - s) // 2
                self._cover_lbl.setPixmap(px.copy(x, y, s, s))
                self._cover_lbl.setText("")
                return
        self._cover_lbl.clear()
        self._cover_lbl.setText("Aucune cover")

    def _extract_cover_menu(self):
        """Affiche un menu de choix de source si plusieurs, sinon extrait directement."""
        if not self._book:
            return
        sources = self._book.sources
        if not sources:
            return
        if len(sources) == 1:
            self._extract_cover_from(sources[0])
            return
        # Plusieurs sources → menu sous le bouton
        menu = QMenu(self)
        actions = []
        for src in sources:
            stereo = "Stéréo" if src.channels >= 2 else "Mono"
            label  = (f"{src.folder_label}  —  "
                      f"{src.codec.upper()} {src.bitrate_kbps}k {stereo}")
            action = QAction(label, menu)
            action.triggered.connect(
                lambda checked=False, s=src: self._extract_cover_from(s))
            menu.addAction(action)
            actions.append(action)
        btn_rect = self._extract_btn.rect()
        pos = self._extract_btn.mapToGlobal(btn_rect.bottomLeft())
        menu.exec(pos)

    def _extract_cover_from(self, src):
        import tempfile
        safe_label = src.folder_label.replace("/", "_").replace("\\", "_").replace(":", "_")
        out    = os.path.join(tempfile.gettempdir(),
                              f"abm_cover_{self._book.id}_{safe_label}.jpg")
        sample = src.path if os.path.isfile(src.path) else _first_audio(src.path)
        if not sample:
            return
        r = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", sample,
             "-an", "-vframes", "1", "-y", out],
            capture_output=True)
        if r.returncode == 0 and os.path.exists(out):
            self._book.config.cover_path = out
            self._cover_path_lbl.setText(out)
            self._load_cover(out)

    def _import_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer une image", "",
            "Images (*.jpg *.jpeg *.png *.webp);;Tous (*.*)")
        if path and self._book:
            self._book.config.cover_path = path
            self._cover_path_lbl.setText(path)
            self._load_cover(path)

    def _clear_cover(self):
        if self._book:
            self._book.config.cover_path = ""
            self._cover_path_lbl.setText("")
            self._cover_lbl.clear()
            self._cover_lbl.setText("Aucune cover")

    # ── Sauvegarde ────────────────────────────────────────────────────

    def _load_title_source(self, value: str):
        for btn in self._title_source_group.buttons():
            if btn.property("title_source_value") == value:
                btn.setChecked(True)
                break

    def _on_title_source_changed(self, btn):
        if self._book:
            self._book.config.title_source = btn.property("title_source_value")

    def _apply_to_config(self):
        if not self._book:
            return
        cfg = self._book.config
        for key, le in self._vars.items():
            setattr(cfg, key, le.text())
        cfg.bitrate     = self._bitrate_cb.currentText()
        cfg.sample_rate = self._sr_cb.currentText()
        cfg.watermark   = self._watermark_cb.isChecked()
        cfg.ignore_metadata_check = self._ignore_meta_cb.isChecked()
        cfg.description = self._desc_edit.toPlainText().strip()
        checked = self._title_source_group.checkedButton()
        if checked:
            cfg.title_source = checked.property("title_source_value")
        src = self._get_source()
        if src:
            cfg.selected_source_label = src.folder_label

    def _fetch_from_amazon(self):
        asin = self._vars["asin"].text().strip()
        if not asin:
            return
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("…")
        self._fetch_thread = _FetchThread(asin)
        self._fetch_thread.success.connect(self._on_fetch_success)
        self._fetch_thread.failed.connect(self._on_fetch_failed)
        self._fetch_thread.start()

    def _on_fetch_success(self, meta: dict):
        # Description : toujours remplacée (c'est l'action principale du fetch)
        if meta.get("description"):
            self._desc_edit.setPlainText(meta["description"])
        # Autres champs : seulement si le champ est vide
        for key in ("title", "author", "narrator", "publisher", "year", "copyright"):
            val = meta.get(key)
            if val and not self._vars[key].text().strip():
                self._vars[key].setText(val)
        if meta.get("cover_url") and self._book and not self._book.config.cover_url:
            self._book.config.cover_url = meta["cover_url"]
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText("  Fetch Amazon")

    def _on_fetch_failed(self):
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText("  Fetch Amazon")

    def _save_config(self):
        if not self._book:
            return
        self._apply_to_config()
        self.app.config_manager.save_book(self._book)
        self.app.library_panel.populate(self.app.library_panel._books)

    def navigate(self, delta: int):
        if not self._book:
            return
        self._save_config()
        books = self.app.library_panel.get_filtered_books()
        if not books:
            return
        try:
            idx = next(i for i, b in enumerate(books) if b.id == self._book.id)
        except StopIteration:
            return
        self.app.on_book_selected(books[(idx + delta) % len(books)])

    def _add_to_queue(self):
        if self._book:
            self._apply_to_config()
            self.app.add_to_queue(self._book)

    def _convert_now(self):
        if self._book:
            self._apply_to_config()
            self.app.convert_now(self._book)
