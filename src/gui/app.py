import sys
import os
import ctypes
from typing import List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QPushButton, QLabel, QStackedWidget, QProgressBar,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

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

SIDEBAR_W = 200

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

        self._build_ui()
        self.window.show()
        self._set_dark_titlebar()
        self._auto_load_library()
        self._qt_app.aboutToQuit.connect(self._on_app_quit)

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
        sb = QFrame()
        sb.setFixedWidth(SIDEBAR_W)
        sb.setObjectName("Sidebar")
        sb.setStyleSheet("""
            QFrame#Sidebar {
                background: #1a1a1a;
                border-right: 1px solid #333;
            }
        """)

        layout = QVBoxLayout(sb)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo + titre
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 24, 0, 16)
        hl.setSpacing(4)
        hl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        for text, style in [
            ("🎧",              "color:#0067c0; font-size:26pt; background:transparent;"),
            ("Audiobook Manager","color:#f3f3f3; font-size:10pt; font-weight:bold; background:transparent;"),
            ("HellTrucker",     "color:#888; font-size:8pt; background:transparent;"),
        ]:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.setStyleSheet(style)
            hl.addWidget(lbl)

        layout.addWidget(header)
        layout.addWidget(self._hline())

        for page_id, icon, label in [
            ("library",      "🔍", "Bibliothèque"),
            ("editor",       "✏",  "Éditeur"),
            ("queue",        "▶",  "Conversion"),
            ("scene_copy",   "📋", "Copie scène"),
            ("prez",         "📰", "Présentation"),
            ("console",      "🖥", "Console"),
            ("referential",  "📚", "Référentiel"),
        ]:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(NAV_BASE.format(bg="transparent", fg="#ccc",
                                              hover="rgba(255,255,255,0.06)"))
            btn.clicked.connect(lambda _, p=page_id: self._show_page(p))
            layout.addWidget(btn)
            self._nav_btns[page_id] = btn

        layout.addStretch()
        layout.addWidget(self._hline())

        cfg_btn = QPushButton("  ⚙  Paramètres")
        cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cfg_btn.setStyleSheet(NAV_BASE.format(bg="transparent", fg="#888",
                                              hover="rgba(255,255,255,0.06)"))
        cfg_btn.clicked.connect(self._open_settings)
        layout.addWidget(cfg_btn)

        return sb

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
        for pid, btn in self._nav_btns.items():
            if pid == page_id:
                btn.setStyleSheet(NAV_BASE.format(bg="#0067c0", fg="white",
                                                  hover="#0055aa"))
            else:
                btn.setStyleSheet(NAV_BASE.format(bg="transparent", fg="#ccc",
                                                  hover="rgba(255,255,255,0.06)"))

    # ── Page 1 : Bibliothèque ──────────────────────────────────────────────

    def _build_library_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(10)

        self._scan_btn = QPushButton("⟳  Scanner")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setToolTip(
            "Scan incrémental : ne traite que les nouveaux dossiers / fichiers.\n"
            "Les livres déjà connus sont conservés tels quels.\n"
            "Les sorties de conversion et les chemins listés dans Paramètres > "
            "« Ignorés au scan » sont exclus.\n"
            "Pour forcer un scan complet : cliquer Reset puis Scanner.")
        self._scan_btn.setStyleSheet("""
            QPushButton {
                background: #0067c0; color: white; border: none;
                padding: 5px 14px; font-size: 9pt; font-weight: bold;
                font-family: "Segoe UI";
            }
            QPushButton:hover   { background: #0055aa; }
            QPushButton:pressed { background: #003f88; }
            QPushButton:disabled{ background: #444; color: #888; }
        """)
        self._scan_btn.clicked.connect(self._start_scan)
        bl.addWidget(self._scan_btn)

        update_btn = QPushButton("↻  Update")
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.setToolTip(
            "Recharge la bibliothèque depuis l'état sauvegardé\n"
            "(instantané, sans aucun scan de fichiers)")
        update_btn.clicked.connect(self._update_library)
        bl.addWidget(update_btn)

        reset_btn = QPushButton("↺  Reset cache")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip(
            "Vide uniquement le cache de fingerprints / ffprobe.\n"
            "Les fusions manuelles, les méta saisies et la liste des livres "
            "sont préservées.\n"
            "Le prochain Scanner re-fingerprint tous les fichiers à neuf.")
        reset_btn.clicked.connect(self._reset_cache)
        bl.addWidget(reset_btn)

        self._scan_label = QLabel("Aucun scan effectué")
        self._scan_label.setStyleSheet("color: #888; font-size: 9pt;")
        bl.addWidget(self._scan_label)

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

        bl.addStretch()
        vl.addWidget(bar)
        vl.addWidget(self._hline())

        self.library_panel = LibraryPanel(self)
        vl.addWidget(self.library_panel, 1)

        self._pages["library"] = page
        self._stack.addWidget(page)

    # ── Page 2 : Éditeur ──────────────────────────────────────────────────

    def _build_editor_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Header
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 5, 8, 5)
        hl.setSpacing(8)

        back = QPushButton("← Bibliothèque")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setStyleSheet("""
            QPushButton {
                background: transparent; color: #888; border: none;
                padding: 4px 10px; font-size: 9pt;
            }
            QPushButton:hover { color: #f3f3f3; background: rgba(255,255,255,0.05); }
        """)
        back.clicked.connect(lambda: self._show_page("library"))
        hl.addWidget(back)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3a3a3a;")
        hl.addWidget(sep)

        self._editor_title = QLabel("Aucun livre sélectionné")
        self._editor_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hl.addWidget(self._editor_title)
        hl.addStretch()

        vl.addWidget(header)
        vl.addWidget(self._hline())

        self.editor_panel = EditorPanel(self)
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
        if pending > 0:
            btn.setText(f"  ▶  Conversion  ({pending})")
        else:
            btn.setText("  ▶  Conversion")

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
        """Recharge instantanément depuis last_library.json + library.json, sans ffprobe."""
        books = self.scanner.load_last_books()
        self.library_panel.populate(books)
        n = len(books)
        self._scan_label.setText(
            f"{n} livre{'s' if n != 1 else ''} — mis à jour")
        self._scan_label.setStyleSheet("color: #57cc7a; font-size: 9pt;")

    def _auto_load_library(self):
        books = self.scanner.load_last_books()
        if books:
            self.library_panel.populate(books)
            n = len(books)
            self._scan_label.setText(
                f"{n} livre{'s' if n != 1 else ''} — cliquez Scanner pour mettre à jour")
            self._scan_label.setStyleSheet("color: #888; font-size: 9pt;")

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
            self._scan_label.setText("Cache vidé — cliquez Scanner")
            self._scan_label.setStyleSheet("color: #e8a020; font-size: 9pt;")

    def _start_scan(self):
        if not self.config_manager.app_config.source_folders:
            QMessageBox.information(
                self.window, "Aucun dossier configuré",
                "Configurez d'abord les dossiers sources dans Paramètres.")
            self._open_settings()
            return

        self._scan_btn.setEnabled(False)
        self._scan_label.setText("Scan en cours…")
        self._scan_label.setStyleSheet("color: #e8a020; font-size: 9pt;")
        self._scan_progress.show()

        self._scan_progress.setValue(0)
        self._scan_thread = _ScanThread(self.scanner)
        self._scan_thread.progress.connect(self._on_scan_progress)
        self._scan_thread.finished.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_progress(self, current: int, total: int, msg: str):
        pct = int(current / total * 100) if total > 0 else 0
        self._scan_progress.setValue(pct)
        self._scan_label.setText(msg[:70])

    def _on_scan_done(self, books: List[BookEntry]):
        self._scan_progress.setValue(100)
        self._scan_progress.hide()
        self._scan_btn.setEnabled(True)
        self.library_panel.populate(books)
        n = len(books)
        self._scan_label.setText(
            f"{n} livre{'s' if n != 1 else ''} trouvé{'s' if n != 1 else ''}")
        self._scan_label.setStyleSheet("color: #57cc7a; font-size: 9pt;")

    def on_book_selected(self, book: BookEntry):
        self.editor_panel.load_book(book)
        self._editor_title.setText(book.display_title)
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
