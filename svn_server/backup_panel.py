"""Backup Panel — dump/load, hot copy, and retention management.

T-405: all sub-tasks (a-f)
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime

from PySide6.QtCore import QSettings, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_admin_svc as svc
from svn_shared.exceptions import SvnCommandError
from svn_shared.widgets.progress_overlay import ProgressOverlay


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _BackupWorker(QThread):
    finished = Signal(str)  # output path or result message
    error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(str(result) if result else "Done.")
        except (SvnCommandError, OSError) as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Dump / Load tab
# ---------------------------------------------------------------------------

class _DumpLoadTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo_path: str | None = None
        self._setup_ui()

    def set_repo(self, repo_path: str) -> None:
        self._repo_path = repo_path

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        warn = QLabel(
            "⚠  Dump/Load does NOT preserve hook scripts or authz settings. "
            "Use Hot Copy if you need to retain them."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(
            "background:#fff3cd; color:#856404; padding:6px; border:1px solid #ffc107;"
        )
        layout.addWidget(warn)

        # Dump group
        dump_group = QGroupBox("Dump Repository")
        dump_form = QFormLayout(dump_group)

        out_row = QWidget()
        out_layout = QHBoxLayout(out_row)
        out_layout.setContentsMargins(0, 0, 0, 0)
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("Output file path (e.g. /backups/repo.svndump)")
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_output)
        out_layout.addWidget(self._out_edit)
        out_layout.addWidget(browse)
        dump_form.addRow("Output file:", out_row)

        self._incremental_cb = QCheckBox("Incremental dump")
        dump_form.addRow("", self._incremental_cb)

        rev_group = QWidget()
        rev_layout = QHBoxLayout(rev_group)
        rev_layout.setContentsMargins(0, 0, 0, 0)
        self._use_range_cb = QCheckBox("Revision range:")
        self._lower_spin = QSpinBox()
        self._lower_spin.setRange(0, 999999)
        rev_layout.addWidget(self._use_range_cb)
        rev_layout.addWidget(QLabel("from"))
        rev_layout.addWidget(self._lower_spin)
        self._upper_spin = QSpinBox()
        self._upper_spin.setRange(0, 999999)
        self._upper_spin.setValue(999999)
        rev_layout.addWidget(QLabel("to"))
        rev_layout.addWidget(self._upper_spin)
        rev_layout.addStretch()
        dump_form.addRow("", rev_group)

        dump_btn = QPushButton("💾 Start Dump")
        dump_btn.clicked.connect(self._on_dump)
        dump_form.addRow("", dump_btn)
        layout.addWidget(dump_group)

        # Load group
        load_group = QGroupBox("Load Dump File")
        load_form = QFormLayout(load_group)

        in_row = QWidget()
        in_layout = QHBoxLayout(in_row)
        in_layout.setContentsMargins(0, 0, 0, 0)
        self._in_edit = QLineEdit()
        self._in_edit.setPlaceholderText("Input .svndump or .svndump.gz file")
        in_browse = QPushButton("Browse…")
        in_browse.setFixedWidth(80)
        in_browse.clicked.connect(self._browse_input)
        in_layout.addWidget(self._in_edit)
        in_layout.addWidget(in_browse)
        load_form.addRow("Dump file:", in_row)

        load_btn = QPushButton("📥 Start Load")
        load_btn.clicked.connect(self._on_load)
        load_form.addRow("", load_btn)
        layout.addWidget(load_group)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch()

        self._overlay = ProgressOverlay(self)
        self._worker: _BackupWorker | None = None

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Dump File", "", "Dump files (*.svndump);;All files (*)"
        )
        if path:
            self._out_edit.setText(path)

    def _browse_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Dump File", "", "Dump files (*.svndump *.svndump.gz);;All files (*)"
        )
        if path:
            self._in_edit.setText(path)

    def _on_dump(self) -> None:
        if not self._repo_path:
            self._status.setText("No repository selected.")
            return
        out = self._out_edit.text().strip()
        if not out:
            self._status.setText("Specify an output file path.")
            return
        lower = None
        upper = None
        if self._use_range_cb.isChecked():
            lower = self._lower_spin.value()
            upper = self._upper_spin.value()
            # The "to" spinner defaults to 999999, which is far above most repos'
            # actual HEAD revision. svnadmin dump errors out ("Revisions must not
            # be greater than the youngest revision") if asked to dump past HEAD,
            # so clamp the upper bound to the real HEAD revision here.
            try:
                head = svc.repo_info(self._repo_path).head_revision
            except (SvnCommandError, OSError):
                head = None
            if head is not None and upper > head:
                upper = head
            if lower > upper:
                self._status.setText(
                    f"❌ Invalid revision range: {lower}:{upper} (repository HEAD is {head})."
                )
                return
        self._overlay.show_progress("Dumping repository…", indeterminate=True)
        self._worker = _BackupWorker(
            svc.dump, self._repo_path, out,
            incremental=self._incremental_cb.isChecked(),
            lower_rev=lower, upper_rev=upper,
        )
        self._worker.finished.connect(lambda p: (
            self._overlay.hide_progress(),
            self._status.setText(f"✅ Dump complete: {p}"),
        ))
        self._worker.error.connect(lambda e: (
            self._overlay.hide_progress(),
            self._status.setText(f"❌ {e}"),
        ))
        self._worker.start()

    def _on_load(self) -> None:
        if not self._repo_path:
            self._status.setText("No repository selected.")
            return
        inp = self._in_edit.text().strip()
        if not inp:
            self._status.setText("Specify a dump file.")
            return
        self._overlay.show_progress("Loading dump…", indeterminate=True)
        self._worker = _BackupWorker(svc.load, self._repo_path, inp)
        self._worker.finished.connect(lambda _: (
            self._overlay.hide_progress(),
            self._status.setText("✅ Load complete."),
        ))
        self._worker.error.connect(lambda e: (
            self._overlay.hide_progress(),
            self._status.setText(f"❌ {e}"),
        ))
        self._worker.start()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())


# ---------------------------------------------------------------------------
# Hot Copy tab
# ---------------------------------------------------------------------------

class _HotCopyTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo_path: str | None = None
        self._setup_ui()

    def set_repo(self, repo_path: str) -> None:
        self._repo_path = repo_path

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "ℹ  Hot copy creates an online backup that preserves hook scripts, "
            "authz files, and repository history without interrupting service."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#dbeafe; color:#1e3a8a; padding:6px; border:1px solid #93c5fd;"
        )
        layout.addWidget(info)

        group = QGroupBox("Hot Copy")
        form = QFormLayout(group)

        dest_row = QWidget()
        dest_layout = QHBoxLayout(dest_row)
        dest_layout.setContentsMargins(0, 0, 0, 0)
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Destination directory")
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_dest)
        dest_layout.addWidget(self._dest_edit)
        dest_layout.addWidget(browse)
        form.addRow("Destination:", dest_row)

        copy_btn = QPushButton("📋 Start Hot Copy")
        copy_btn.clicked.connect(self._on_hotcopy)
        form.addRow("", copy_btn)
        layout.addWidget(group)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch()

        self._overlay = ProgressOverlay(self)
        self._worker: _BackupWorker | None = None

    def _browse_dest(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Destination")
        if path:
            self._dest_edit.setText(path)

    def _on_hotcopy(self) -> None:
        if not self._repo_path:
            self._status.setText("No repository selected.")
            return
        dest_dir = self._dest_edit.text().strip()
        if not dest_dir:
            self._status.setText("Specify a destination directory.")
            return
        # svnadmin hotcopy refuses to write into an existing non-empty directory, so
        # a raw user-picked folder (likely already containing other backups/files)
        # would fail on the very first run, and re-using the same folder for repeat
        # backups of the same repo would fail on the second run. Nest each hotcopy
        # under a unique, timestamped subfolder instead.
        repo_name = os.path.basename(self._repo_path.rstrip(os.sep))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(dest_dir, f"{repo_name}_{stamp}")
        self._overlay.show_progress("Creating hot copy…", indeterminate=True)
        self._worker = _BackupWorker(svc.hotcopy, self._repo_path, dest)
        self._worker.finished.connect(lambda _: (
            self._overlay.hide_progress(),
            self._status.setText(f"✅ Hot copy complete: {dest}"),
        ))
        self._worker.error.connect(lambda e: (
            self._overlay.hide_progress(),
            self._status.setText(f"❌ {e}"),
        ))
        self._worker.start()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())


# ---------------------------------------------------------------------------
# Retention tab
# ---------------------------------------------------------------------------

class _RetentionTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backup_dir: str | None = None
        self._setup_ui()

    def set_backup_dir(self, path: str) -> None:
        self._backup_dir = path

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("Backup directory to apply retention to")
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self._dir_edit)
        dir_layout.addWidget(browse)
        layout.addWidget(QLabel("Backup directory:"))
        layout.addWidget(dir_row)

        policy_group = QGroupBox("Retention Policy")
        policy_form = QFormLayout(policy_group)

        self._max_age_spin = QSpinBox()
        self._max_age_spin.setRange(0, 3650)
        self._max_age_spin.setValue(30)
        self._max_age_spin.setSuffix(" days")
        self._max_age_spin.setSpecialValueText("Disabled")
        policy_form.addRow("Delete backups older than:", self._max_age_spin)

        self._min_keep_spin = QSpinBox()
        self._min_keep_spin.setRange(0, 100)
        self._min_keep_spin.setValue(3)
        self._min_keep_spin.setSuffix(" copies")
        self._min_keep_spin.setSpecialValueText("No minimum")
        policy_form.addRow("Always keep at least:", self._min_keep_spin)

        layout.addWidget(policy_group)

        apply_btn = QPushButton("🧹 Apply Cleanup")
        apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(apply_btn)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch()

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if path:
            self._dir_edit.setText(path)

    def _on_apply(self) -> None:
        backup_dir = self._dir_edit.text().strip()
        if not backup_dir or not os.path.isdir(backup_dir):
            self._status.setText("Select a valid backup directory.")
            return

        max_age = self._max_age_spin.value()
        min_keep = self._min_keep_spin.value()

        try:
            files = sorted([
                f for f in os.listdir(backup_dir)
                if os.path.isfile(os.path.join(backup_dir, f))
            ], key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))

            removed = 0
            now = datetime.now().timestamp()
            for i, filename in enumerate(files):
                path = os.path.join(backup_dir, filename)
                age_days = (now - os.path.getmtime(path)) / 86400
                remaining = len(files) - i
                if remaining <= min_keep:
                    break
                if max_age > 0 and age_days > max_age:
                    os.remove(path)
                    removed += 1

            self._status.setText(
                f"✅ Cleanup complete. Removed {removed} file(s) from {backup_dir}."
            )
        except OSError as exc:
            self._status.setText(f"❌ {exc}")


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class BackupPanel(QWidget):
    """Backup panel with Dump/Load, Hot Copy, and Retention tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def set_repo(self, repo_path: str) -> None:
        self._dump_tab.set_repo(repo_path)
        self._hotcopy_tab.set_repo(repo_path)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        self._dump_tab = _DumpLoadTab()
        self._hotcopy_tab = _HotCopyTab()
        self._retention_tab = _RetentionTab()

        tabs.addTab(self._dump_tab, "Dump / Load")
        tabs.addTab(self._hotcopy_tab, "Hot Copy")
        tabs.addTab(self._retention_tab, "Retention")
        layout.addWidget(tabs)
