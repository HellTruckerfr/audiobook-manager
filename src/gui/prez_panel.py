import os
import urllib.request
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QFrame, QTextBrowser, QComboBox,
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap, QTextDocument

from ..models import BookEntry
from ..bbcode import generate_prez, bbcode_to_html


class _UploadThread(QThread):
    done   = pyqtSignal(str)   # URL on success
    failed = pyqtSignal(str)   # error message

    def __init__(self, file_path: str):
        super().__init__()
        self._path = file_path

    def run(self):
        from ..uploader import upload_to_catbox
        try:
            url = upload_to_catbox(self._path)
            self.done.emit(url)
        except Exception as e:
            self.failed.emit(str(e))


class _PreviewBrowser(QTextBrowser):
    """QTextBrowser qui charge les images http(s) distantes via urllib."""

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
        self._upload_thread: Optional[_UploadThread] = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(8)

        # Format M4B / MP3
        bl.addWidget(QLabel("Format :"))
        self._fmt_cb = QComboBox()
        self._fmt_cb.addItem("M4B", "m4b")
        self._fmt_cb.addItem("MP3", "mp3")
        self._fmt_cb.setMaximumWidth(70)
        self._fmt_cb.currentIndexChanged.connect(self._regenerate)
        bl.addWidget(self._fmt_cb)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #444;")
        bl.addWidget(sep)

        # Note
        bl.addWidget(QLabel("Note :"))
        self._rating_le = QLineEdit()
        self._rating_le.setPlaceholderText("ex: 9.6")
        self._rating_le.setMaximumWidth(72)
        self._rating_le.setToolTip("Note sur 10 (optionnel) — non sauvegardée")
        self._rating_le.textChanged.connect(self._regenerate)
        bl.addWidget(self._rating_le)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #444;")
        bl.addWidget(sep2)

        # Cover URL + upload
        bl.addWidget(QLabel("Cover URL :"))
        self._cover_url_le = QLineEdit()
        self._cover_url_le.setPlaceholderText("URL hébergée (catbox.moe…)")
        self._cover_url_le.setToolTip(
            "URL publique de la cover pour [img].\n"
            "Sauvegardée dans le livre.")
        self._cover_url_le.textChanged.connect(self._on_cover_url_changed)
        bl.addWidget(self._cover_url_le, 1)

        self._upload_btn = QPushButton("📤 Catbox")
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setToolTip(
            "Upload la cover locale (config.cover_path) sur catbox.moe\n"
            "et remplit automatiquement l'URL ci-contre.")
        self._upload_btn.clicked.connect(self._upload_cover)
        bl.addWidget(self._upload_btn)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet("color: #444;")
        bl.addWidget(sep3)

        copy_btn = QPushButton("📋 Copier")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet("""
            QPushButton {
                background: #0067c0; color: white; border: none;
                padding: 5px 12px; font-size: 9pt; font-weight: bold;
            }
            QPushButton:hover   { background: #0055aa; }
            QPushButton:pressed { background: #003f88; }
        """)
        copy_btn.clicked.connect(self._copy)
        bl.addWidget(copy_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size: 9pt;")
        bl.addWidget(self._status_lbl)

        layout.addWidget(bar)

        hline = QFrame()
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setStyleSheet("color: #333;")
        layout.addWidget(hline)

        # ── Splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #333; }")

        # Gauche : liste de livres
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(4)
        ll.addWidget(QLabel("Livres avec sortie disponible"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        ll.addWidget(self._list, 1)
        splitter.addWidget(left)

        # Droite : onglets BBCode / Aperçu
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab { padding: 5px 14px; }"
            "QTabBar::tab:selected { color: white; }")

        self._bbcode_edit = QTextEdit()
        self._bbcode_edit.setReadOnly(True)
        self._bbcode_edit.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 9pt;"
            " background: #1a1a1a; color: #ddd; border: none; }")
        self._tabs.addTab(self._bbcode_edit, "BBCode")

        self._preview = _PreviewBrowser()
        self._preview.setOpenLinks(False)
        self._preview.setStyleSheet(
            "QTextBrowser { background: #1e1e1e; border: none; }")
        self._tabs.addTab(self._preview, "Aperçu")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        rl.addWidget(self._tabs, 1)

        self._warn_lbl = QLabel("")
        self._warn_lbl.setStyleSheet("color: #e8a020; font-size: 8.5pt;")
        self._warn_lbl.setWordWrap(True)
        rl.addWidget(self._warn_lbl)

        splitter.addWidget(right)
        splitter.setSizes([300, 880])
        layout.addWidget(splitter, 1)

    # ── Public API ────────────────────────────────────────────────────

    def refresh_books(self):
        self._books = [
            b for b in (self.app.scanner.load_last_books() or [])
            if b.output_m4b_info is not None or b.output_mp3_info is not None
        ]
        self._fill_list()

    # ── Internals ─────────────────────────────────────────────────────

    def _fill_list(self):
        prev_id = self._current.id if self._current else None
        self._list.blockSignals(True)
        self._list.clear()
        for book in self._books:
            author = book.display_author or "?"
            title  = book.display_title  or "?"
            flags  = []
            if book.output_m4b_info:
                flags.append("M4B")
            if book.output_mp3_info:
                flags.append("MP3")
            badge = f"  [{'/'.join(flags)}]" if flags else ""
            item = QListWidgetItem(f"{author} — {title}{badge}")
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
        # Auto-select format based on what's available
        fmt = self._fmt_cb.currentData()
        if fmt == "m4b" and not self._current.output_m4b_info and self._current.output_mp3_info:
            self._fmt_cb.setCurrentIndex(1)
        elif fmt == "mp3" and not self._current.output_mp3_info and self._current.output_m4b_info:
            self._fmt_cb.setCurrentIndex(0)
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
        fmt     = self._fmt_cb.currentData()
        bbcode  = generate_prez(self._current, tracker_name=tracker,
                                rating=rating, fmt=fmt)
        self._bbcode_edit.setPlainText(bbcode)

        if self._tabs.currentIndex() == 1:
            self._update_preview(bbcode)

        # Warnings
        warn = []
        if not self._current.config.cover_url:
            warn.append("⚠ Pas d'URL de cover.")
        info = (self._current.output_m4b_info if fmt == "m4b"
                else self._current.output_mp3_info)
        if not info:
            warn.append(f"⚠ Pas d'infos {fmt.upper()} — codec/bitrate/taille omis.")
        self._warn_lbl.setText("  ".join(warn))
        self._status_lbl.setText("")

    def _on_tab_changed(self, index: int):
        if index == 1:
            self._update_preview(self._bbcode_edit.toPlainText())

    def _update_preview(self, bbcode: str):
        if not bbcode:
            self._preview.clear()
            return
        self._preview.setHtml(bbcode_to_html(bbcode))

    def _copy(self):
        text = self._bbcode_edit.toPlainText()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self._status_lbl.setStyleSheet("color: #57cc7a; font-size: 9pt;")
        self._status_lbl.setText("✓ Copié !")

    # ── Upload catbox ─────────────────────────────────────────────────

    def _upload_cover(self):
        if not self._current:
            return
        cover = self._current.config.cover_path
        if not cover or not os.path.exists(cover):
            self._status_lbl.setStyleSheet("color: #e8a020; font-size: 9pt;")
            self._status_lbl.setText("⚠ Aucune cover locale (renseignez-la dans l'éditeur).")
            return
        self._upload_btn.setEnabled(False)
        self._upload_btn.setText("…")
        self._status_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        self._status_lbl.setText("Upload en cours…")

        self._upload_thread = _UploadThread(cover)
        self._upload_thread.done.connect(self._on_upload_done)
        self._upload_thread.failed.connect(self._on_upload_failed)
        self._upload_thread.start()

    def _on_upload_done(self, url: str):
        self._upload_btn.setEnabled(True)
        self._upload_btn.setText("📤 Catbox")
        self._cover_url_le.setText(url)   # déclenche _on_cover_url_changed → save
        self._status_lbl.setStyleSheet("color: #57cc7a; font-size: 9pt;")
        self._status_lbl.setText(f"✓ Uploadé : {url}")

    def _on_upload_failed(self, error: str):
        self._upload_btn.setEnabled(True)
        self._upload_btn.setText("📤 Catbox")
        self._status_lbl.setStyleSheet("color: #e05555; font-size: 9pt;")
        self._status_lbl.setText(f"✗ Erreur upload : {error}")
