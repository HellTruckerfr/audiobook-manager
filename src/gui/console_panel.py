import html
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont


class _LogBridge(QObject):
    message = pyqtSignal(str, str)  # (text, level)


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
        self._bridge.message.connect(self._append_html)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("background: #1a1a1a; border-bottom: 1px solid #2a2a2a;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 5, 10, 5)
        bl.setSpacing(8)

        lbl = QLabel("Console de conversion")
        lbl.setStyleSheet("color: #666; font-size: 9pt;")
        bl.addWidget(lbl)
        bl.addStretch()

        for label, fn in [("📋 Copier tout", self._copy_all),
                           ("🗑 Vider",       self._clear)]:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.clicked.connect(fn)
            bl.addWidget(btn)

        layout.addWidget(bar)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setStyleSheet(
            "QTextEdit { background:#0d0d0d; color:#c0c0c0; border:none; padding:4px; }")
        self._text.document().setMaximumBlockCount(8000)
        layout.addWidget(self._text, 1)

    # ── API publique (thread-safe) ─────────────────────────────────────────

    def log(self, msg: str, level: str = "info"):
        """Peut être appelé depuis n'importe quel thread."""
        self._bridge.message.emit(msg, level)

    # ── Interne ────────────────────────────────────────────────────────────

    def _append_html(self, msg: str, level: str):
        color = self.COLORS.get(level, "#c0c0c0")
        ts    = time.strftime("%H:%M:%S")
        line  = (
            f'<span style="color:#2e2e2e">[{ts}]</span>'
            f' <span style="color:{color}">{html.escape(msg)}</span>'
        )
        self._text.append(line)
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear(self):
        self._text.clear()

    def _copy_all(self):
        QApplication.clipboard().setText(self._text.toPlainText())
