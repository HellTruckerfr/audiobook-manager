from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QDialog, QDialogButtonBox,
    QLineEdit, QMessageBox,
)
from PyQt6.QtCore import Qt


_FIELDS = [
    ("author",    "Auteurs"),
    ("series",    "Séries"),
    ("narrator",  "Narrateurs"),
    ("publisher", "Éditeurs"),
]


class ReferentialPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._lists: dict = {}
        self._count_lbls: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)
        lbl = QLabel("Référentiel")
        lbl.setStyleSheet("font-size: 11pt; font-weight: bold;")
        hl.addWidget(lbl)
        hl.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #57cc7a; font-size: 9pt;")
        hl.addWidget(self._status_lbl)
        layout.addWidget(header)

        self._tabs = QTabWidget()
        for field, label in _FIELDS:
            self._tabs.addTab(self._build_tab(field), label)
        layout.addWidget(self._tabs, 1)

    def _build_tab(self, field: str) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(8)

        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        lst.setSortingEnabled(False)
        lst.doubleClicked.connect(lambda _, f=field: self._rename(f))
        self._lists[field] = lst
        vl.addWidget(lst, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        rename_btn = QPushButton("✎ Renommer")
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.clicked.connect(lambda _, f=field: self._rename(f))
        btn_row.addWidget(rename_btn)

        delete_btn = QPushButton("✕ Supprimer")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda _, f=field: self._delete(f))
        btn_row.addWidget(delete_btn)

        btn_row.addStretch()

        count_lbl = QLabel("")
        count_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        self._count_lbls[field] = count_lbl
        btn_row.addWidget(count_lbl)

        vl.addLayout(btn_row)
        return w

    def refresh(self):
        for field, lst in self._lists.items():
            values = self.app.config_manager.get_referential(field)
            lst.clear()
            for v in values:
                lst.addItem(QListWidgetItem(v))
            n = len(values)
            self._count_lbls[field].setText(f"{n} entrée{'s' if n != 1 else ''}")

    def _rename(self, field: str):
        lst = self._lists[field]
        item = lst.currentItem()
        if not item:
            return
        old = item.text()

        dlg = QDialog(self)
        dlg.setWindowTitle("Renommer")
        dlg.resize(400, 110)
        vl = QVBoxLayout(dlg)
        vl.addWidget(QLabel(f"Nouveau nom pour « {old} » :"))
        le = QLineEdit(old)
        le.selectAll()
        vl.addWidget(le)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new = le.text().strip()
        if not new or new == old:
            return

        count = self.app.config_manager.rename_referential_value(field, old, new)
        self.refresh()
        if count:
            self._status_lbl.setText(f"✓ {count} livre{'s' if count != 1 else ''} mis à jour")
            self.app._update_library()

    def _delete(self, field: str):
        lst = self._lists[field]
        item = lst.currentItem()
        if not item:
            return
        old = item.text()

        reply = QMessageBox.question(
            self, "Supprimer",
            f"Effacer « {old} » de tous les livres qui l'utilisent ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        count = self.app.config_manager.rename_referential_value(field, old, "")
        self.refresh()
        if count:
            self._status_lbl.setText(f"✓ {count} livre{'s' if count != 1 else ''} mis à jour")
            self.app._update_library()
