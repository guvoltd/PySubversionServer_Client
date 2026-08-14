"""Background Job Scheduler — schedule and run SVN backup/verify jobs.

T-406: all sub-tasks (a-i)
"""

from __future__ import annotations
import logging

import json
import subprocess
from datetime import datetime
from typing import Any

from PySide6.QtCore import QSettings, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtCore import QTime

import svn_shared.svn_admin_svc as svc
from svn_shared.exceptions import SvnCommandError

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "Server/scheduled_jobs"
_HISTORY_KEY  = "Server/job_history"
_MAX_HISTORY  = 20

_JOB_TYPES = ["Full Backup", "Incremental Backup", "Verify Repository"]
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_STATUS_STYLES = {
    "Success": "color:#22863a; font-weight:bold;",
    "Error":   "color:#cb2431; font-weight:bold;",
    "Running": "color:#0366d6; font-weight:bold;",
}

# Crontab day-of-week: Mon=1 ... Sun=7 (ISO) → cron 0=Sun,1=Mon,...
_CRON_DOW = {
    "Monday": "1", "Tuesday": "2", "Wednesday": "3",
    "Thursday": "4", "Friday": "5", "Saturday": "6", "Sunday": "0",
}


def _load_jobs() -> list[dict]:
    raw = QSettings().value(_SETTINGS_KEY, "[]")
    logger.debug("Loading jobs from QSettings key '%s'", _SETTINGS_KEY)
    try:
        jobs = json.loads(raw) if isinstance(raw, str) else (raw or [])
        logger.debug("Loaded %d jobs.", len(jobs))
        return jobs
    except Exception as e:
        logger.error("Failed to parse jobs JSON: %s", e)
        return []


def _save_jobs(jobs: list[dict]) -> None:
    logger.debug("Saving %d jobs to QSettings key '%s'", len(jobs), _SETTINGS_KEY)
    QSettings().setValue(_SETTINGS_KEY, json.dumps(jobs))


def _load_history() -> list[dict]:
    raw = QSettings().value(_HISTORY_KEY, "[]")
    logger.debug("Loading job history from QSettings key '%s'", _HISTORY_KEY)
    try:
        history = json.loads(raw) if isinstance(raw, str) else (raw or [])
        logger.debug("Loaded %d history entries.", len(history))
        return history
    except Exception as e:
        logger.error("Failed to parse job history JSON: %s", e)
        return []


def _save_history(history: list[dict]) -> None:
    logger.debug("Saving %d history entries (max %d) to QSettings key '%s'", len(history), _MAX_HISTORY, _HISTORY_KEY)
    QSettings().setValue(_HISTORY_KEY, json.dumps(history[-_MAX_HISTORY:]))


def _crontab_line(job: dict) -> str:
    t = job.get("time", "01:00")
    hour, minute = t.split(":") if ":" in t else ("1", "0")
    dow = _CRON_DOW.get(job.get("day", "Saturday"), "6")
    repo = job.get("repos", "ALL")
    job_type = job.get("type", "Full Backup")
    comment = f"# SVN {job_type} — {repo}"
    if job_type == "Verify Repository":
        cmd = f'svnadmin verify "{repo}"'
    else:
        # A fixed ".bak" destination only works the first time this line runs: svnadmin
        # hotcopy refuses to write into an existing non-empty directory, so every run
        # after the first would fail. Compute a fresh timestamp at cron execution time
        # (matches the in-app "Run Now" behavior — see _RunWorker.run above).
        cmd = f'svnadmin hotcopy "{repo}" "{repo}.bak.$(date +\\%Y\\%m\\%d\\%H\\%M\\%S)"'
    return f"{comment}\n{minute} {hour} * * {dow} {cmd}"


# ---------------------------------------------------------------------------
# Run-now worker
# ---------------------------------------------------------------------------

class _RunWorker(QThread):
    finished = Signal(str, str)  # job_name, status ("Success" / "Error: …")
    error = Signal(str)

    def __init__(self, job: dict, repo_root: str) -> None:
        super().__init__()
        self._job = job
        self._repo_root = repo_root

    def run(self) -> None:
        job_type = self._job.get("type", "Full Backup")
        repos_setting = self._job.get("repos", "ALL")
        name = self._job.get("name", job_type)
        logger.info("Worker starting job '%s'. Type: %s, Repos: %s", name, job_type, repos_setting)

        try:
            import os
            if repos_setting == "ALL":
                logger.debug("Job is for ALL repositories. Scanning root: %s", self._repo_root)
                if self._repo_root and os.path.isdir(self._repo_root):
                    repos = [
                        os.path.join(self._repo_root, d)
                        for d in os.listdir(self._repo_root)
                        if os.path.isdir(os.path.join(self._repo_root, d))
                    ]
                    logger.debug("Found %d repositories to process.", len(repos))
                else:
                    repos = []
                    logger.warning("Repository root is not set or not a directory.")
            else:
                repos = [repos_setting]
                logger.debug("Job is for a single repository: %s", repos_setting)

            for repo in repos:
                logger.debug("Processing repo: %s", repo)
                if job_type == "Full Backup":
                    # A fixed ".bak" destination only works once: svnadmin hotcopy
                    # refuses to write into an existing non-empty directory, so every
                    # run after the first of this (recurring, scheduled) job type would
                    # fail. Timestamp it, same as the Incremental Backup case below, and
                    # let the Retention tab prune old copies.
                    dest = repo + f".full.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    logger.debug("Performing full backup (hotcopy) to: %s", dest)
                    svc.hotcopy(repo, dest)
                elif job_type == "Incremental Backup":
                    dest = repo + f".incr.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    logger.debug("Performing incremental backup (hotcopy) to: %s", dest)
                    svc.hotcopy(repo, dest)
                elif job_type == "Verify Repository":
                    logger.debug("Performing repository verification.")
                    svc.verify(repo)
                else:
                    logger.warning("Unknown job type '%s', skipping.", job_type)

            logger.info("Job '%s' finished successfully.", name)
            self.finished.emit(name, "Success")
        except Exception as exc:
            logger.error("Job '%s' failed: %s", name, exc, exc_info=True)
            self.finished.emit(name, f"Error: {exc}")


# ---------------------------------------------------------------------------
# Create / Edit job dialog
# ---------------------------------------------------------------------------

class _JobDialog(QDialog):
    def __init__(self, job: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Job" if not job else "Edit Job")
        logger.debug("Opening _JobDialog. Editing job: %s", job.get("name") if job else "False")
        self.setMinimumWidth(440)
        self.setModal(True)
        j = job or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(j.get("name", ""))
        self._name_edit.setPlaceholderText("Weekly Full Backup")
        self._name_edit.textChanged.connect(self._validate)
        form.addRow("Job name:", self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(_JOB_TYPES)
        self._type_combo.setCurrentText(j.get("type", "Full Backup"))
        form.addRow("Job type:", self._type_combo)

        repos_group = QGroupBox("Repository Selection")
        repos_layout = QVBoxLayout(repos_group)
        self._all_repos_cb = QCheckBox("All Repositories")
        self._all_repos_cb.setChecked(j.get("repos", "ALL") == "ALL")
        self._all_repos_cb.toggled.connect(self._on_all_repos_toggled)
        repos_layout.addWidget(self._all_repos_cb)
        self._repo_path_edit = QLineEdit(j.get("repos", "") if j.get("repos") != "ALL" else "")
        self._repo_path_edit.setPlaceholderText("Repository path")
        repos_layout.addWidget(self._repo_path_edit)

        layout.addLayout(form)
        layout.addWidget(repos_group)

        sched_group = QGroupBox("Schedule")
        sched_form = QFormLayout(sched_group)

        self._day_combo = QComboBox()
        self._day_combo.addItems(_DAYS)
        self._day_combo.setCurrentText(j.get("day", "Saturday"))
        sched_form.addRow("Day of week:", self._day_combo)

        t_str = j.get("time", "01:00")
        h, m = (int(x) for x in t_str.split(":")) if ":" in t_str else (1, 0)
        self._time_edit = QTimeEdit()
        self._time_edit.setTime(QTime(h, m))
        self._time_edit.setDisplayFormat("HH:mm")
        sched_form.addRow("Time:", self._time_edit)

        layout.addWidget(sched_group)

        notif_group = QGroupBox("Notifications")
        notif_form = QFormLayout(notif_group)
        self._notif_combo = QComboBox()
        self._notif_combo.addItems(["Never", "Error", "Warning", "Success"])
        self._notif_combo.setCurrentText(j.get("notify", "Error"))
        notif_form.addRow("Notify on:", self._notif_combo)
        self._email_edit = QLineEdit(j.get("notify_email", ""))
        self._email_edit.setPlaceholderText("admin@example.com")
        notif_form.addRow("Email:", self._email_edit)
        layout.addWidget(notif_group)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._on_all_repos_toggled(self._all_repos_cb.isChecked())
        self._validate()

    def _validate(self) -> None:
        self._ok_btn.setEnabled(bool(self._name_edit.text().strip()))

    def _on_all_repos_toggled(self, all_: bool) -> None:
        self._repo_path_edit.setEnabled(not all_)

    def get_job(self) -> dict:
        repos = "ALL" if self._all_repos_cb.isChecked() else self._repo_path_edit.text().strip()
        t = self._time_edit.time()
        job_data = {
            "name": self._name_edit.text().strip(),
            "type": self._type_combo.currentText(),
            "repos": repos,
            "day": self._day_combo.currentText(),
            "time": f"{t.hour():02d}:{t.minute():02d}",
            "notify": self._notif_combo.currentText(),
            "notify_email": self._email_edit.text().strip(),
        }
        logger.debug("Returning job data from dialog: %s", job_data)
        return job_data


# ---------------------------------------------------------------------------
# Crontab line viewer
# ---------------------------------------------------------------------------

class _CrontabDialog(QDialog):
    def __init__(self, crontab_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crontab Entry")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Add the following line(s) to your crontab (crontab -e):"))
        self._text = QTextEdit()
        self._text.setPlainText(crontab_text)
        self._text.setReadOnly(True)
        self._text.setFont(self._mono_font())
        layout.addWidget(self._text)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        copy_btn = QPushButton("📋 Copy to Clipboard")
        from PySide6.QtWidgets import QApplication
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(crontab_text))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addWidget(btn_row)

    @staticmethod
    def _mono_font():
        from PySide6.QtGui import QFont
        f = QFont("Monospace")
        f.setStyleHint(QFont.StyleHint.TypeWriter)
        return f


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class JobScheduler(QWidget):
    """Background job scheduler — configure, run, and track SVN maintenance jobs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._jobs: list[dict] = []
        self._repo_root: str = ""
        self._worker: _RunWorker | None = None
        self._setup_ui()
        self._load()

    def set_repo_root(self, root: str) -> None:
        logger.debug("JobScheduler repo root set to: %s", root)
        self._repo_root = root

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        tb = QWidget()
        tb_layout = QHBoxLayout(tb)
        tb_layout.setContentsMargins(4, 4, 4, 4)

        create_btn = QPushButton("➕ Create Job")
        create_btn.clicked.connect(self._on_create)
        self._edit_btn = QPushButton("✏ Edit")
        self._edit_btn.clicked.connect(self._on_edit)
        self._edit_btn.setEnabled(False)
        self._del_btn = QPushButton("🗑 Delete")
        self._del_btn.clicked.connect(self._on_delete)
        self._del_btn.setEnabled(False)
        self._run_btn = QPushButton("▶ Run Now")
        self._run_btn.clicked.connect(self._on_run_now)
        self._run_btn.setEnabled(False)
        self._cron_btn = QPushButton("📋 Show Crontab")
        self._cron_btn.clicked.connect(self._on_show_crontab)
        self._cron_btn.setEnabled(False)

        for w in (create_btn, self._edit_btn, self._del_btn, self._run_btn, self._cron_btn):
            tb_layout.addWidget(w)
        tb_layout.addStretch()
        layout.addWidget(tb)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Job table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Name", "Type", "Repositories", "Schedule", "Last Status"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self._table)

        # History panel
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(4, 4, 4, 4)
        history_layout.addWidget(QLabel("<b>Job History (last 20 runs)</b>"))
        self._history_table = QTableWidget(0, 4)
        self._history_table.setHorizontalHeaderLabels(["Job", "Time", "Duration", "Status"])
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self._history_table)
        splitter.addWidget(history_widget)

        splitter.setSizes([300, 200])
        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load(self) -> None:
        logger.info("Loading jobs and history for JobScheduler UI.")
        self._jobs = _load_jobs()
        self._refresh_table()
        self._refresh_history()

    def _refresh_table(self) -> None:
        self._table.setRowCount(len(self._jobs))
        for i, job in enumerate(self._jobs):
            self._table.setItem(i, 0, QTableWidgetItem(job.get("name", "")))
            self._table.setItem(i, 1, QTableWidgetItem(job.get("type", "")))
            repos = job.get("repos", "ALL")
            self._table.setItem(i, 2, QTableWidgetItem(repos))
            sched = f"{job.get('day', '?')} {job.get('time', '?')}"
            self._table.setItem(i, 3, QTableWidgetItem(sched))
            status = job.get("last_status", "—")
            status_item = QTableWidgetItem(status)
            if status.startswith("Error"):
                status_item.setForeground(Qt.GlobalColor.red)
            elif status == "Success":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            self._table.setItem(i, 4, status_item)

    def _refresh_history(self) -> None:
        history = _load_history()
        self._history_table.setRowCount(len(history))
        for i, entry in enumerate(reversed(history)):
            self._history_table.setItem(i, 0, QTableWidgetItem(entry.get("job", "")))
            self._history_table.setItem(i, 1, QTableWidgetItem(entry.get("time", "")))
            self._history_table.setItem(i, 2, QTableWidgetItem(entry.get("duration", "")))
            status = entry.get("status", "")
            item = QTableWidgetItem(status)
            if status.startswith("Error"):
                item.setForeground(Qt.GlobalColor.red)
            elif status == "Success":
                item.setForeground(Qt.GlobalColor.darkGreen)
            self._history_table.setItem(i, 3, item)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_selection(self) -> None:
        has = bool(self._table.selectedItems())
        self._edit_btn.setEnabled(has)
        self._del_btn.setEnabled(has)
        self._run_btn.setEnabled(has)
        self._cron_btn.setEnabled(has)

    def _current_job_idx(self) -> int:
        rows = self._table.selectedItems()
        return self._table.row(rows[0]) if rows else -1

    def _on_create(self) -> None:
        logger.debug("Create Job button clicked.")
        dlg = _JobDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_job = dlg.get_job()
            logger.info("Adding new job: %s", new_job.get("name"))
            self._jobs.append(new_job)
            _save_jobs(self._jobs)
            self._refresh_table()

    def _on_edit(self) -> None:
        idx = self._current_job_idx()
        if idx < 0:
            return
        logger.debug("Edit Job button clicked for job at index %d.", idx)
        dlg = _JobDialog(job=self._jobs[idx], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            edited_job = dlg.get_job()
            logger.info("Saving edited job: %s", edited_job.get("name"))
            self._jobs[idx] = edited_job
            _save_jobs(self._jobs)
            self._refresh_table()

    def _on_delete(self) -> None:
        idx = self._current_job_idx()
        if idx < 0:
            return
        name = self._jobs[idx].get("name", "")
        logger.debug("Delete Job button clicked for job: %s", name)
        reply = QMessageBox.question(self, "Delete Job", f"Delete job '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Deleting job: %s", name)
            self._jobs.pop(idx)
            _save_jobs(self._jobs)
            self._refresh_table()
        else:
            logger.debug("Job deletion cancelled by user.")

    def _on_run_now(self) -> None:
        idx = self._current_job_idx()
        if idx < 0:
            return
        job = self._jobs[idx]
        logger.info("Manually running job: %s", job.get("name"))
        self._run_btn.setEnabled(False)
        start_time = datetime.now()
        self._worker = _RunWorker(job, self._repo_root)
        self._worker.finished.connect(
            lambda name, status: self._on_run_done(idx, name, status, start_time)
        )
        self._worker.start()

    def _on_run_done(self, idx: int, name: str, status: str, start_time: datetime) -> None:
        duration = (datetime.now() - start_time).total_seconds()
        logger.info("Job run finished. Name: %s, Status: %s, Duration: %.1fs", name, status, duration)
        self._jobs[idx]["last_status"] = status
        _save_jobs(self._jobs)

        history = _load_history()
        history.append({
            "job": name,
            "time": start_time.strftime("%Y-%m-%d %H:%M"),
            "duration": f"{duration:.1f}s",
            "status": status,
        })
        _save_history(history)

        self._refresh_table()
        self._refresh_history()
        self._run_btn.setEnabled(True)
        QMessageBox.information(self, "Job Complete", f"{name}: {status}")

    def _on_show_crontab(self) -> None:
        idx = self._current_job_idx()
        if idx < 0:
            return
        logger.debug("Show Crontab button clicked.")
        cron_text = _crontab_line(self._jobs[idx])
        dlg = _CrontabDialog(cron_text, self)
        dlg.exec()
