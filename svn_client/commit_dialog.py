"""Commit dialog — file selection, message editor, diff preview, recent messages.

T-304: all sub-tasks (a-e)
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.svn_client_svc import StatusEntry
from svn_shared.exceptions import SvnCommandError
from svn_shared.widgets.progress_overlay import ProgressOverlay

from svn_client.diff_viewer import DiffViewer

_RECENT_KEY = "Client/recent_messages"
_MAX_RECENT = 10

# statuses that should appear in the commit file list
_COMMITTABLE = {"modified", "added", "deleted", "replaced", "missing"}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _CommitWorker(QThread):
    finished = Signal(int)   # committed revision
    error = Signal(str)

    def __init__(self, wc_path: str, message: str, files: list[str]) -> None:
        super().__init__()
        self._wc_path = wc_path
        self._message = message
        self._files = files

    def run(self) -> None:
        try:
            rev = svc.commit(self._wc_path, self._message, self._files or None)
            self.finished.emit(rev)
        except SvnCommandError as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# File list widget
# ---------------------------------------------------------------------------

class _FileList(QWidget):
    """Checkable list of files to include in the commit."""

    selection_changed = Signal()

    def __init__(self, entries: list[StatusEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Select-all / none row
        ctrl_row = QWidget()
        ctrl_layout = QHBoxLayout(ctrl_row)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        select_all = QPushButton("Select All")
        select_all.setFixedHeight(22)
        select_none = QPushButton("Select None")
        select_none.setFixedHeight(22)
        select_all.clicked.connect(self._select_all)
        select_none.clicked.connect(self._select_none)
        ctrl_layout.addWidget(select_all)
        ctrl_layout.addWidget(select_none)
        ctrl_layout.addStretch()
        layout.addWidget(ctrl_row)

        self._list = QListWidget()
        self._list.itemChanged.connect(lambda _: self.selection_changed.emit())
        layout.addWidget(self._list)

        for entry in entries:
            if entry.status not in _COMMITTABLE:
                continue
            item = QListWidgetItem(f"[{entry.status[0].upper()}]  {entry.path}")
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(entry.path)
            self._list.addItem(item)

    def checked_paths(self) -> list[str]:
        paths = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return paths

    def selected_path(self) -> str | None:
        items = self._list.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _select_all(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)


# ---------------------------------------------------------------------------
# Commit dialog
# ---------------------------------------------------------------------------

class CommitDialog(QDialog):
    """Commit dialog with file selector, message editor, and diff preview.

    Signals:
        commit_completed(revision): emitted after a successful commit.
    """

    commit_completed = Signal(int)

    def __init__(
        self,
        wc_path: str,
        entries: list[StatusEntry],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Commit — {wc_path}")
        self.setMinimumSize(780, 560)
        self.setModal(True)
        self._wc_path = wc_path
        self._entries = entries
        self._worker: _CommitWorker | None = None
        self._setup_ui()
        self._validate()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Recent messages dropdown
        recent_row = QWidget()
        recent_layout = QHBoxLayout(recent_row)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.addWidget(QLabel("Recent messages:"))
        self._recent_combo = QComboBox()
        self._recent_combo.setMinimumWidth(300)
        self._recent_combo.addItem("— select a recent message —")
        for msg in self._load_recent():
            self._recent_combo.addItem(msg[:80] + ("…" if len(msg) > 80 else ""), msg)
        self._recent_combo.currentIndexChanged.connect(self._on_recent_selected)
        recent_layout.addWidget(self._recent_combo)
        recent_layout.addStretch()
        layout.addWidget(recent_row)

        # Horizontal splitter: file list (left) | right side
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: file list
        self._file_list = _FileList(self._entries)
        self._file_list.selection_changed.connect(self._validate)
        self._file_list._list.currentItemChanged.connect(self._on_file_selected)
        main_splitter.addWidget(self._file_list)

        # Right: message + diff preview
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        right_layout.addWidget(QLabel("Commit message:"))
        self._msg_edit = QPlainTextEdit()
        self._msg_edit.setPlaceholderText("Describe what this commit does…")
        self._msg_edit.setMaximumHeight(100)
        self._msg_edit.textChanged.connect(self._validate)
        right_layout.addWidget(self._msg_edit)

        right_layout.addWidget(QLabel("Diff preview (selected file):"))
        self._diff_viewer = DiffViewer()
        right_layout.addWidget(self._diff_viewer)

        main_splitter.addWidget(right)
        main_splitter.setSizes([220, 560])
        layout.addWidget(main_splitter)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._commit_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._commit_btn.setText("Commit")
        self._commit_btn.setEnabled(False)
        self._buttons.accepted.connect(self._on_commit)
        self._buttons.rejected.connect(self._on_cancel)
        layout.addWidget(self._buttons)

        # Progress overlay
        self._overlay = ProgressOverlay(self)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_recent_selected(self, index: int) -> None:
        if index <= 0:
            return
        msg = self._recent_combo.itemData(index)
        if msg:
            self._msg_edit.setPlainText(msg)
        self._recent_combo.setCurrentIndex(0)

    def _on_file_selected(self, current, previous) -> None:
        if not current:
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path and self._wc_path:
            self._diff_viewer.load_from_wc(self._wc_path, file_path=path)

    def _validate(self) -> None:
        has_message = bool(self._msg_edit.toPlainText().strip())
        has_files = bool(self._file_list.checked_paths())
        self._commit_btn.setEnabled(has_message and has_files)

    def _on_commit(self) -> None:
        message = self._msg_edit.toPlainText().strip()
        files = self._file_list.checked_paths()
        self._commit_btn.setEnabled(False)
        self._overlay.show_progress("Committing…", indeterminate=True)

        self._worker = _CommitWorker(self._wc_path, message, files)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, revision: int) -> None:
        self._overlay.hide_progress()
        msg = self._msg_edit.toPlainText().strip()
        self._save_recent(msg)
        self.commit_completed.emit(revision)
        QMessageBox.information(self, "Committed", f"Committed revision {revision}.")
        self.accept()

    def _on_error(self, msg: str) -> None:
        self._overlay.hide_progress()
        self._commit_btn.setEnabled(True)
        QMessageBox.critical(self, "Commit Failed", msg)

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.reject()

    # ------------------------------------------------------------------
    # Recent messages persistence
    # ------------------------------------------------------------------

    def _load_recent(self) -> list[str]:
        s = QSettings()
        msgs = s.value(_RECENT_KEY, [])
        return msgs if isinstance(msgs, list) else []

    def _save_recent(self, message: str) -> None:
        if not message:
            return
        s = QSettings()
        msgs: list[str] = s.value(_RECENT_KEY, [])
        if not isinstance(msgs, list):
            msgs = []
        if message in msgs:
            msgs.remove(message)
        msgs.insert(0, message)
        s.setValue(_RECENT_KEY, msgs[:_MAX_RECENT])

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
