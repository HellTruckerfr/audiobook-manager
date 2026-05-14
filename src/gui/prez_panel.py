import urllib.request
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QFrame, QTextBrowser,
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap, QTextDocument

from ..models import BookEntry
from ..bbcode import generate_prez, bbcode_to_html


class _ImageLoader(QThread):
    """Télécharge une image distante en arrière-plan et renvoie ses bytes."""
    done = pyqtSignal(bytes)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            with urllib.request.urlopen(self._url, timeout=8) as r:
                self.done.emit(r.read())
        except Exception:
            self.done.emit(b"")


class _PreviewBrowser(QTextBrowser):
    """QTextBrowser qui charge les images http(s) via urllib."""

    def loadResource(self, resource_type: int, url: QUrl):
        if resource_type == QTextDocument.ResourceType.ImageResource.value:
            scheme = url.scheme()
            if scheme in ("http", "https"):
                try:
                    req = urllib.request.Request(
                        url.toString(),
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    with urllib.request.urlopen(req, timeout=8) as r:
                        data = r.read()
                    pix = QPixmap()
                    pix.loadFromData(data)
                    return pix
                except Exception:
                    pass
        return super().loadResource(resource_type, url)


class PrezPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._books: List[BookEntry] = []
        self._current: Optional[BookEntry] = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(10)

        lbl = QLabel("Note :")
        lbl.setStyleSheet("color: #ccc;")
        bl.addWidget(lbl)

        self._rating_le = QLineEdit()
        self._rating_le.setPlaceholderText("ex: 9.6")
        self._rating_le.setMaximumWidth(80)
        self._rating_le.setToolTip("Note sur 10 (optionnel) — non sauvegardée")
        self._rating_le.textChanged.connect(self._regenerate)
        bl.addWidget(self._rating_le)

        self._cover_url_le = QLineEdit()
        self._cover_url_le.setPlaceholderText("URL de la cover (hébergement externe)…")
        self._cover_url_le.setToolTip(
            "URL publique de la cover pour la balise [img].\n"
            "Sauvegardée dans le livre. Laisser vide pour omettre [img].")
        self._cover_url_le.textChanged.connect(self._on_cover_url_changed)
        bl.addWidget(self._cover_url_le, 1)

        copy_btn = QPushButton("📋  Copier BBCode")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet("""
            QPushButton {
                background: #0067c0; color: white; border: none;
                padding: 5px 14px; font-size: 9pt; font-weight: bold;
            }
            QPushButton:hover   { background: #0055aa; }
            QPushButton:pressed { background: #003f88; }
        """)
        copy_btn.clicked.connect(self._copy)
        bl.addWidget(copy_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #57cc7a; font-size: 9pt;")
        bl.addWidget(self._status_lbl)

        layout.addWidget(bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #333; }")

        # ── Gauche : liste de livres ──
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(4)
        ll.addWidget(QLabel("Livres"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        ll.addWidget(self._list, 1)
        splitter.addWidget(left)

        # ── Droite : onglets BBCode / Aperçu ──
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabBar::tab { padding: 5px 14px; }
            QTabBar::tab:selected { color: white; }
        """)

        # Onglet BBCode
        self._bbcode_edit = QTextEdit()
        self._bbcode_edit.setReadOnly(True)
        self._bbcode_edit.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 9pt;"
            " background: #1a1a1a; color: #ddd; border: none; }")
        tabs.addTab(self._bbcode_edit, "BBCode")

        # Onglet Aperçu
        self._preview = _PreviewBrowser()
        self._preview.setOpenLinks(False)
        self._preview.setStyleSheet(
            "QTextBrowser { background: #1e1e1e; border: none; }")
        tabs.addTab(self._preview, "Aperçu")

        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs

        rl.addWidget(tabs, 1)

        self._warn_lbl = QLabel("")
        self._warn_lbl.setStyleSheet("color: #e8a020; font-size: 8.5pt;")
        self._warn_lbl.setWordWrap(True)
        rl.addWidget(self._warn_lbl)

        splitter.addWidget(right)
        splitter.setSizes([280, 900])
        layout.addWidget(splitter, 1)

    # ── Public API ────────────────────────────────────────────────────

    def refresh_books(self):
        self._books = list(self.app.scanner.load_last_books() or [])
        self._fill_list()

    # ── Internals ─────────────────────────────────────────────────────

    def _fill_list(self):
        prev_id = self._current.id if self._current else None
        self._list.blockSignals(True)
        self._list.clear()
        for book in self._books:
            author = book.display_author or "?"
            title  = book.display_title  or "?"
            item = QListWidgetItem(f"{author} — {title}")
            item.setData(Qt.ItemDataRole.UserRole, book.id)
            self._list.addItem(item)
        self._list.blockSignals(False)
        if prev_id:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == prev_id:
                    self._list.setCurrentRow(i)
                    return
        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._books):
            self._current = None
            self._bbcode_edit.clear()
            self._preview.clear()
            return
        self._current = self._books[row]
        self._cover_url_le.blockSignals(True)
        self._cover_url_le.setText(self._current.config.cover_url)
        self._cover_url_le.blockSignals(False)
        self._regenerate()

    def _on_cover_url_changed(self, url: str):
        if self._current:
            self._current.config.cover_url = url.strip()
            self.app.config_manager.save_book(self._current)
        self._regenerate()

    def _regenerate(self):
        if not self._current:
            self._bbcode_edit.clear()
            self._preview.clear()
            return
        tracker = self.app.config_manager.app_config.tracker_name or "La Cale"
        rating  = self._rating_le.text().strip()
        bbcode  = generate_prez(self._current, tracker_name=tracker, rating=rating)
        self._bbcode_edit.setPlainText(bbcode)

        if self._tabs.currentIndex() == 1:
            self._update_preview(bbcode)

        warn = []
        if not self._current.config.cover_url:
            warn.append("⚠ Pas d'URL de cover — renseignez-la ci-dessus.")
        if not self._current.output_m4b_info:
            warn.append("⚠ Pas d'infos M4B — codec/bitrate/taille omis.")
        self._warn_lbl.setText("  ".join(warn))
        self._status_lbl.setText("")

    def _on_tab_changed(self, index: int):
        if index == 1:
            self._update_preview(self._bbcode_edit.toPlainText())

    def _update_preview(self, bbcode: str):
        if not bbcode:
            self._preview.clear()
            return
        html = bbcode_to_html(bbcode)
        self._preview.setHtml(html)

    def _copy(self):
        text = self._bbcode_edit.toPlainText()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self._status_lbl.setText("✓ Copié !")
