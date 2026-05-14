import os
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QCheckBox, QFileDialog,
    QDialogButtonBox, QMessageBox, QFrame, QComboBox,
)
from PyQt6.QtCore import Qt

from ..config_manager import ConfigManager, FolderConfig
from ..windows_utils import set_music_folder_type


class SettingsDialog(QDialog):
    def __init__(self, parent, config_manager: ConfigManager):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Paramètres")
        self.resize(720, 480)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_sources_tab(),  "Dossiers sources")
        tabs.addTab(self._build_output_tab(),   "Sorties")
        tabs.addTab(self._build_options_tab(),  "Options")
        tabs.addTab(self._build_ignore_tab(),   "Ignorés au scan")
        layout.addWidget(tabs, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._load()

    # ── Onglet sources ────────────────────────────────────────────────

    def _build_sources_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)
        vl.addWidget(QLabel("Dossiers à scanner (MP3, M4B, mixtes) :"))

        self._src_table = QTableWidget(0, 3)
        self._src_table.setHorizontalHeaderLabels(["Étiquette", "Chemin", "Structuré"])
        self._src_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._src_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._src_table.setShowGrid(False)
        self._src_table.verticalHeader().hide()

        hh = self._src_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._src_table.setColumnWidth(0, 120)
        self._src_table.setColumnWidth(2, 80)
        vl.addWidget(self._src_table, 1)

        btn_row = QHBoxLayout()
        for text, fn in [
            ("+ Ajouter",  self._add_source),
            ("✎ Modifier", self._edit_source),
            ("✕ Supprimer",self._del_source),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btn_row.addWidget(b)
        btn_row.addStretch()
        vl.addLayout(btn_row)
        return w

    # ── Onglet sorties ────────────────────────────────────────────────

    _NAMING_STYLES = [
        ("perso", "Perso — T 01 - Titre.m4b  (Auteur/Série/fichier)"),
        ("scene", "Scène — Série.T01.Titre.Auteur.FR.[AAC.128K]-Tag.m4b"),
    ]
    _NAMING_PREVIEW = {
        "perso": "Auteur/\n  The Expanse/\n    T 06 - Les Cendres de Babylone.m4b\n    T 07 - Le soulèvement de Persépolis.m4b",
        "scene": "Auteur/\n  The.Expanse.T06.Les.Cendres.de.Babylone.James.S.A.Corey.FR.[AAC.128K]-HellTrucker.m4b\n  The.Expanse.T07.Le.soulavement.de.Persepolis.James.S.A.Corey.FR.[AAC.128K]-HellTrucker.m4b",
    }

    def _build_output_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)
        vl.setSpacing(10)

        self._out_m4b = QLineEdit()
        self._out_mp3 = QLineEdit()

        for label, le in [("Sortie M4B :", self._out_m4b),
                           ("Sortie MP3 :", self._out_mp3)]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            row.addWidget(le, 4)
            btn = QPushButton("…")
            btn.setMaximumWidth(30)
            _le = le
            btn.clicked.connect(lambda _, l=_le: self._browse_dir(l))
            row.addWidget(btn)
            music_btn = QPushButton("♪")
            music_btn.setMaximumWidth(30)
            music_btn.setToolTip(
                "Configurer comme dossier Musique (Windows Explorer)\n"
                "Crée desktop.ini récursivement — active les colonnes\n"
                "N°, Titre, Auteurs, Interprète de l'album, Album, Durée"
            )
            music_btn.clicked.connect(lambda _, l=_le: self._apply_music_folder_type(l))
            row.addWidget(music_btn)
            vl.addLayout(row)

        # ── Nommage des fichiers ──────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        vl.addWidget(sep)

        vl.addWidget(QLabel("Nommage des fichiers M4B :"))
        self._naming_cb = QComboBox()
        for _key, _label in self._NAMING_STYLES:
            self._naming_cb.addItem(_label, _key)
        vl.addWidget(self._naming_cb)

        self._naming_preview = QLabel()
        self._naming_preview.setStyleSheet(
            "color: #888; font-family: Consolas, monospace; font-size: 8.5pt;"
            "background: #1a1a1a; padding: 6px; border-radius: 4px;")
        self._naming_preview.setTextFormat(Qt.TextFormat.PlainText)
        vl.addWidget(self._naming_preview)

        self._naming_cb.currentIndexChanged.connect(self._update_naming_preview)

        vl.addStretch()
        return w

    def _update_naming_preview(self):
        key = self._naming_cb.currentData()
        self._naming_preview.setText(self._NAMING_PREVIEW.get(key, ""))

    def _apply_music_folder_type(self, path_le: QLineEdit):
        path = path_le.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Dossier introuvable",
                                f"Le dossier n'existe pas :\n{path}")
            return
        processed, errors = set_music_folder_type(path)
        if errors:
            QMessageBox.warning(
                self, "Type Musique",
                f"{processed} dossier(s) configurés, {errors} erreur(s).\n"
                "Vérifiez les droits d'accès (relancer en admin si nécessaire).")
        else:
            QMessageBox.information(
                self, "Type Musique",
                f"{processed} dossier(s) configurés avec succès.\n"
                "Rouvrez les dossiers dans l'Explorateur pour voir les colonnes musique.")

    # ── Onglet options ────────────────────────────────────────────────

    _META_FIELDS = [
        ("title",      "Titre"),
        ("author",     "Auteur"),
        ("series",     "Série"),
        ("volume",     "Volume"),
        ("narrator",   "Narrateur"),
        ("genre",      "Genre"),
        ("year",       "Année"),
        ("language",   "Langue"),
        ("asin",       "ASIN"),
        ("publisher",  "Éditeur"),
        ("cover_path", "Cover"),
    ]

    def _build_options_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)
        vl.setSpacing(10)

        self._logo_path = QLineEdit()
        self._font_path = QLineEdit()
        self._tracker_name = QLineEdit()

        for label, le, is_dir in [
            ("Logo watermark :", self._logo_path, False),
            ("Police FFmpeg :",  self._font_path, False),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            row.addWidget(le, 4)
            btn = QPushButton("…")
            btn.setMaximumWidth(30)
            _le = le
            btn.clicked.connect(lambda _, l=_le: self._browse_file(l))
            row.addWidget(btn)
            vl.addLayout(row)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setStyleSheet("color: #444;")
        vl.addWidget(sep0)

        row_tracker = QHBoxLayout()
        row_tracker.addWidget(QLabel("Nom du tracker :"), 1)
        row_tracker.addWidget(self._tracker_name, 4)
        vl.addLayout(row_tracker)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        vl.addWidget(sep)

        vl.addWidget(QLabel(
            "Champs requis pour qu'un livre soit considéré « complet »\n"
            "(utilisé par le filtre « Cacher livres complets » de la Bibliothèque) :"))

        grid = QHBoxLayout()
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        self._meta_field_cbs: dict = {}
        for i, (key, label) in enumerate(self._META_FIELDS):
            cb = QCheckBox(label)
            self._meta_field_cbs[key] = cb
            (col1 if i % 2 == 0 else col2).addWidget(cb)
        grid.addLayout(col1)
        grid.addLayout(col2)
        grid.addStretch()
        vl.addLayout(grid)

        vl.addStretch()
        return w

    # ── Onglet ignorés au scan ────────────────────────────────────────

    def _build_ignore_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Chemins exclus du scan. Les sorties M4B des conversions et les "
            "fichiers copiés via « Copie scène » sont ajoutés automatiquement à "
            "cette liste.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #888;")
        vl.addWidget(info)

        self._ignore_table = QTableWidget(0, 1)
        self._ignore_table.setHorizontalHeaderLabels(["Chemin"])
        self._ignore_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._ignore_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._ignore_table.setShowGrid(False)
        self._ignore_table.verticalHeader().hide()
        self._ignore_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        vl.addWidget(self._ignore_table, 1)

        btn_row = QHBoxLayout()
        for text, fn in [
            ("+ Fichier…",   self._add_ignore_file),
            ("+ Dossier…",   self._add_ignore_folder),
            ("✕ Retirer",    self._del_ignore),
            ("✕ Tout vider", self._clear_ignore),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btn_row.addWidget(b)
        btn_row.addStretch()
        vl.addLayout(btn_row)
        return w

    def _append_ignore(self, path: str):
        row = self._ignore_table.rowCount()
        self._ignore_table.insertRow(row)
        it = QTableWidgetItem(path)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self._ignore_table.setItem(row, 0, it)

    def _add_ignore_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Fichier à ignorer", "",
                                              "Audiobooks (*.m4b *.mp3);;Tous (*.*)")
        if path:
            self._append_ignore(path)

    def _add_ignore_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Dossier à ignorer")
        if path:
            self._append_ignore(path)

    def _del_ignore(self):
        rows = sorted({i.row() for i in self._ignore_table.selectedItems()},
                      reverse=True)
        for r in rows:
            self._ignore_table.removeRow(r)

    def _clear_ignore(self):
        if self._ignore_table.rowCount() == 0:
            return
        if QMessageBox.question(
            self, "Vider la liste",
            "Vider tous les chemins ignorés ?\n"
            "Les sorties de conversion seront re-détectées au prochain scan.",
        ) == QMessageBox.StandardButton.Yes:
            self._ignore_table.setRowCount(0)

    # ── Load / Save ───────────────────────────────────────────────────

    def _load(self):
        self._src_table.setRowCount(0)
        for f in self.cfg.app_config.source_folders:
            self._append_source(f)
        self._out_m4b.setText(self.cfg.app_config.output_m4b)
        self._out_mp3.setText(self.cfg.app_config.output_mp3)
        self._logo_path.setText(self.cfg.app_config.logo_path)
        self._font_path.setText(self.cfg.app_config.font_path)
        self._tracker_name.setText(self.cfg.app_config.tracker_name)
        # Nommage
        style = self.cfg.app_config.naming_style
        for i, (key, _) in enumerate(self._NAMING_STYLES):
            if key == style:
                self._naming_cb.setCurrentIndex(i)
                break
        self._update_naming_preview()
        # Champs méta requis
        required = set(self.cfg.app_config.metadata_required_fields)
        for key, cb in self._meta_field_cbs.items():
            cb.setChecked(key in required)
        # Liste des chemins ignorés
        self._ignore_table.setRowCount(0)
        for p in self.cfg.app_config.scan_ignore_paths:
            self._append_ignore(p)

    def _save(self):
        folders = []
        for row in range(self._src_table.rowCount()):
            label = self._src_table.item(row, 0).text()
            path  = self._src_table.item(row, 1).text()
            struc = self._src_table.item(row, 2).text() == "Oui"
            folders.append(FolderConfig(label=label, path=path, structured=struc))

        self.cfg.app_config.source_folders = folders
        self.cfg.app_config.output_m4b     = self._out_m4b.text()
        self.cfg.app_config.output_mp3     = self._out_mp3.text()
        self.cfg.app_config.logo_path      = self._logo_path.text()
        self.cfg.app_config.font_path      = self._font_path.text()
        self.cfg.app_config.tracker_name   = self._tracker_name.text().strip() or "La Cale"
        self.cfg.app_config.naming_style   = self._naming_cb.currentData()
        self.cfg.app_config.metadata_required_fields = [
            key for key, cb in self._meta_field_cbs.items() if cb.isChecked()
        ]
        self.cfg.app_config.scan_ignore_paths = [
            self._ignore_table.item(r, 0).text()
            for r in range(self._ignore_table.rowCount())
            if self._ignore_table.item(r, 0)
        ]
        self.cfg.save_config()
        self.accept()

    # ── Gestion des sources ───────────────────────────────────────────

    def _append_source(self, fc: FolderConfig):
        row = self._src_table.rowCount()
        self._src_table.insertRow(row)
        for col, text in enumerate([fc.label, fc.path, "Oui" if fc.structured else "Non"]):
            it = QTableWidgetItem(text)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._src_table.setItem(row, col, it)

    def _add_source(self):
        _FolderDialog(self, None, self._append_source).exec()

    def _edit_source(self):
        rows = self._src_table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        fc = FolderConfig(
            label=self._src_table.item(row, 0).text(),
            path=self._src_table.item(row, 1).text(),
            structured=self._src_table.item(row, 2).text() == "Oui",
        )
        def _apply(new_fc: FolderConfig):
            for col, text in enumerate([new_fc.label, new_fc.path,
                                         "Oui" if new_fc.structured else "Non"]):
                self._src_table.item(row, col).setText(text)

        _FolderDialog(self, fc, _apply).exec()

    def _del_source(self):
        rows = self._src_table.selectedItems()
        if rows:
            self._src_table.removeRow(rows[0].row())

    # ── Browse helpers ────────────────────────────────────────────────

    @staticmethod
    def _browse_dir(le: QLineEdit):
        path = QFileDialog.getExistingDirectory(None, "Sélectionner un dossier",
                                                le.text())
        if path:
            le.setText(path)

    @staticmethod
    def _browse_file(le: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(None, "Sélectionner un fichier",
                                              le.text())
        if path:
            le.setText(path)


class _FolderDialog(QDialog):
    def __init__(self, parent, folder: Optional[FolderConfig],
                 callback: Callable[[FolderConfig], None]):
        super().__init__(parent)
        self.callback = callback
        self.setWindowTitle("Dossier source")
        self.resize(500, 160)

        vl = QVBoxLayout(self)

        form_w = QWidget()
        form_l = QVBoxLayout(form_w)
        form_l.setSpacing(8)

        def _row(label, widget, btn=None):
            hl = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setMinimumWidth(100)
            hl.addWidget(lbl)
            hl.addWidget(widget, 1)
            if btn:
                hl.addWidget(btn)
            form_l.addLayout(hl)

        self._label_le = QLineEdit(folder.label if folder else "")
        _row("Étiquette :", self._label_le)

        self._path_le = QLineEdit(folder.path if folder else "")
        browse = QPushButton("…")
        browse.setMaximumWidth(30)
        browse.clicked.connect(self._browse)
        _row("Chemin :", self._path_le, browse)

        self._structured_cb = QCheckBox("Structuré  (Auteur › [Série ›] Volume)")
        self._structured_cb.setChecked(folder.structured if folder else False)
        form_l.addWidget(self._structured_cb)

        hint = QLabel("Structuré = dossiers organisés en Auteur > [Série >] Volume")
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        form_l.addWidget(hint)

        vl.addWidget(form_w)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        vl.addWidget(btns)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier",
                                                self._path_le.text())
        if path:
            self._path_le.setText(path)
            if not self._label_le.text():
                self._label_le.setText(os.path.basename(path))

    def _ok(self):
        path = self._path_le.text().strip()
        if not path:
            QMessageBox.warning(self, "Attention", "Le chemin est requis.")
            return
        self.callback(FolderConfig(
            label=self._label_le.text().strip() or path,
            path=path,
            structured=self._structured_cb.isChecked(),
        ))
        self.accept()
