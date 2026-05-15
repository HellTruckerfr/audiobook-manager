import sys
import os
import ctypes
from typing import List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QPushButton, QLabel, QStackedWidget, QProgressBar,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QIcon, QPainter

from ..config_manager import ConfigManager
from ..scanner import Scanner
from ..converter import Converter
from ..models import BookEntry
from .library_panel import LibraryPanel
from .editor_panel import EditorPanel
from .queue_panel import QueuePanel
from .console_panel import ConsolePanel
from .scene_copy_panel import SceneCopyPanel
from .prez_panel import PrezPanel
from .settings_dialog import SettingsDialog
from .referential_panel import ReferentialPanel
from .theme import DARK_STYLESHEET

def _auto_icon(path: str) -> QIcon:
    return QIcon(path)


SIDEBAR_W           = 200
SIDEBAR_W_COLLAPSED = 52

NAV_BASE = """
QPushButton {{
    background: {bg};
    color: {fg};
    text-align: left;
    padding: 11px 16px;
    border: none;
    font-size: 10pt;
    font-family: "Segoe UI";
    border-radius: 0;
}}
QPushButton:hover {{ background: {hover}; }}
"""

NAV_BASE_ICON = """
QPushButton {{
    background: {bg};
    color: {fg};
    text-align: center;
    padding: 11px 0px;
    border: none;
    font-size: 14pt;
    border-radius: 0;
}}
QPushButton:hover {{ background: {hover}; }}
"""


class _ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ScanThread(QThread):
    progress = pyqtSignal(int, int, str)   # (current, total, message)
    finished = pyqtSignal(list)

    def __init__(self, scanner):
        super().__init__()
        self._scanner = scanner

    def run(self):
        try:
            books = self._scanner.scan_all(progress_cb=self.progress.emit)
        except Exception:
            books = []
        self.finished.emit(books)


class AudiobookManagerApp:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.config_manager = ConfigManager(base_dir)
        self.config_manager.load()
        self.scanner   = Scanner(self.config_manager)
        self.converter = Converter(self.config_manager)

        self._qt_app = QApplication(sys.argv)
        self._apply_theme()

        self.window = QMainWindow()
        self.window.setWindowTitle("Audiobook Manager — HellTrucker")
        self.window.resize(1300, 800)
        self.window.setMinimumSize(900, 580)
        self.window.setCentralWidget(self._build_splash_widget())
        self.window.show()
        self._set_dark_titlebar()
        QApplication.processEvents()

        self._build_ui()
        self._set_dark_titlebar()
        self._auto_load_library()
        self._qt_app.aboutToQuit.connect(self._on_app_quit)

    # ── Splash screen ──────────────────────────────────────────────────────

    def _build_splash_widget(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: #1a1a1a;")
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(0)

        # Icône
        _ico = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons", "audiobook-manager.ico")
        icon_pix = QIcon(_ico).pixmap(QSize(96, 96))
        if not icon_pix.isNull():
            lbl_icon = QLabel()
            lbl_icon.setPixmap(icon_pix)
            lbl_icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl_icon.setStyleSheet("background: transparent; padding-bottom: 16px;")
            layout.addWidget(lbl_icon)

        # Titre
        lbl_title = QLabel("Audiobook Manager")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl_title.setStyleSheet(
            "color: #ffffff; font-size: 22pt; font-weight: bold;"
            " font-family: 'Segoe UI'; background: transparent;")
        layout.addWidget(lbl_title)

        # Sous-titre
        lbl_sub = QLabel("HellTrucker")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl_sub.setStyleSheet(
            "color: #666666; font-size: 10pt; font-family: 'Segoe UI';"
            " background: transparent; padding-bottom: 24px;")
        layout.addWidget(lbl_sub)

        # Ligne de séparation
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedWidth(200)
        sep.setStyleSheet("color: #2e2e2e; background: #2e2e2e;")
        layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignHCenter)

        # Texte chargement
        lbl_load = QLabel("Chargement…")
        lbl_load.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl_load.setStyleSheet(
            "color: #444444; font-size: 9pt; font-family: 'Segoe UI';"
            " background: transparent; padding-top: 12px;")
        layout.addWidget(lbl_load)

        return widget

    # ── Thème ──────────────────────────────────────────────────────────────

    def _apply_theme(self):
        self._qt_app.setStyleSheet(DARK_STYLESHEET)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,          QColor("#202020"))
        palette.setColor(QPalette.ColorRole.WindowText,      QColor("#f3f3f3"))
        palette.setColor(QPalette.ColorRole.Base,            QColor("#1e1e1e"))
        palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#242424"))
        palette.setColor(QPalette.ColorRole.Text,            QColor("#f3f3f3"))
        palette.setColor(QPalette.ColorRole.Button,          QColor("#383838"))
        palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#f3f3f3"))
        palette.setColor(QPalette.ColorRole.Highlight,       QColor("#0067c0"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Link,            QColor("#4fc3f7"))
        palette.setColor(QPalette.ColorRole.Mid,             QColor("#3a3a3a"))
        palette.setColor(QPalette.ColorRole.Dark,            QColor("#1a1a1a"))
        palette.setColor(QPalette.ColorRole.Shadow,          QColor("#111111"))
        self._qt_app.setPalette(palette)

    def _set_dark_titlebar(self):
        try:
            hwnd = int(self.window.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    # ── Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.window.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._pages: dict    = {}
        self._nav_btns: dict = {}

        layout.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        self._build_library_page()
        self._build_editor_page()
        self._build_queue_page()
        self._build_scene_copy_page()
        self._build_prez_page()
        self._build_console_page()
        self._build_referential_page()

        self.queue_panel.jobs_changed.connect(self._on_queue_changed)

        self._show_page("library")

    def _build_scene_copy_page(self):
        self.scene_copy_panel = SceneCopyPanel(self)
        self._pages["scene_copy"] = self.scene_copy_panel
        self._stack.addWidget(self.scene_copy_panel)

    def _build_prez_page(self):
        self.prez_panel = PrezPanel(self)
        self._pages["prez"] = self.prez_panel
        self._stack.addWidget(self.prez_panel)

    def _on_queue_changed(self):
        self.library_panel.refresh_queue_checkboxes()
        self.editor_panel.refresh_queue_state()

    def _build_sidebar(self) -> QFrame:
        self._sidebar_expanded = True
        self._sidebar_nav_items    = []   # (page_id, icon, label, btn)
        self._sidebar_section_lbls = []   # QLabel section headers

        _icons = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons")
        self._nav_icon_paths = {
            "library":     os.path.join(_icons, "Bibliothèque.ico"),
            "editor":      os.path.join(_icons, "editeur.ico"),
            "queue":       os.path.join(_icons, "Conversion.ico"),
            "scene_copy":  os.path.join(_icons, "copie scene.ico"),
            "prez":        os.path.join(_icons, "presentation.ico"),
            "referential": os.path.join(_icons, "referentiel.ico"),
            "console":     os.path.join(_icons, "terminal.ico"),
        }

        sb = QFrame()
        sb.setFixedWidth(SIDEBAR_W)
        sb.setObjectName("Sidebar")
        sb.setStyleSheet("""
            QFrame#Sidebar {
                background: #1a1a1a;
                border-right: 1px solid #333;
            }
        """)
        self._sidebar = sb

        layout = QVBoxLayout(sb)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header : logo + toggle ──
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 16, 0, 12)
        hl.setSpacing(3)
        hl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._app_icon = QIcon(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons", "audiobook-manager.ico"))

        self._lbl_icon = _ClickableLabel()
        self._lbl_icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._lbl_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_icon.setToolTip("Réduire / agrandir la sidebar")
        self._lbl_icon.clicked.connect(self._toggle_sidebar)
        self._lbl_icon.setStyleSheet("background:transparent; padding:4px;")
        self._set_icon_pixmap(96)
        hl.addWidget(self._lbl_icon)

        self._lbl_name = QLabel("Audiobook Manager")
        self._lbl_name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._lbl_name.setStyleSheet("color:#f3f3f3; font-size:10pt; font-weight:bold; background:transparent;")
        hl.addWidget(self._lbl_name)

        self._lbl_user = QLabel("HellTrucker")
        self._lbl_user.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._lbl_user.setStyleSheet("color:#888; font-size:8pt; background:transparent;")
        hl.addWidget(self._lbl_user)

        layout.addWidget(header)
        layout.addWidget(self._hline())

        TOP_ITEMS = [
            "Édition",
            ("library",      "🔍", "Bibliothèque"),
            ("editor",       "✏",  "Éditeur"),
            ("queue",        "▶",  "Conversion"),
            "Scène",
            ("scene_copy",   "📋", "Copie scène"),
            ("prez",         "📰", "Présentation"),
        ]

        BOTTOM_ITEMS = [
            "Outils",
            ("referential",  "📚", "Référentiel"),
            ("console",      "🖥", "Console"),
        ]

        for item in TOP_ITEMS:
            self._add_nav_item(layout, item)

        layout.addStretch()

        for item in BOTTOM_ITEMS:
            self._add_nav_item(layout, item)

        layout.addWidget(self._hline())

        self._settings_btn = QPushButton("   Paramètres")
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setIcon(_auto_icon(os.path.join(_icons, "parametre.ico")))
        self._settings_btn.setIconSize(QSize(32, 32))
        self._settings_btn.setStyleSheet(NAV_BASE.format(bg="transparent", fg="#888",
                                                         hover="rgba(255,255,255,0.06)"))
        self._settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(self._settings_btn)

        return sb

    def _add_nav_item(self, layout, item):
        if isinstance(item, str):
            lbl = QLabel(item.upper())
            lbl.setStyleSheet(
                "color: #555; font-size: 7.5pt; font-weight: bold;"
                " padding: 10px 16px 2px 16px; background: transparent;")
            layout.addWidget(lbl)
            self._sidebar_section_lbls.append(lbl)
            return
        page_id, icon, label = item
        icon_path = self._nav_icon_paths.get(page_id)
        if icon_path:
            btn = QPushButton(f"   {label}")
            btn.setIcon(_auto_icon(icon_path))
            btn.setIconSize(QSize(32, 32))
        else:
            btn = QPushButton(f"  {icon}  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(NAV_BASE.format(bg="transparent", fg="#ccc",
                                          hover="rgba(255,255,255,0.06)"))
        btn.clicked.connect(lambda _, p=page_id: self._show_page(p))
        layout.addWidget(btn)
        self._nav_btns[page_id] = btn
        self._sidebar_nav_items.append((page_id, icon, label, btn))

    def _set_icon_pixmap(self, size: int):
        if self._app_icon.isNull():
            self._lbl_icon.setText("🎧")
            self._lbl_icon.setStyleSheet(
                f"color:#0067c0; font-size:{'26' if size >= 40 else '20'}pt;"
                " background:transparent; padding:4px;")
        else:
            ratio = self._lbl_icon.devicePixelRatioF()
            pix = self._app_icon.pixmap(QSize(int(size * ratio), int(size * ratio)))
            pix.setDevicePixelRatio(ratio)
            self._lbl_icon.setPixmap(pix)

    def _toggle_sidebar(self):
        self._sidebar_expanded = not self._sidebar_expanded
        exp = self._sidebar_expanded

        self._sidebar.setFixedWidth(SIDEBAR_W if exp else SIDEBAR_W_COLLAPSED)
        self._lbl_name.setVisible(exp)
        self._lbl_user.setVisible(exp)
        self._set_icon_pixmap(96 if exp else 64)

        for lbl in self._sidebar_section_lbls:
            lbl.setVisible(exp)

        for page_id, icon, label, btn in self._sidebar_nav_items:
            has_png = page_id in self._nav_icon_paths
            active  = (self._stack.currentWidget() == self._pages.get(page_id))
            if exp:
                if has_png:
                    if page_id == "queue":
                        current_text = btn.text()
                        badge = ""
                        if "(" in current_text:
                            badge = " " + current_text[current_text.index("("):]
                        btn.setText(f"   {label}{badge}")
                    else:
                        btn.setText(f"   {label}")
                else:
                    if page_id == "queue":
                        current_text = btn.text()
                        badge = ""
                        if "(" in current_text:
                            badge = " " + current_text[current_text.index("("):]
                        btn.setText(f"  {icon}  {label}{badge}")
                    else:
                        btn.setText(f"  {icon}  {label}")
                btn.setStyleSheet(
                    NAV_BASE.format(
                        bg="#0067c0" if active else "transparent",
                        fg="white"   if active else "#ccc",
                        hover="#0055aa" if active else "rgba(255,255,255,0.06)",
                    )
                )
            else:
                btn.setText("" if has_png else icon)
                btn.setStyleSheet(
                    NAV_BASE_ICON.format(
                        bg="#0067c0" if active else "transparent",
                        fg="white"   if active else "#ccc",
                        hover="#0055aa" if active else "rgba(255,255,255,0.06)",
                    )
                )

        if exp:
            self._settings_btn.setText("   Paramètres")
            self._settings_btn.setStyleSheet(NAV_BASE.format(
                bg="transparent", fg="#888", hover="rgba(255,255,255,0.06)"))
        else:
            self._settings_btn.setText("")
            self._settings_btn.setStyleSheet(NAV_BASE_ICON.format(
                bg="transparent", fg="#666", hover="rgba(255,255,255,0.06)"))

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        return line

    def _show_page(self, page_id: str):
        if page_id in self._pages:
            self._stack.setCurrentWidget(self._pages[page_id])
            if page_id == "scene_copy":
                self.scene_copy_panel.refresh_books()
            elif page_id == "prez":
                self.prez_panel.refresh_books()
            elif page_id == "referential":
                self.referential_panel.refresh()
        exp = self._sidebar_expanded
        base = NAV_BASE if exp else NAV_BASE_ICON
        for pid, icon, label, btn in self._sidebar_nav_items:
            if pid == page_id:
                btn.setStyleSheet(base.format(bg="#0067c0", fg="white", hover="#0055aa"))
            else:
                btn.setStyleSheet(base.format(bg="transparent", fg="#ccc",
                                              hover="rgba(255,255,255,0.06)"))

    # ── Page 1 : Bibliothèque ──────────────────────────────────────────────

    def _build_library_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self.library_panel = LibraryPanel(self)
        self.library_panel.scan_requested.connect(self._start_scan)
        self.library_panel.update_requested.connect(self._update_library)
        self.library_panel.reset_requested.connect(self._reset_cache)
        vl.addWidget(self.library_panel, 1)

        self._pages["library"] = page
        self._stack.addWidget(page)

    # ── Page 2 : Éditeur ──────────────────────────────────────────────────

    def _build_editor_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self.editor_panel = EditorPanel(self)
        self.editor_panel.back_requested.connect(lambda: self._show_page("library"))
        vl.addWidget(self.editor_panel, 1)

        self._pages["editor"] = page
        self._stack.addWidget(page)

    # ── Page 3 : File de conversion ────────────────────────────────────────

    def _build_queue_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Header
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 5, 8, 5)

        lbl = QLabel("File de conversion")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hl.addWidget(lbl)
        hl.addStretch()

        vl.addWidget(header)
        vl.addWidget(self._hline())

        self.queue_panel = QueuePanel(self)
        self.queue_panel.pending_changed.connect(self._update_queue_badge)
        vl.addWidget(self.queue_panel, 1)

        self._pages["queue"] = page
        self._stack.addWidget(page)

    def _update_queue_badge(self, pending: int):
        btn = self._nav_btns.get("queue")
        if btn is None:
            return
        if self._sidebar_expanded:
            btn.setText(f"   Conversion  ({pending})" if pending > 0
                        else "   Conversion")
        # In collapsed mode the button shows only the icon — badge not shown

    # ── Page 4 : Console ──────────────────────────────────────────────────

    def _build_console_page(self):
        self.console_panel = ConsolePanel()
        self._pages["console"] = self.console_panel
        self._stack.addWidget(self.console_panel)

    def _build_referential_page(self):
        self.referential_panel = ReferentialPanel(self)
        self._pages["referential"] = self.referential_panel
        self._stack.addWidget(self.referential_panel)

    # ── Actions ────────────────────────────────────────────────────────────

    def _update_library(self):
        books = self.scanner.load_last_books()
        self.library_panel.populate(books)
        n = len(books)
        self.library_panel.set_scan_label(
            f"{n} livre{'s' if n != 1 else ''} — mis à jour", "#57cc7a")

    def _auto_load_library(self):
        books = self.scanner.load_last_books()
        if books:
            self.library_panel.populate(books)
            n = len(books)
            self.library_panel.set_scan_label(
                f"{n} livre{'s' if n != 1 else ''} — cliquez Scanner pour mettre à jour")

    def _open_settings(self):
        SettingsDialog(self.window, self.config_manager).exec()

    def _reset_cache(self):
        reply = QMessageBox.question(
            self.window, "Vider le cache",
            "Vider le cache de fingerprints / ffprobe ?\n\n"
            "✓ Conservés : fusions manuelles, méta saisies, liste des livres.\n"
            "Le prochain Scanner re-fingerprint tous les fichiers et "
            "détecte les changements.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.reset_scan_cache()
            self.library_panel.set_scan_label("Cache vidé — cliquez Scanner", "#e8a020")

    def _start_scan(self):
        if not self.config_manager.app_config.source_folders:
            QMessageBox.information(
                self.window, "Aucun dossier configuré",
                "Configurez d'abord les dossiers sources dans Paramètres.")
            self._open_settings()
            return

        self.library_panel.set_scanning(True)
        self.library_panel.set_scan_label("Scan en cours…", "#e8a020")

        self._scan_thread = _ScanThread(self.scanner)
        self._scan_thread.progress.connect(self._on_scan_progress)
        self._scan_thread.finished.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_progress(self, current: int, total: int, msg: str):
        pct = int(current / total * 100) if total > 0 else 0
        self.library_panel.set_scan_progress(pct, msg)

    def _on_scan_done(self, books: List[BookEntry]):
        self.library_panel.set_scanning(False)
        self.library_panel.populate(books)
        n = len(books)
        self.library_panel.set_scan_label(
            f"{n} livre{'s' if n != 1 else ''} trouvé{'s' if n != 1 else ''}", "#57cc7a")

    def on_book_selected(self, book: BookEntry):
        self.editor_panel.load_book(book)
        self._show_page("editor")

    def add_to_queue(self, book: BookEntry):
        self.queue_panel.add_job(book)
        self._show_page("queue")

    def convert_now(self, book: BookEntry):
        self.queue_panel.add_job(book)
        self.queue_panel.start_all()
        self._show_page("queue")

    def add_mp3_export(self, book: BookEntry):
        self.queue_panel.add_job(book, job_type="mp3")
        self._show_page("queue")

    def update_book_metadata(self, book: BookEntry):
        """Ajoute un job de mise à jour des tags M4B à la file."""
        self.queue_panel.add_job(book, job_type="meta")
        self._show_page("queue")

    def _on_app_quit(self):
        self.converter.cancel()
        self.converter.join(timeout=15.0)

    def run(self):
        sys.exit(self._qt_app.exec())
