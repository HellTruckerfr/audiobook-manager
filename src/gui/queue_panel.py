import os
import subprocess
import time
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame, QMenu, QProgressBar, QComboBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import QApplication

from ..models import ConversionJob, BookEntry

STATUS_COLOR = {
    "queued":     "#888",
    "converting": "#e8a020",
    "done":       "#57cc7a",
    "error":      "#c94040",
    "cancelled":  "#555",
}
STATUS_ICON = {
    "queued":     "○",
    "converting": "⟳",
    "done":       "✓",
    "error":      "✗",
    "cancelled":  "—",
}

COL_CHECK = 0
COL_ICON  = 1
COL_TITLE = 2
COL_AUTH  = 3
COL_PROG  = 4
COL_SIZE  = 5
COL_INFO  = 6

_PROGRESS_STYLE = """
QProgressBar {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    text-align: center;
    color: #e0e0e0;
    font-size: 8pt;
    font-weight: bold;
}
QProgressBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #00408a,
        stop:0.5 #0067c0,
        stop:1 #1a8cff
    );
    border-radius: 3px;
}
"""

_BTN_STYLE = """
QPushButton {
    background: transparent; color: #ccc; border: 1px solid #444;
    padding: 4px 10px; font-size: 8pt;
}
QPushButton:hover  { background: rgba(255,255,255,0.06); color: #f3f3f3; }
QPushButton:pressed { background: rgba(255,255,255,0.10); }
"""


class _Bridge(QObject):
    progress = pyqtSignal(float, str)
    done     = pyqtSignal(bool, str)
    log      = pyqtSignal(str, str)


class QueuePanel(QWidget):
    pending_changed = pyqtSignal(int)
    jobs_changed    = pyqtSignal()

    def __init__(self, app):
        super().__init__()
        self.app      = app
        self._jobs: List[ConversionJob]        = []
        self._running: Optional[ConversionJob] = None
        self._bridge: Optional[_Bridge]        = None
        self._progress_bars: dict              = {}
        self._job_start_time: dict             = {}
        self._populating: bool                 = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Toolbar ────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        self._btn_start = QPushButton("▶  Lancer la conversion")
        self._btn_start.setStyleSheet("""
            QPushButton {
                background: #0067c0; color: white; border: none;
                padding: 5px 16px; font-weight: bold; font-size: 9pt;
            }
            QPushButton:hover    { background: #0055aa; }
            QPushButton:pressed  { background: #003f88; }
            QPushButton:disabled { background: #444; color: #666; }
        """)
        self._btn_start.clicked.connect(self.start_all)
        ctrl.addWidget(self._btn_start)

        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["M4B", "MP3", "Méta"])
        self._fmt_combo.setFixedWidth(76)
        self._fmt_combo.setToolTip(
            "Format de conversion pour tous les jobs en attente.\n"
            "Méta = mise à jour des tags M4B sans réencodage.\n"
            "Changer ici met à jour l'ensemble de la file.")
        self._fmt_combo.setStyleSheet("""
            QComboBox {
                background: #2a2a2a; color: #f3f3f3;
                border: 1px solid #444; padding: 4px 6px; font-size: 9pt;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #2a2a2a; color: #f3f3f3;
                selection-background-color: #0067c0;
            }
        """)
        self._fmt_combo.currentTextChanged.connect(self._on_format_changed)
        ctrl.addWidget(self._fmt_combo)

        btn_cancel = QPushButton("✕  Annuler en cours")
        btn_cancel.setToolTip("Annule uniquement la conversion en cours")
        btn_cancel.setStyleSheet(_BTN_STYLE)
        btn_cancel.clicked.connect(self._cancel_current)
        ctrl.addWidget(btn_cancel)

        btn_cancel_all = QPushButton("✕✕  Tout annuler")
        btn_cancel_all.setToolTip("Annule la conversion en cours ET vide tous les jobs en attente")
        btn_cancel_all.setStyleSheet(_BTN_STYLE)
        btn_cancel_all.clicked.connect(self._cancel_all)
        ctrl.addWidget(btn_cancel_all)

        btn_clear = QPushButton("🗑  Vider terminés")
        btn_clear.setStyleSheet(_BTN_STYLE)
        btn_clear.clicked.connect(self._clear_done)
        ctrl.addWidget(btn_clear)

        ctrl.addSpacing(12)

        check_all_btn = QPushButton("☑ Tout")
        check_all_btn.setToolTip("Cocher tous les jobs")
        check_all_btn.setStyleSheet(_BTN_STYLE)
        check_all_btn.clicked.connect(self._check_all)
        ctrl.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("☐ Tout")
        uncheck_all_btn.setToolTip("Décocher tous les jobs")
        uncheck_all_btn.setStyleSheet(_BTN_STYLE)
        uncheck_all_btn.clicked.connect(self._uncheck_all)
        ctrl.addWidget(uncheck_all_btn)

        ctrl.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        ctrl.addWidget(self._status_lbl)

        layout.addLayout(ctrl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

        # ── Table ──────────────────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["▶", "", "Titre", "Auteur", "Progression", "Taille", "Info"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.itemChanged.connect(self._on_item_changed)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_ICON,  QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_AUTH,  QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_PROG,  QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_SIZE,  QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_INFO,  QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(COL_CHECK, 32)
        self._table.setColumnWidth(COL_ICON,  28)
        self._table.setColumnWidth(COL_TITLE, 320)
        self._table.setColumnWidth(COL_AUTH,  160)
        self._table.setColumnWidth(COL_PROG,  180)
        self._table.setColumnWidth(COL_SIZE,  72)

        layout.addWidget(self._table, 1)
        self._update_status_lbl()

    # ── Public API ─────────────────────────────────────────────────────

    _FMT_MAP = {"m4b": "m4b", "mp3": "mp3", "méta": "meta"}

    def add_job(self, book: BookEntry, job_type: str = "m4b"):
        fmt = self._FMT_MAP.get(self._fmt_combo.currentText().lower(), "m4b")
        # job_type explicite (ex: "mp3", "meta") prime sur la combo globale
        effective_type = job_type if job_type != "m4b" else fmt
        for j in self._jobs:
            if j.book.id == book.id and j.status == "queued" and j.job_type == effective_type:
                return
        job = ConversionJob(book=book, job_type=effective_type)
        self._jobs.append(job)
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setRowHeight(row, 28)
        self._set_row(row, job, "", "")
        self._update_status_lbl()
        self.pending_changed.emit(self._pending_count())
        self.jobs_changed.emit()

    def is_book_queued(self, book_id: str) -> bool:
        return any(j.book.id == book_id and j.status in ("queued", "converting")
                   for j in self._jobs)

    def remove_pending_by_book(self, book_id: str) -> bool:
        target = next((j for j in self._jobs
                       if j.book.id == book_id and j.status == "queued"), None)
        if target is None:
            return False
        self._remove_job(target)
        return True

    def start_all(self):
        if not [j for j in self._jobs if j.status == "queued"]:
            return
        self._btn_start.setEnabled(False)
        self._process_next()

    # ── Format global ──────────────────────────────────────────────────

    def _on_format_changed(self, text: str):
        fmt = self._FMT_MAP.get(text.lower(), "m4b")
        for job in self._jobs:
            if job.status == "queued":
                job.job_type = fmt
        self._refresh_all_rows()

    def _refresh_all_rows(self):
        for row in range(self._table.rowCount()):
            it = self._table.item(row, COL_TITLE)
            if it is None:
                continue
            book_id = it.data(Qt.ItemDataRole.UserRole)
            job = next((j for j in self._jobs if j.book.id == book_id), None)
            if job:
                self._set_row(row, job, self._table.item(row, COL_SIZE).text()
                              if self._table.item(row, COL_SIZE) else "",
                              self._table.item(row, COL_INFO).text()
                              if self._table.item(row, COL_INFO) else "")

    # ── Traitement ─────────────────────────────────────────────────────

    def _process_next(self):
        pending = [j for j in self._jobs if j.status == "queued"]
        if not pending:
            self._btn_start.setEnabled(True)
            self._update_status_lbl()
            return

        job = pending[0]
        self._running = job
        job.status = "converting"
        row = self._find_row(job)
        self._set_row(row, job, "", "Démarrage…")
        self._install_progress_bar(row, job.book.id, 0)

        cfg = self.app.config_manager.app_config
        self._job_start_time[job.book.id] = time.monotonic()

        bridge = _Bridge()
        self._bridge = bridge
        bridge.progress.connect(lambda pct, msg: self._on_progress(job, pct, msg))
        bridge.done.connect(lambda ok, result: self._on_done(job, ok, result))
        console = getattr(self.app, "console_panel", None)
        if console:
            bridge.log.connect(console.log)

        if job.job_type == "meta":
            self.app.converter.update_metadata(
                job.book,
                progress_cb=bridge.progress.emit,
                done_cb=bridge.done.emit,
                log_cb=bridge.log.emit,
            )
        elif job.job_type == "mp3":
            from ..converter import build_mp3_output_dir
            out_dir = cfg.output_mp3 or os.path.join(
                os.path.expanduser("~"), "audiobooks", "mp3")
            out_path = build_mp3_output_dir(job.book, out_dir)
            job.output_path = out_path
            self.app.converter.convert_to_mp3(
                job.book, out_path,
                progress_cb=bridge.progress.emit,
                done_cb=bridge.done.emit,
                log_cb=bridge.log.emit,
            )
        else:
            from ..converter import build_output_filename, build_output_subdir, _clean_filename
            style    = cfg.naming_style
            author   = _clean_filename(job.book.display_author.split(",")[0].strip())
            subdir   = build_output_subdir(job.book, style)
            out_path = os.path.join(
                cfg.output_m4b or os.path.join(os.path.expanduser("~"), "audiobooks", "m4b"),
                author, subdir, build_output_filename(job.book, style))
            job.output_path = out_path
            self.app.converter.convert(
                job.book, out_path,
                progress_cb=bridge.progress.emit,
                done_cb=bridge.done.emit,
                log_cb=bridge.log.emit,
            )

    def _on_progress(self, job: ConversionJob, pct: float, msg: str):
        job.progress = pct
        row = self._find_row(job)

        # pct < 0 = phase parallèle indéterminée
        indeterminate = pct < 0

        eta_str = ""
        if not indeterminate:
            start = self._job_start_time.get(job.book.id)
            if start and pct > 0.06:
                frac = (pct - 0.05) / 0.95
                if frac > 0.01:
                    elapsed   = time.monotonic() - start
                    remaining = elapsed * (1 - frac) / frac
                    if remaining < 60:
                        eta_str = f" — ETA {int(remaining)}s"
                    else:
                        eta_str = f" — ETA {int(remaining // 60)}m{int(remaining % 60):02d}s"

        if row >= 0:
            self._install_progress_bar(row, job.book.id, int(pct * 100),
                                       indeterminate=indeterminate)
            it = self._table.item(row, COL_INFO)
            if it:
                it.setText(f"{msg}{eta_str}" if msg else eta_str)
        self._update_status_lbl(
            converting=0 if indeterminate else int(pct * 100), eta=eta_str)

    def _on_done(self, job: ConversionJob, ok: bool, result: str):
        row = self._find_row(job)
        self._remove_progress_bar(job.book.id, row)

        if ok:
            job.status = "done"
            if job.job_type == "mp3":
                size = ""
                if os.path.isdir(result):
                    total = sum(
                        os.path.getsize(os.path.join(result, f))
                        for f in os.listdir(result) if f.endswith(".mp3")
                    )
                    size = f"{total / 1024 / 1024:.1f} MB"
                self._set_row(row, job, size, "")
            else:
                job.book.output_m4b_path = result
                self.app.config_manager.save_book(job.book)
                self.app.library_panel.update_status(job.book.id, "done")
                size = ""
                if os.path.exists(result):
                    size = f"{os.path.getsize(result) / 1024 / 1024:.1f} MB"
                self._set_row(row, job, size, "")
        else:
            job.status = "error"
            if job.job_type != "mp3":
                self.app.library_panel.update_status(job.book.id, "error")
            self._set_row(row, job, "", result)

        self._running = None
        self._bridge  = None
        self._update_status_lbl()
        self.pending_changed.emit(self._pending_count())
        self.jobs_changed.emit()
        self._process_next()

    def _cancel_current(self):
        if self._running:
            self.app.converter.cancel()
            row = self._find_row(self._running)
            self._remove_progress_bar(self._running.book.id, row)
            self._running.status = "cancelled"
            self._set_row(row, self._running, "", "")
            self._running = None
        self._btn_start.setEnabled(True)
        self._update_status_lbl()
        self.pending_changed.emit(self._pending_count())
        self.jobs_changed.emit()

    def _cancel_all(self):
        # Annuler la conversion en cours
        if self._running:
            self.app.converter.cancel()
            row = self._find_row(self._running)
            self._remove_progress_bar(self._running.book.id, row)
            self._running.status = "cancelled"
            self._set_row(row, self._running, "", "")
            self._running = None
        # Marquer tous les jobs en attente comme annulés
        for job in self._jobs:
            if job.status == "queued":
                job.status = "cancelled"
                row = self._find_row(job)
                if row >= 0:
                    self._set_row(row, job, "", "")
        self._btn_start.setEnabled(True)
        self._update_status_lbl()
        self.pending_changed.emit(self._pending_count())
        self.jobs_changed.emit()

    def _clear_done(self):
        done_statuses = {"done", "error", "cancelled"}
        to_remove = [j for j in self._jobs if j.status in done_statuses]
        for job in to_remove:
            row = self._find_row(job)
            self._remove_progress_bar(job.book.id, row)
            if row >= 0:
                self._table.removeRow(row)
        self._jobs = [j for j in self._jobs if j.status not in done_statuses]
        self._update_status_lbl()
        self.pending_changed.emit(self._pending_count())
        self.jobs_changed.emit()

    # ── Checkboxes ─────────────────────────────────────────────────────

    def _check_all(self):
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb:
                    cb.setCheckState(Qt.CheckState.Checked)
        finally:
            self._populating = False

    def _uncheck_all(self):
        self._populating = True
        try:
            for row in range(self._table.rowCount()):
                cb = self._table.item(row, COL_CHECK)
                if cb:
                    cb.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._populating = False

    def _on_item_changed(self, item: QTableWidgetItem):
        pass  # checkboxes gérées via _checked_jobs()

    def _checked_jobs(self) -> List[ConversionJob]:
        result = []
        for row in range(self._table.rowCount()):
            cb = self._table.item(row, COL_CHECK)
            ti = self._table.item(row, COL_TITLE)
            if cb and ti and cb.checkState() == Qt.CheckState.Checked:
                book_id = ti.data(Qt.ItemDataRole.UserRole)
                job = next((j for j in self._jobs if j.book.id == book_id), None)
                if job:
                    result.append(job)
        return result

    # ── Progress bar ───────────────────────────────────────────────────

    def _install_progress_bar(self, row: int, book_id: str, value: int,
                              indeterminate: bool = False):
        if book_id not in self._progress_bars:
            pb = QProgressBar()
            pb.setTextVisible(True)
            pb.setStyleSheet(_PROGRESS_STYLE)
            pb.setFixedHeight(20)
            self._progress_bars[book_id] = pb
            self._table.setCellWidget(row, COL_PROG, pb)
        pb = self._progress_bars[book_id]
        if indeterminate:
            pb.setRange(0, 0)   # animation pulsante
        else:
            pb.setRange(0, 100)
            pb.setValue(value)

    def _remove_progress_bar(self, book_id: str, row: int):
        if book_id in self._progress_bars:
            if row >= 0:
                self._table.setCellWidget(row, COL_PROG, None)
            del self._progress_bars[book_id]

    # ── Menu contextuel ────────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint):
        checked = self._checked_jobs()
        if checked:
            self._show_multi_menu(pos, checked)
            return
        job = self._selected_job()
        if not job:
            return
        self._show_single_menu(pos, job)

    def _show_single_menu(self, pos: QPoint, job: ConversionJob):
        menu = QMenu(self)

        if job.status == "done" and job.output_path:
            a = QAction("📂  Ouvrir dans l'Explorateur", menu)
            a.triggered.connect(lambda: _open_in_explorer(job.output_path))
            menu.addAction(a)
            menu.addSeparator()

        if job.status == "error":
            row = self._find_row(job)
            err_item = self._table.item(row, COL_INFO) if row >= 0 else None
            err_text = err_item.text() if err_item else ""
            if err_text:
                a = QAction("📋  Copier l'erreur", menu)
                a.triggered.connect(lambda checked=False, t=err_text: _copy_to_clipboard(t))
                menu.addAction(a)
                menu.addSeparator()

        if job.status in ("queued", "error", "cancelled", "done"):
            menu.addAction("✕  Retirer de la file").triggered.connect(
                lambda: self._remove_job(job))

        if job.status == "queued":
            menu.addAction("⚡  Démarrer maintenant").triggered.connect(self.start_all)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _show_multi_menu(self, pos: QPoint, jobs: List[ConversionJob]):
        n = len(jobs)
        menu = QMenu(self)
        menu.addAction(f"({n} jobs cochés)").setEnabled(False)
        menu.addSeparator()

        removable = [j for j in jobs if j.status in ("queued", "error", "cancelled", "done")]
        if removable:
            menu.addAction(f"✕  Retirer {len(removable)} jobs").triggered.connect(
                lambda: [self._remove_job(j) for j in list(removable)])

        queued = [j for j in jobs if j.status == "queued"]
        if queued:
            menu.addAction(f"⚡  Lancer {len(queued)} jobs en attente").triggered.connect(
                self.start_all)

        menu.addSeparator()
        menu.addAction("☐  Tout décocher").triggered.connect(self._uncheck_all)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _remove_job(self, job: ConversionJob):
        row = self._find_row(job)
        self._remove_progress_bar(job.book.id, row)
        if row >= 0:
            self._table.removeRow(row)
        self._jobs = [j for j in self._jobs if j is not job]
        self._update_status_lbl()
        self.pending_changed.emit(self._pending_count())
        self.jobs_changed.emit()

    # ── Helpers ────────────────────────────────────────────────────────

    def _selected_job(self) -> Optional[ConversionJob]:
        items = self._table.selectedItems()
        if not items:
            return None
        it = self._table.item(items[0].row(), COL_TITLE)
        if it is None:
            return None
        book_id = it.data(Qt.ItemDataRole.UserRole)
        return next((j for j in self._jobs if j.book.id == book_id), None)

    def _find_row(self, job: ConversionJob) -> int:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_TITLE)
            if item and item.data(Qt.ItemDataRole.UserRole) == job.book.id:
                return row
        return -1

    def _set_row(self, row: int, job: ConversionJob, size: str, info: str):
        if row < 0:
            return
        color = STATUS_COLOR.get(job.status, "#888")
        icon  = STATUS_ICON.get(job.status, "○")

        self._populating = True
        try:
            # Checkbox
            cb = self._table.item(row, COL_CHECK)
            if cb is None:
                cb = QTableWidgetItem("")
                cb.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable)
                cb.setCheckState(Qt.CheckState.Unchecked)
                cb.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, COL_CHECK, cb)

            for col, text in [
                (COL_ICON,  icon),
                (COL_TITLE, job.book.display_title),
                (COL_AUTH,  job.book.display_author),
                (COL_SIZE,  size),
                (COL_INFO,  info),
            ]:
                it = self._table.item(row, col)
                if it is None:
                    it = QTableWidgetItem()
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    self._table.setItem(row, col, it)
                it.setText(text)
                it.setForeground(QColor(color))
                if col == COL_ICON:
                    it.setTextAlignment(
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                if col == COL_TITLE:
                    it.setData(Qt.ItemDataRole.UserRole, job.book.id)
                    # Suffixe format pour les jobs MP3
                    display = job.book.display_title
                    if job.job_type == "mp3":
                        display += "  [MP3]"
                    elif job.job_type == "meta":
                        display += "  [Méta]"
                    it.setText(display)
                if col == COL_INFO and text:
                    it.setToolTip(text)

            # Progression : item vide si pas de widget actif
            if job.book.id not in self._progress_bars:
                it = self._table.item(row, COL_PROG)
                if it is None:
                    it = QTableWidgetItem()
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    self._table.setItem(row, COL_PROG, it)
                it.setText("")
        finally:
            self._populating = False

    def _pending_count(self) -> int:
        return sum(1 for j in self._jobs if j.status == "queued")

    def _update_status_lbl(self, converting: Optional[int] = None, eta: str = ""):
        total   = len(self._jobs)
        done    = sum(1 for j in self._jobs if j.status == "done")
        pending = self._pending_count()
        errors  = sum(1 for j in self._jobs if j.status == "error")

        if total == 0:
            self._status_lbl.setText("File vide")
            return
        if converting is not None:
            eta_part = f"  ·  {eta.strip(' —')}" if eta.strip(" —") else ""
            self._status_lbl.setText(
                f"Conversion en cours — {converting}%{eta_part}  ·  "
                f"{done}/{total} terminé{'s' if done != 1 else ''}")
            return

        parts = []
        if done:
            parts.append(f"{done} terminé{'s' if done != 1 else ''}")
        if pending:
            parts.append(f"{pending} en attente")
        if errors:
            parts.append(f"{errors} erreur{'s' if errors != 1 else ''}")
        self._status_lbl.setText("  ·  ".join(parts) if parts else f"{total} jobs")


def _copy_to_clipboard(text: str):
    QApplication.clipboard().setText(text)


def _open_in_explorer(path: str):
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif os.path.isdir(path):
        subprocess.Popen(["explorer", os.path.normpath(path)])
    else:
        parent = os.path.dirname(path)
        if os.path.isdir(parent):
            subprocess.Popen(["explorer", os.path.normpath(parent)])
