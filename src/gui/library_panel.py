import os
import re
import subprocess
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QLabel, QAbstractItemView, QMenu,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QMessageBox,
    QCheckBox, QPushButton, QScrollArea, QStackedWidget, QSlider,
    QStyle, QStyleOptionButton,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QProgressBar

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
        if book.source_is_output:
            return "⚠", "#c8a000"  # converti mais source originale disparue
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


# ── Catalogue helpers ──────────────────────────────────────────────────────


def _vol_key(vol: str):
    if not vol:
        return (999, "")
    m = re.match(r'^(\d+(?:\.\d+)?)', vol.strip())
    return (float(m.group(1)), vol) if m else (999, vol)


def _primary_author(author: str) -> str:
    """Premier auteur quand plusieurs sont séparés par une virgule."""
    return author.split(",")[0].strip() if author else "?"


def _folder_jpg(directory: str) -> str:
    """Cherche folder.jpg/cover.jpg dans un dossier donné."""
    if not directory:
        return ""
    for name in ("folder.jpg", "folder.jpeg", "folder.png",
                 "cover.jpg", "cover.png"):
        p = os.path.join(directory, name)
        if os.path.isfile(p):
            return p
    return ""


def _book_cover_path(book) -> str:
    """folder.jpg dans dirname(m4b) = dossier série ou auteur, sinon config.cover_path.
    Utilisé pour les cartes DE GROUPE (série, auteur).
    Structure : root/auteur/[série/]livre.m4b  (le M4B est directement dans son dossier)
    """
    if book.output_m4b_path:
        p = _folder_jpg(os.path.dirname(book.output_m4b_path))
        if p:
            return p
    if book.config.cover_path and os.path.isfile(book.config.cover_path):
        return book.config.cover_path
    return ""


def _individual_cover_path(book) -> str:
    """Cover du livre individuel : config.cover_path UNIQUEMENT.
    Pas de folder.jpg — sinon on remonterait au dossier série/auteur par erreur.
    """
    if book.config.cover_path and os.path.isfile(book.config.cover_path):
        return book.config.cover_path
    return ""


def _series_cover_path(book) -> str:
    """folder.jpg dans le dossier série = dirname(m4b).
    Le M4B est directement dans le dossier série → dirname(m4b) = dossier série.
    """
    if not book.output_m4b_path:
        return _book_cover_path(book)
    return _folder_jpg(os.path.dirname(book.output_m4b_path)) or _book_cover_path(book)


def _author_cover_path(book) -> str:
    """folder.jpg dans le dossier auteur.
    Série      : dirname(dirname(m4b)) = dirname(série) = auteur
    Standalone : dirname(m4b) = auteur (le M4B est directement dans le dossier auteur)
    """
    if not book.output_m4b_path:
        return _book_cover_path(book)
    m4b_dir = os.path.dirname(book.output_m4b_path)
    if (book.config.series or "").strip():
        author_dir = os.path.dirname(m4b_dir)   # remonter 1 niveau au-dessus du dossier série
    else:
        author_dir = m4b_dir                     # le M4B standalone est dans le dossier auteur
    return _folder_jpg(author_dir) or _book_cover_path(book)


def _placeholder_pixmap(title: str, w: int, h: int) -> QPixmap:
    px = QPixmap(w, h)
    px.fill(QColor("#252525"))
    p = QPainter(px)
    p.setPen(QColor("#3a3a3a"))
    p.drawRect(0, 0, w - 1, h - 1)
    font = QFont("Segoe UI", 18, QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor("#555"))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter,
               (title[:2].upper() if title else "?"))
    p.end()
    return px


class _CatalogueCard(QWidget):
    """Clickable card : cover square thumbnail + title + optional subtitle."""
    clicked = pyqtSignal()

    def __init__(self, title: str, cover_path: str = "",
                 subtitle: str = "", card_size: int = 150, parent=None):
        super().__init__(parent)
        cw = ch = card_size
        w  = cw + 16
        h  = ch + 60
        self.setFixedSize(w, h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(8, 8, 8, 6)
        vl.setSpacing(4)

        self._cover = QLabel()
        self._cover.setFixedSize(cw, ch)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet(
            "border: 1px solid #3a3a3a; border-radius: 3px;")

        if cover_path and os.path.isfile(cover_path):
            # Scale-to-fill puis crop centré pour garantir un carré 1:1
            px_s = QPixmap(cover_path).scaled(
                cw, ch,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = (px_s.width()  - cw) // 2
            y = (px_s.height() - ch) // 2
            self._cover.setPixmap(px_s.copy(x, y, cw, ch))
        else:
            self._cover.setPixmap(_placeholder_pixmap(title, cw, ch))

        vl.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignHCenter)

        lbl = QLabel(title)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        lbl.setStyleSheet("font-size: 8pt; color: #ccc; background: transparent;")
        lbl.setMaximumHeight(32)
        vl.addWidget(lbl)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            sub.setStyleSheet("font-size: 7pt; color: #777; background: transparent;")
            vl.addWidget(sub)

        vl.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setStyleSheet("background: #2a2a2a; border-radius: 4px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("")
        super().leaveEvent(event)


class CatalogueView(QWidget):
    """3-level catalogue : Auteurs → Séries+standalone → Volumes."""
    book_selected = pyqtSignal(object)
    _COLS = 5

    _CARD_DEFAULT = 150
    _CARD_MIN     = 80
    _CARD_MAX     = 280
    _CARD_STEP    = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._books: list = []
        self._query: str  = ""
        self._level: int  = 0
        self._cur_author: str  = ""
        self._cur_series: str  = ""
        self._cur_series_books: list = []
        self._card_size: int        = self._CARD_DEFAULT
        self._actual_card_size: int = self._CARD_DEFAULT
        self._cols: int             = 5

        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._on_resize_timeout)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        nav = QWidget()
        nav.setFixedHeight(48)
        nav.setStyleSheet("background: #1e1e1e; border-bottom: 1px solid #333;")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(12, 6, 12, 6)
        nl.setSpacing(12)

        self._back_btn = QPushButton("←  Retour")
        self._back_btn.setFlat(True)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setMinimumHeight(34)
        self._back_btn.setStyleSheet(
            "QPushButton {"
            "  color: #4a9eff; font-size: 10pt; font-weight: bold;"
            "  border: 1px solid #2a5a9a; border-radius: 4px;"
            "  padding: 4px 14px; background: #1a2a3a;"
            "}"
            "QPushButton:hover { background: #1e3550; color: #77bbff; }"
            "QPushButton:pressed { background: #152840; }")
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.hide()
        nl.addWidget(self._back_btn)

        sep_nav = QFrame()
        sep_nav.setFrameShape(QFrame.Shape.VLine)
        sep_nav.setStyleSheet("color: #333;")
        sep_nav.hide()
        self._nav_sep = sep_nav
        nl.addWidget(sep_nav)

        self._breadcrumb = QLabel("Auteurs")
        self._breadcrumb.setStyleSheet(
            "color: #bbb; font-size: 10pt; font-family: 'Segoe UI';")
        nl.addWidget(self._breadcrumb)
        nl.addStretch()

        # ── Zoom ──────────────────────────────────────────────────────
        _zoom_btn_style = (
            "QPushButton {"
            "  color: #ccc; font-size: 11pt; font-weight: bold;"
            "  border: 1px solid #444; border-radius: 4px;"
            "  background: #2a2a2a; min-width: 32px; min-height: 28px;"
            "  padding: 0px 4px;"
            "}"
            "QPushButton:hover   { background: #3a3a3a; color: #fff; }"
            "QPushButton:pressed { background: #1a1a1a; }")

        zoom_lbl = QLabel("Zoom :")
        zoom_lbl.setStyleSheet("color: #777; font-size: 8pt;")
        nl.addWidget(zoom_lbl)

        btn_minus = QPushButton("-")
        btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_minus.setStyleSheet(_zoom_btn_style)
        btn_minus.clicked.connect(self._zoom_out)
        nl.addWidget(btn_minus)

        btn_plus = QPushButton("+")
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plus.setStyleSheet(_zoom_btn_style)
        btn_plus.clicked.connect(self._zoom_in)
        nl.addWidget(btn_plus)

        vl.addWidget(nav)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: #1a1a1a; border: none; }")

        self._inner = QWidget()
        self._inner.setStyleSheet("background: #1a1a1a;")
        self._grid = QGridLayout(self._inner)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(16, 16, 16, 16)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll.setWidget(self._inner)
        vl.addWidget(self._scroll, 1)

    # ── Zoom & colonnes dynamiques ──────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        # Premier affichage : width() est maintenant correct, forcer re-rendu
        QTimer.singleShot(0, self._on_resize_timeout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _on_resize_timeout(self):
        prev_size = self._actual_card_size
        prev_cols = self._cols
        self._update_layout()
        if abs(self._actual_card_size - prev_size) > 2 or self._cols != prev_cols:
            self._show_level()

    def _update_layout(self):
        """Calcule cols et taille réelle pour remplir toute la largeur disponible."""
        spacing  = 16
        margins  = 32   # grid contentsMargins (16px × 2)
        # Utiliser la largeur réelle du viewport (exclut la scrollbar)
        w = self._scroll.viewport().width()
        if w <= 50:
            w = self.width()
        if w <= 50:
            p = self.parent()
            while p:
                pw = p.width()
                if pw > 50:
                    w = pw
                    break
                p = p.parent() if callable(getattr(p, 'parent', None)) else None
        if w <= 50:
            return
        available = w - margins
        # Chaque widget carte = card_size + 16 (8px padding interne × 2)
        card_w = self._card_size + 16
        cols   = max(1, (available + spacing) // (card_w + spacing))
        # Taille réelle pour remplir exactement la largeur disponible
        actual_w = (available - spacing * (cols - 1)) // cols
        actual   = max(self._CARD_MIN, actual_w - 16)
        self._cols = cols
        self._actual_card_size = actual

    def _zoom_in(self):
        if self._card_size < self._CARD_MAX:
            self._card_size = min(self._CARD_MAX,
                                  self._card_size + self._CARD_STEP)
            self._update_layout()
            self._show_level()

    def _zoom_out(self):
        if self._card_size > self._CARD_MIN:
            self._card_size = max(self._CARD_MIN,
                                  self._card_size - self._CARD_STEP)
            self._update_layout()
            self._show_level()

    # ── Public API ──────────────────────────────────────────────────────

    def set_books(self, books: list, query: str = ""):
        self._books  = books
        self._query  = query
        self._level  = 0
        self._cur_author = ""
        self._cur_series = ""
        self._show_authors()

    def set_query(self, query: str):
        self._query = query
        self._show_level()

    # ── Navigation ──────────────────────────────────────────────────────

    def _go_back(self):
        if self._level == 2:
            self._level = 1
            self._cur_series = ""
            self._show_author_content()
        else:
            self._level = 0
            self._cur_author = ""
            self._show_authors()

    def _show_level(self):
        if self._level == 0:
            self._show_authors()
        elif self._level == 1:
            self._show_author_content()
        else:
            self._show_series_volumes()

    def _filtered_books(self) -> list:
        if not self._query:
            return self._books
        q = self._query.lower()
        return [b for b in self._books
                if q in b.display_title.lower()
                or q in b.display_author.lower()
                or q in (b.config.series or "").lower()]

    # ── Level 0 : Auteurs ───────────────────────────────────────────────

    def _show_authors(self):
        books = self._filtered_books()
        authors: dict = {}
        for b in books:
            # Regrouper sous l'auteur principal (avant la première virgule)
            primary = _primary_author(b.display_author)
            key = primary.lower()
            if key not in authors:
                authors[key] = {"display": primary, "books": []}
            authors[key]["books"].append(b)

        entries = sorted(authors.values(), key=lambda e: e["display"].lower())
        self._clear_grid()
        self._back_btn.hide()
        self._nav_sep.hide()
        n = len(entries)
        self._breadcrumb.setText(f"Auteurs ({n})")

        for i, entry in enumerate(entries):
            cover_path = next(
                (_author_cover_path(b) for b in entry["books"]
                 if _author_cover_path(b)),
                "")
            nb = len(entry["books"])
            card = _CatalogueCard(entry["display"], cover_path,
                                  subtitle=f"{nb} livre{'s' if nb != 1 else ''}",
                                  card_size=self._actual_card_size)
            author = entry["display"]
            card.clicked.connect(
                lambda checked=False, a=author: self._drill_author(a))
            self._grid.addWidget(card, i // self._cols, i % self._cols)

    def _drill_author(self, author: str):
        self._level = 1
        self._cur_author = author
        self._show_author_content()

    # ── Level 1 : Séries + standalone ──────────────────────────────────

    def _show_author_content(self):
        # Inclure tous les livres dont l'auteur principal correspond
        books = [b for b in self._filtered_books()
                 if _primary_author(b.display_author).strip().lower()
                    == self._cur_author.strip().lower()]

        series: dict   = {}
        standalone: list = []
        for b in books:
            s = (b.config.series or "").strip()
            if s:
                series.setdefault(s, []).append(b)
            else:
                standalone.append(b)

        self._clear_grid()
        self._back_btn.show()
        self._nav_sep.show()
        self._breadcrumb.setText(f"Auteurs  /  {self._cur_author}")

        items: list = []
        for sname in sorted(series):
            sbooks = sorted(series[sname], key=lambda b: _vol_key(b.config.volume))
            cover_path = next(
                (_series_cover_path(b) for b in sbooks if _series_cover_path(b)), "")
            nb = len(sbooks)
            items.append(("series", sname, cover_path, sbooks,
                           f"{nb} tome{'s' if nb != 1 else ''}"))

        for b in sorted(standalone, key=lambda b: b.display_title.lower()):
            items.append(("book", b.display_title, _individual_cover_path(b), b, ""))

        for i, (kind, label, cover_path, data, sub) in enumerate(items):
            card = _CatalogueCard(label, cover_path, subtitle=sub,
                                  card_size=self._actual_card_size)
            if kind == "series":
                card.clicked.connect(
                    lambda checked=False, s=label, bks=data:
                        self._drill_series(s, bks))
            else:
                card.clicked.connect(
                    lambda checked=False, b=data: self.book_selected.emit(b))
            self._grid.addWidget(card, i // self._cols, i % self._cols)

    def _drill_series(self, series: str, books: list):
        self._level = 2
        self._cur_series = series
        self._cur_series_books = books
        self._show_series_volumes()

    # ── Level 2 : Volumes ──────────────────────────────────────────────

    def _show_series_volumes(self):
        books = sorted(self._cur_series_books,
                       key=lambda b: _vol_key(b.config.volume))
        self._clear_grid()
        self._back_btn.show()
        self._nav_sep.show()
        self._breadcrumb.setText(
            f"Auteurs  /  {self._cur_author}  /  {self._cur_series}")

        for i, b in enumerate(books):
            vol = b.config.volume or ""
            sub = f"Tome {vol}" if vol else ""
            card = _CatalogueCard(b.display_title, _individual_cover_path(b),
                                  subtitle=sub, card_size=self._actual_card_size)
            card.clicked.connect(
                lambda checked=False, bk=b: self.book_selected.emit(bk))
            self._grid.addWidget(card, i // self._cols, i % self._cols)

    # ── Helpers ────────────────────────────────────────────────────────

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()


# ── Custom header with native checkbox ────────────────────────────────────


class _CheckHeaderView(QHeaderView):
    """QHeaderView qui dessine une checkbox native Qt dans la colonne 0."""
    check_toggled = pyqtSignal(bool)   # True = tout cocher

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._check_col = 0
        self._checked   = False
        self._partial   = False
        self.setSectionsClickable(True)

    def set_state(self, checked: bool, partial: bool = False):
        if self._checked == checked and self._partial == partial:
            return
        self._checked = checked
        self._partial = partial
        self.viewport().update(
            self.sectionViewportPosition(self._check_col), 0,
            self.sectionSize(self._check_col), self.height())

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex == self._check_col:
            opt = QStyleOptionButton()
            cb = 14
            x = rect.x() + (rect.width()  - cb) // 2
            y = rect.y() + (rect.height() - cb) // 2
            opt.rect = QRect(x, y, cb, cb)
            if self._partial:
                opt.state = (QStyle.StateFlag.State_NoChange
                             | QStyle.StateFlag.State_Enabled)
            elif self._checked:
                opt.state = (QStyle.StateFlag.State_On
                             | QStyle.StateFlag.State_Enabled)
            else:
                opt.state = (QStyle.StateFlag.State_Off
                             | QStyle.StateFlag.State_Enabled)
            self.style().drawPrimitive(
                QStyle.PrimitiveElement.PE_IndicatorCheckBox, opt, painter)
        painter.restore()

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.pos()) == self._check_col:
            self.check_toggled.emit(not self._checked)
            return
        super().mousePressEvent(event)


# ── Library panel ──────────────────────────────────────────────────────────


class LibraryPanel(QWidget):
    scan_requested   = pyqtSignal()
    update_requested = pyqtSignal()
    reset_requested  = pyqtSignal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._books: List[BookEntry]          = []
        self._filtered_books: List[BookEntry] = []
        self._id_to_book: dict                = {}
        self._catalogue_mode: bool            = False
        self._catalogue: CatalogueView        = None  # type: ignore

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._persist_col_widths)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar (scanner + recherche sur une seule ligne) ──────────
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(8)

        # Boutons scanner
        self._scan_btn = QPushButton("⟳  Scanner")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setToolTip(
            "Scan incrémental : ne traite que les nouveaux dossiers / fichiers.\n"
            "Les livres déjà connus sont conservés tels quels.")
        self._scan_btn.setStyleSheet("""
            QPushButton {
                background: #0067c0; color: white; border: none;
                padding: 5px 14px; font-size: 9pt; font-weight: bold;
                font-family: "Segoe UI";
            }
            QPushButton:hover    { background: #0055aa; }
            QPushButton:pressed  { background: #003f88; }
            QPushButton:disabled { background: #444; color: #888; }
        """)
        self._scan_btn.clicked.connect(self.scan_requested)
        bl.addWidget(self._scan_btn)

        update_btn = QPushButton("↻  Update")
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.setToolTip("Recharge depuis l'état sauvegardé (sans scan)")
        update_btn.clicked.connect(self.update_requested)
        bl.addWidget(update_btn)

        reset_btn = QPushButton("↺  Reset cache")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip("Vide le cache ffprobe — le prochain scan re-fingerprint tout")
        reset_btn.clicked.connect(self.reset_requested)
        bl.addWidget(reset_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3a3a3a;")
        bl.addWidget(sep)

        # Recherche
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

        self._hide_complete_cb = QCheckBox("Cacher complets")
        self._hide_complete_cb.setToolTip(
            "Masque les livres dont les méta requises sont renseignées\n"
            "(ou marqués « ignorer la vérif »).")
        saved_hide = bool(self.app.config_manager.app_config.ui_prefs.get(
            HIDE_COMPLETE_KEY, False))
        self._hide_complete_cb.setChecked(saved_hide)
        self._hide_complete_cb.toggled.connect(self._on_hide_complete_toggled)
        bl.addWidget(self._hide_complete_cb)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet("color: #3a3a3a;")
        bl.addWidget(sep3)

        self._cat_btn = QPushButton("⊞  Catalogue")
        self._cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cat_btn.setToolTip("Basculer vers la vue catalogue (auteurs / séries / volumes)")
        self._cat_btn.setCheckable(True)
        self._cat_btn.setStyleSheet("""
            QPushButton {
                background: #333; color: #ccc; border: none;
                padding: 5px 12px; font-size: 9pt;
                font-family: "Segoe UI";
            }
            QPushButton:hover   { background: #3a3a3a; }
            QPushButton:checked { background: #1a4a7a; color: #fff; }
        """)
        self._cat_btn.clicked.connect(self._toggle_catalogue_view)
        bl.addWidget(self._cat_btn)

        bl.addStretch()

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 100)
        self._scan_progress.setValue(0)
        self._scan_progress.setMaximumWidth(160)
        self._scan_progress.setMaximumHeight(10)
        self._scan_progress.setTextVisible(True)
        self._scan_progress.setFormat("%p%")
        self._scan_progress.setStyleSheet(
            "QProgressBar { border: 1px solid #444; border-radius: 4px;"
            " background: #2a2a2a; color: #ccc; font-size: 7pt; }"
            "QProgressBar::chunk { background: #0067c0; border-radius: 3px; }")
        self._scan_progress.hide()
        bl.addWidget(self._scan_progress)

        self._scan_label = QLabel("Aucun scan effectué")
        self._scan_label.setStyleSheet("color: #888; font-size: 9pt;")
        bl.addWidget(self._scan_label)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color: #555; font-size: 9pt;")
        bl.addWidget(self._count_lbl)

        layout.addWidget(bar)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #333;")
        layout.addWidget(sep2)

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

        self._check_header = _CheckHeaderView(Qt.Orientation.Horizontal, self._table)
        self._check_header.setHighlightSections(False)
        self._table.setHorizontalHeader(self._check_header)
        self._check_header.sectionResized.connect(lambda: self._save_timer.start())
        self._check_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._check_header.customContextMenuRequested.connect(self._show_header_menu)
        self._check_header.setSectionsClickable(True)
        self._check_header.sectionClicked.connect(self._on_header_clicked)
        self._check_header.check_toggled.connect(self._on_check_header_toggled)

        self._rebuild_columns()

        # Placeholder initial
        self._table.setItem(0, COL_TITLE, _make_item(
            "Cliquez sur ⟳ Scanner pour charger la bibliothèque", color="#555"))
        self._table.item(0, COL_TITLE).setFlags(Qt.ItemFlag.ItemIsEnabled)

        self._catalogue = CatalogueView()
        self._catalogue.book_selected.connect(self.app.on_book_selected)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._table)      # index 0 : liste
        self._stack.addWidget(self._catalogue)  # index 1 : catalogue
        layout.addWidget(self._stack, 1)

    # ── Toggle vue catalogue ──────────────────────────────────────────

    def _toggle_catalogue_view(self):
        self._catalogue_mode = self._cat_btn.isChecked()
        if self._catalogue_mode:
            query = self._search.text().lower().strip()
            self._catalogue.set_books(self._books, query)
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(0)

    # ── Public API ─────────────────────────────────────────────────────

    def set_scanning(self, scanning: bool):
        self._scan_btn.setEnabled(not scanning)
        if scanning:
            self._scan_progress.show()
            self._scan_progress.setValue(0)
        else:
            self._scan_progress.hide()
            self._scan_btn.setEnabled(True)

    def set_scan_progress(self, pct: int, msg: str):
        self._scan_progress.setValue(pct)
        self._scan_label.setText(msg[:70])

    def set_scan_label(self, text: str, color: str = "#888"):
        self._scan_label.setText(text)
        self._scan_label.setStyleSheet(f"color: {color}; font-size: 9pt;")

    def populate(self, books: List[BookEntry]):
        self._books      = books
        self._id_to_book = {b.id: b for b in books}
        if self._catalogue is not None:
            query = self._search.text().lower().strip()
            self._catalogue.set_books(books, query)
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
                status_item = _make_item(icon, True, color)
                if book and book.source_is_output:
                    status_item.setToolTip("Source originale introuvable — seul le fichier de sortie M4B subsiste.\n"
                                           "La re-conversion M4B est bloquée ; utilisez 'Méta' pour mettre à jour les tags.")
                self._table.setItem(row, COL_STATUS, status_item)
                self._populating = False
                break

    def refresh_queue_checkboxes(self):
        pass

    # ── Internal ───────────────────────────────────────────────────────

    def _rebuild_columns(self):
        headers = (["", "Titre", "Auteur"] + EXTRA_COLS
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

                status_item = _make_item(icon, True, color)
                if book.source_is_output:
                    status_item.setToolTip("Source originale introuvable — seul le fichier de sortie M4B subsiste.\n"
                                           "La re-conversion M4B est bloquée ; utilisez 'Méta' pour mettre à jour les tags.")
                self._table.setItem(row, COL_STATUS, status_item)

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
        self._update_check_header()
        n_visible = len(books)
        self._count_lbl.setText(f"{n_visible} livre{'s' if n_visible != 1 else ''}")

        if self._catalogue_mode and self._catalogue is not None:
            self._catalogue.set_query(query)

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

    def _on_header_clicked(self, section: int):
        pass  # col 0 handled by _check_header.check_toggled; other cols unused

    def _on_check_header_toggled(self, checked: bool):
        target = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb:
                    cb.setCheckState(target)
        finally:
            self._populating = False
        self._update_check_header()

    def _update_check_header(self):
        n = self._table.rowCount()
        checked = sum(
            1 for r in range(n)
            if self._table.item(r, COL_CHECK) and
            self._table.item(r, COL_CHECK).checkState() == Qt.CheckState.Checked
        ) if n > 0 else 0
        self._check_header.set_state(checked == n and n > 0, 0 < checked < n)

    def _check_all(self):
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb:
                    cb.setCheckState(Qt.CheckState.Checked)
        finally:
            self._populating = False
        self._update_check_header()

    def _uncheck_all(self):
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb:
                    cb.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._populating = False
        self._update_check_header()

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
            meta_with_m4b = [b for b in books if b.output_m4b_path]
            if meta_with_m4b:
                menu.addAction(f"🏷  Mettre à jour les tags M4B ({len(meta_with_m4b)} livres)").triggered.connect(
                    lambda checked=False, bl=meta_with_m4b: [self.app.update_book_metadata(b) for b in bl])
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
            if book.output_m4b_path:
                menu.addAction("🏷  Mettre à jour les tags M4B").triggered.connect(
                    lambda checked=False, b=book: self.app.update_book_metadata(b))
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
