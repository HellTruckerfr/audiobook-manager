DARK_STYLESHEET = """
/* ══════════════════════════════════════════════════════════════
   Windows 11 Dark — Audiobook Manager
   ══════════════════════════════════════════════════════════════ */

/* ── Global ───────────────────────────────────────────────── */
* {
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 10pt;
}

QWidget {
    background-color: #202020;
    color: #f3f3f3;
    selection-background-color: #0067c0;
    selection-color: #ffffff;
}

QMainWindow {
    background-color: #202020;
}

QFrame {
    background-color: transparent;
    border: none;
}

QLabel {
    background: transparent;
    color: #f3f3f3;
}

/* ── Line Edit ────────────────────────────────────────────── */
QLineEdit {
    background-color: #3a3a3a;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 4px 8px;
    color: #f3f3f3;
    min-height: 22px;
}
QLineEdit:focus {
    border-color: #0067c0;
    background-color: #3d3d3d;
}
QLineEdit:disabled {
    background-color: #2a2a2a;
    color: #555;
    border-color: #383838;
}
QLineEdit:read-only {
    background-color: #2e2e2e;
    color: #aaa;
}

/* ── Combo Box ────────────────────────────────────────────── */
QComboBox {
    background-color: #3a3a3a;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 4px 8px;
    color: #f3f3f3;
    min-height: 22px;
}
QComboBox:hover {
    border-color: #686868;
}
QComboBox:focus {
    border-color: #0067c0;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    border-left: 1px solid #505050;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left:  4px solid transparent;
    border-right: 4px solid transparent;
    border-top:   5px solid #aaaaaa;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    border: 1px solid #505050;
    border-radius: 4px;
    selection-background-color: #0067c0;
    selection-color: white;
    color: #f3f3f3;
    outline: none;
    padding: 2px;
}
QComboBox QAbstractItemView::item {
    padding: 4px 8px;
    min-height: 22px;
}
QComboBox QAbstractItemView::item:hover {
    background: rgba(255,255,255,0.07);
}

/* ── Push Button ─────────────────────────────────────────── */
QPushButton {
    background-color: #383838;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 5px 14px;
    color: #f3f3f3;
    font-size: 9.5pt;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #444;
    border-color: #606060;
}
QPushButton:pressed {
    background-color: #2a2a2a;
    border-color: #404040;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #555;
    border-color: #383838;
}
QPushButton:default {
    border-color: #0067c0;
}

/* ── Check Box ───────────────────────────────────────────── */
QCheckBox {
    background: transparent;
    spacing: 7px;
    color: #f3f3f3;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #555;
    border-radius: 3px;
    background: #3a3a3a;
}
QCheckBox::indicator:hover {
    border-color: #0067c0;
}
QCheckBox::indicator:checked {
    background: #0067c0;
    border-color: #0067c0;
}
QCheckBox::indicator:checked:hover {
    background: #0055aa;
}

/* ── Tab Widget ──────────────────────────────────────────── */
QTabWidget {
    background: transparent;
}
QTabWidget::pane {
    border: none;
    border-top: 1px solid #2e2e2e;
    background-color: #202020;
    top: -1px;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #999;
    padding: 7px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 9.5pt;
    min-width: 70px;
}
QTabBar::tab:hover {
    color: #e0e0e0;
    background: rgba(255,255,255,0.04);
}
QTabBar::tab:selected {
    color: #f3f3f3;
    border-bottom: 2px solid #0067c0;
}

/* ── Table Widget ────────────────────────────────────────── */
QTableWidget {
    background-color: #1e1e1e;
    alternate-background-color: #222222;
    border: none;
    gridline-color: transparent;
    color: #e8e8e8;
    font-size: 9pt;
    outline: none;
}
QTableWidget::item {
    padding: 5px 6px;
    border: none;
}
QTableWidget::item:selected {
    background-color: #0067c0;
    color: white;
}
QTableWidget::item:hover:!selected {
    background-color: rgba(255,255,255,0.05);
}
QTableCornerButton::section {
    background-color: #1e1e1e;
    border: none;
    border-bottom: 1px solid #2e2e2e;
}

/* ── Header View ─────────────────────────────────────────── */
QHeaderView {
    background: #1e1e1e;
    border: none;
}
QHeaderView::section {
    background-color: #1e1e1e;
    color: #888;
    padding: 5px 8px;
    border: none;
    border-bottom: 1px solid #2e2e2e;
    border-right: 1px solid #2e2e2e;
    font-size: 8.5pt;
    font-weight: normal;
}
QHeaderView::section:last {
    border-right: none;
}
QHeaderView::section:hover {
    background-color: #282828;
    color: #cccccc;
}
QHeaderView::section:checked {
    background-color: #0067c0;
    color: white;
}

/* ── Scroll Bar ──────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #4a4a4a;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #686868;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #4a4a4a;
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #686868;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    width: 0;
}

/* ── Dialog ──────────────────────────────────────────────── */
QDialog {
    background-color: #202020;
}
QDialogButtonBox QPushButton {
    min-width: 72px;
}

/* ── Splitter ────────────────────────────────────────────── */
QSplitter::handle {
    background: #2e2e2e;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* ── Progress Bar ────────────────────────────────────────── */
QProgressBar {
    background-color: #2a2a2a;
    border: none;
    border-radius: 3px;
    color: transparent;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #0067c0;
    border-radius: 3px;
}

/* ── Message Box ─────────────────────────────────────────── */
QMessageBox {
    background-color: #202020;
}
QMessageBox QLabel {
    color: #f3f3f3;
}

/* ── Tool Tip ────────────────────────────────────────────── */
QToolTip {
    background-color: #2d2d2d;
    color: #f3f3f3;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 9pt;
}

/* ── Group Box ───────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #2e2e2e;
    border-radius: 4px;
    margin-top: 14px;
    padding-top: 6px;
    color: #888;
    font-size: 9pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #888;
}

/* ── Form Layout label alignment ─────────────────────────── */
QFormLayout QLabel {
    color: #bbb;
    font-size: 9.5pt;
}
"""
