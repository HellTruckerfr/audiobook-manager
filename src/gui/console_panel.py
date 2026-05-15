import html
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QApplication, QTabWidget,
)
from PyQt6.QtCore import pyqtSignal, QObject, QSize
from PyQt6.QtGui import QFont

from .icon_utils import get_icon


class _LogBridge(QObject):
    conv_msg   = pyqtSignal(str, str)  # (text, level) → conversions tab
    action_msg = pyqtSignal(str, str)  # (text, level) → journal tab


class ConsolePanel(QWidget):
    COLORS = {
        "start":    "#4fc3f7",
        "ok":       "#57cc7a",
        "error":    "#c94040",
        "progress": "#e8a020",
        "detail":   "#606060",
        "ffmpeg":   "#4a4a4a",
        "info":     "#888888",
    }

    def __init__(self):
        super().__init__()
        self._bridge = _LogBridge()
        self._bridge.conv_msg.connect(self._append_conv)
        self._bridge.action_msg.connect(self._append_action)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab { padding: 5px 14px; }"
            "QTabBar::tab:selected { color: white; }"
        )

        self._conv_text, conv_widget = self._make_tab_widget("Console de conversion")
        self._tabs.addTab(conv_widget, "Conversions")

        self._action_text, action_widget = self._make_tab_widget("Journal des actions")
        self._tabs.addTab(action_widget, "Journal")

        layout.addWidget(self._tabs, 1)

    # ── Construction ──────────────────────────────────────────────────────

    def _make_tab_widget(self, label: str):
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("background: #1a1a1a; border-bottom: 1px solid #2a2a2a;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 5, 10, 5)
        bl.setSpacing(8)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #666; font-size: 9pt;")
        bl.addWidget(lbl)
        bl.addStretch()

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 9))
        text.setStyleSheet(
            "QTextEdit { background:#0d0d0d; color:#c0c0c0; border:none; padding:4px; }")
        text.document().setMaximumBlockCount(8000)

        copy_btn = QPushButton("  Copier tout")
        copy_btn.setIcon(get_icon("exportation.ico"))
        copy_btn.setIconSize(QSize(16, 16))
        copy_btn.setFixedHeight(24)
        copy_btn.clicked.connect(lambda _, t=text: QApplication.clipboard().setText(t.toPlainText()))
        bl.addWidget(copy_btn)

        clear_btn = QPushButton("  Vider")
        clear_btn.setIcon(get_icon("Vider.ico"))
        clear_btn.setIconSize(QSize(16, 16))
        clear_btn.setFixedHeight(24)
        clear_btn.clicked.connect(text.clear)
        bl.addWidget(clear_btn)

        vl.addWidget(bar)
        vl.addWidget(text, 1)
        return text, widget

    # ── API publique (thread-safe) ─────────────────────────────────────────

    def log(self, msg: str, level: str = "info"):
        """Log de conversion — peut être appelé depuis n'importe quel thread."""
        self._bridge.conv_msg.emit(msg, level)

    def log_action(self, msg: str, level: str = "info"):
        """Journal des actions — peut être appelé depuis n'importe quel thread."""
        self._bridge.action_msg.emit(msg, level)

    # ── Interne ────────────────────────────────────────────────────────────

    def _fmt(self, msg: str, level: str) -> str:
        color = self.COLORS.get(level, "#c0c0c0")
        ts    = time.strftime("%H:%M:%S")
        return (
            f'<span style="color:#2e2e2e">[{ts}]</span>'
            f' <span style="color:{color}">{html.escape(msg)}</span>'
        )

    def _append_conv(self, msg: str, level: str):
        self._conv_text.append(self._fmt(msg, level))
        sb = self._conv_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _append_action(self, msg: str, level: str):
        self._action_text.append(self._fmt(msg, level))
        sb = self._action_text.verticalScrollBar()
        sb.setValue(sb.maximum())
