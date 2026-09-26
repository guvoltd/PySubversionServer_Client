"""Branch/tag dialog — create branch/tag and switch working copy.

T-305: all sub-tasks (a-c)
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.svn_client_svc import WCInfo
from svn_shared.exceptions import SvnCommandError
from svn_shared.widgets.progress_overlay import ProgressOverlay

_STANDARD_DIRS = {"trunk", "branches", "tags"}

logger = logging.getLogger(__name__)


def _detect_standard_layout(wc_info: WCInfo) -> tuple[str, bool]:
    """Return (repo_root_url, has_standard_layout).

    Standard layout: root URL contains trunk/, branches/, tags/.
    """
    url = wc_info.url
    repo_root = wc_info.repo_root_url
    has_std = any(f"/{d}/" in url or url.endswith(f"/{d}") for d in _STANDARD_DIRS)
    return repo_root, has_std


def _strip_to_root(url: str) -> str:
    """Strip /trunk or /branches/xxx or /tags/xxx from a URL to get the project root."""
    for segment in _STANDARD_DIRS:
        idx = url.find(f"/{segment}")
        if idx != -1:
            return url[:idx]
    return url


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _CopyWorker(QThread):
    # NOTE: not named `finished` -- see the comment on _CheckoutWorker in
    # checkout_dialog.py. A same-signature Signal() named `finished` on a
    # QThread subclass collides with QThread's own built-in completion
    # signal and fires a second time even after the error path runs.
    succeeded = Signal()
    error = Signal(str)

    def __init__(self, src_url: str, dst_url: str, message: str) -> None:
        super().__init__()
        self._src = src_url
        self._dst = dst_url
        self._msg = message

    def run(self) -> None:
        try:
            svc.copy(self._src, self._dst, self._msg)
            self.succeeded.emit()
        except SvnCommandError as exc:
            logger.error("Branch/tag copy failed: %s", exc)
            self.error.emit(str(exc))
        except Exception as exc:
            logger.exception("Branch/tag copy failed with an unexpected error")
            self.error.emit(f"{type(exc).__name__}: {exc}")


class _SwitchWorker(QThread):
    succeeded = Signal()
    error = Signal(str)

    def __init__(self, wc_path: str, url: str) -> None:
        super().__init__()
        self._wc_path = wc_path
        self._url = url

    def run(self) -> None:
        try:
            svc.switch(self._wc_path, self._url)
            self.succeeded.emit()
        except SvnCommandError as exc:
            logger.error("Working copy switch failed: %s", exc)
            self.error.emit(str(exc))
        except Exception as exc:
            logger.exception("Working copy switch failed with an unexpected error")
            self.error.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Create branch/tag page
# ---------------------------------------------------------------------------

class _CreatePage(QWidget):
    def __init__(self, wc_info: WCInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wc_info = wc_info
        repo_root, has_std = _detect_standard_layout(wc_info)
        project_root = _strip_to_root(wc_info.url) if has_std else wc_info.repo_root_url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form_group = QGroupBox("Create Branch / Tag")
        form = QFormLayout(form_group)

        self._src_edit = QLineEdit(wc_info.url)
        self._src_edit.setToolTip("Source URL to copy from (current working copy URL by default)")
        form.addRow("From URL:", self._src_edit)

        if has_std:
            # Offer pre-filled suggestions
            branch_base = f"{project_root}/branches/"
            tag_base = f"{project_root}/tags/"
        else:
            branch_base = f"{project_root}/"
            tag_base = f"{project_root}/"

        self._dst_edit = QLineEdit(branch_base)
        self._dst_edit.setToolTip("Destination URL for the new branch or tag")
        form.addRow("To URL:", self._dst_edit)

        if has_std:
            hint = QLabel(
                f"Branches: {project_root}/branches/&lt;name&gt;<br>"
                f"Tags:     {project_root}/tags/&lt;name&gt;"
            )
            hint.setStyleSheet("font-size: 11px;")
            form.addRow("", hint)

        self._msg_edit = QLineEdit()
        self._msg_edit.setPlaceholderText("Brief description of this branch/tag")
        form.addRow("Commit message:", self._msg_edit)

        layout.addWidget(form_group)
        layout.addStretch()

    @property
    def src_url(self) -> str:
        return self._src_edit.text().strip()

    @property
    def dst_url(self) -> str:
        return self._dst_edit.text().strip()

    @property
    def message(self) -> str:
        return self._msg_edit.text().strip()

    def is_valid(self) -> bool:
        return bool(self.src_url and self.dst_url and self.message)


# ---------------------------------------------------------------------------
# Switch page
# ---------------------------------------------------------------------------

class _SwitchPage(QWidget):
    def __init__(self, wc_info: WCInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wc_info = wc_info
        _, has_std = _detect_standard_layout(wc_info)
        project_root = _strip_to_root(wc_info.url) if has_std else wc_info.repo_root_url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form_group = QGroupBox("Switch Working Copy")
        form = QFormLayout(form_group)

        self._current_label = QLabel(wc_info.url)
        form.addRow("Current URL:", self._current_label)

        self._target_edit = QLineEdit()
        self._target_edit.setPlaceholderText("URL to switch to (branch, tag, or trunk)")
        form.addRow("Switch to URL:", self._target_edit)

        if has_std:
            hint = QLabel(
                f"Trunk: {project_root}/trunk<br>"
                f"Or enter any branch/tag URL from your repository."
            )
            hint.setStyleSheet("font-size: 11px;")
            form.addRow("", hint)

        layout.addWidget(form_group)
        layout.addStretch()

    @property
    def target_url(self) -> str:
        return self._target_edit.text().strip()

    def is_valid(self) -> bool:
        return bool(self.target_url)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class BranchDialog(QDialog):
    """Branch/tag creation and working-copy switch dialog.

    Signals:
        operation_completed(): emitted after a successful copy or switch.
    """

    operation_completed = Signal()

    def __init__(self, wc_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Branch / Tag")
        self.setMinimumWidth(540)
        self.setModal(True)
        self._wc_path = wc_path
        self._worker: QThread | None = None

        # Fetch WC info synchronously (fast; just parses XML)
        try:
            self._wc_info = svc.info(wc_path)
        except SvnCommandError as exc:
            QMessageBox.critical(None, "Cannot read working copy", str(exc))
            self._wc_info = None  # type: ignore[assignment]

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Mode selector
        mode_row = QWidget()
        mode_layout = QVBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        self._create_radio = QRadioButton("Create Branch / Tag")
        self._switch_radio = QRadioButton("Switch Working Copy to Branch / Tag")
        self._create_radio.setChecked(True)
        self._create_radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self._create_radio)
        mode_layout.addWidget(self._switch_radio)
        layout.addWidget(mode_row)

        # Stacked pages
        self._stack = QStackedWidget()
        if self._wc_info:
            self._create_page = _CreatePage(self._wc_info)
            self._switch_page = _SwitchPage(self._wc_info)
        else:
            self._create_page = QWidget()  # type: ignore[assignment]
            self._switch_page = QWidget()  # type: ignore[assignment]
        self._stack.addWidget(self._create_page)
        self._stack.addWidget(self._switch_page)
        layout.addWidget(self._stack)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Create")
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self._on_cancel)
        layout.addWidget(self._buttons)

        self._overlay = ProgressOverlay(self)

    def _on_mode_changed(self, create_checked: bool) -> None:
        self._stack.setCurrentIndex(0 if create_checked else 1)
        self._ok_btn.setText("Create" if create_checked else "Switch")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        if not self._wc_info:
            self.reject()
            return

        if self._create_radio.isChecked():
            if not self._create_page.is_valid():
                QMessageBox.warning(self, "Incomplete", "Please fill in all fields.")
                return
            self._overlay.show_progress("Creating branch/tag…", indeterminate=True)
            self._ok_btn.setEnabled(False)
            self._worker = _CopyWorker(
                self._create_page.src_url,
                self._create_page.dst_url,
                self._create_page.message,
            )
            self._worker.succeeded.connect(self._on_done)
            self._worker.error.connect(self._on_error)
            self._worker.start()
        else:
            if not self._switch_page.is_valid():
                QMessageBox.warning(self, "Incomplete", "Please enter the target URL.")
                return
            self._overlay.show_progress("Switching working copy…", indeterminate=True)
            self._ok_btn.setEnabled(False)
            self._worker = _SwitchWorker(self._wc_path, self._switch_page.target_url)
            self._worker.succeeded.connect(self._on_done)
            self._worker.error.connect(self._on_error)
            self._worker.start()

    def _on_done(self) -> None:
        self._overlay.hide_progress()
        self.operation_completed.emit()
        self.accept()

    def _on_error(self, msg: str) -> None:
        self._overlay.hide_progress()
        self._ok_btn.setEnabled(True)
        QMessageBox.critical(self, "Operation Failed", msg)

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.reject()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
