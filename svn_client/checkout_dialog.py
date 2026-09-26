"""Checkout dialog — URL, local path, revision, progress, credential prompt.

T-303: all sub-tasks (a-e)
"""

from __future__ import annotations

import logging
import re

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.exceptions import SvnAuthError, SvnCommandError
from svn_shared.widgets.progress_overlay import ProgressOverlay

_URL_RE = re.compile(r"^(svn|http|https|file)://\S+", re.IGNORECASE)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _CheckoutWorker(QThread):
    line_received = Signal(str)
    # NOTE: deliberately not named `finished` -- QThread already has a built-in
    # no-arg `finished` signal emitted whenever run() returns (success OR a
    # caught exception). A same-signature custom Signal() of that exact name
    # collides with it, so it fires a second time even on the error path,
    # silently overwriting the error UI with a false "succeeded" outcome.
    succeeded = Signal()
    error = Signal(str)
    auth_error = Signal(str)

    def __init__(
        self,
        url: str,
        path: str,
        revision: str | None,
        username: str | None,
        password: str | None,
    ) -> None:
        super().__init__()
        self._url = url
        self._path = path
        self._revision = revision
        self._username = username
        self._password = password

    def run(self) -> None:
        logger.info(
            "Checkout starting: url=%s path=%s revision=%s",
            self._url, self._path, self._revision or "HEAD",
        )
        try:
            svc.checkout(
                self._url,
                self._path,
                revision=self._revision,
                username=self._username,
                password=self._password,
            )
            logger.info("Checkout finished: path=%s", self._path)
            self.succeeded.emit()
        except SvnAuthError as exc:
            logger.warning("Checkout auth failed: %s", exc)
            self.auth_error.emit(str(exc))
        except SvnCommandError as exc:
            logger.error("Checkout command failed: %s", exc)
            self.error.emit(str(exc))
        except Exception as exc:
            # Catch-all: anything else (bad-argument ValueError, missing `svn`
            # binary, permission errors, ...) must still reach the UI instead
            # of dying silently inside this thread with no visible feedback.
            logger.exception("Checkout failed with an unexpected error")
            self.error.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Credential sub-dialog
# ---------------------------------------------------------------------------

class _CredentialDialog(QDialog):
    """Prompt user for SVN username and password."""

    def __init__(self, realm: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Authentication Required")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Authentication required for:\n{realm}"))

        form = QFormLayout()
        self._user_edit = QLineEdit()
        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username:", self._user_edit)
        form.addRow("Password:", self._pass_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def username(self) -> str:
        return self._user_edit.text().strip()

    @property
    def password(self) -> str:
        return self._pass_edit.text()


# ---------------------------------------------------------------------------
# Checkout dialog
# ---------------------------------------------------------------------------

class CheckoutDialog(QDialog):
    """Checkout wizard: URL, local path, revision, progress feedback.

    Signals:
        checkout_completed(local_path): emitted after successful checkout.
    """

    checkout_completed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Checkout Repository")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._worker: _CheckoutWorker | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Repository group
        repo_group = QGroupBox("Repository")
        repo_form = QFormLayout(repo_group)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("svn://host/repo  or  https://host/repo")
        self._url_edit.textChanged.connect(self._validate)
        repo_form.addRow("URL:", self._url_edit)

        self._url_error = QLabel()
        self._url_error.setStyleSheet("color: red; font-size: 11px;")
        repo_form.addRow("", self._url_error)
        layout.addWidget(repo_group)

        # Local path group
        path_group = QGroupBox("Local Path")
        path_form = QFormLayout(path_group)

        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Directory where the working copy will be created")
        self._path_edit.textChanged.connect(self._validate)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_path)
        path_layout.addWidget(self._path_edit)
        path_layout.addWidget(browse)
        path_form.addRow("Path:", path_row)
        layout.addWidget(path_group)

        # Revision group
        rev_group = QGroupBox("Revision")
        rev_layout = QVBoxLayout(rev_group)

        self._head_radio = QRadioButton("HEAD (latest)")
        self._head_radio.setChecked(True)
        self._specific_radio = QRadioButton("Specific revision:")

        rev_row = QWidget()
        rev_row_layout = QHBoxLayout(rev_row)
        rev_row_layout.setContentsMargins(0, 0, 0, 0)
        rev_row_layout.addWidget(self._specific_radio)
        self._rev_spin = QSpinBox()
        self._rev_spin.setRange(1, 999_999)
        self._rev_spin.setEnabled(False)
        self._specific_radio.toggled.connect(self._rev_spin.setEnabled)
        rev_row_layout.addWidget(self._rev_spin)
        rev_row_layout.addStretch()

        rev_layout.addWidget(self._head_radio)
        rev_layout.addWidget(rev_row)
        layout.addWidget(rev_group)

        # Progress log
        self._log_label = QLabel()
        self._log_label.setStyleSheet("font-size: 11px; padding: 2px;")
        self._log_label.setWordWrap(True)
        layout.addWidget(self._log_label)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Checkout")
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self._on_checkout)
        self._buttons.rejected.connect(self._on_cancel)
        layout.addWidget(self._buttons)

        # Progress overlay
        self._overlay = ProgressOverlay(self)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        url = self._url_edit.text().strip()
        path = self._path_edit.text().strip()
        url_ok = bool(_URL_RE.match(url))
        self._url_error.setText("" if url_ok or not url else "URL must start with svn://, http://, https://, or file://")
        self._ok_btn.setEnabled(url_ok and bool(path))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Checkout Directory")
        if path:
            self._path_edit.setText(path)

    def _on_checkout(self) -> None:
        url = self._url_edit.text().strip()
        path = self._path_edit.text().strip()
        revision = None if self._head_radio.isChecked() else str(self._rev_spin.value())
        self._start_worker(url, path, revision)

    def _start_worker(self, url: str, path: str, revision: str | None) -> None:
        logger.debug("_start_worker: url=%s path=%s revision=%s", url, path, revision)
        self._ok_btn.setEnabled(False)
        self._log_label.setText("Starting checkout…")
        self._overlay.show_progress("Checking out…", indeterminate=True)

        self._worker = _CheckoutWorker(url, path, revision, self._username, self._password)
        self._worker.succeeded.connect(lambda: self._on_done(path))
        self._worker.error.connect(self._on_error)
        self._worker.auth_error.connect(lambda msg: self._on_auth_error(url, path, revision, msg))
        self._worker.start()

    def _on_done(self, path: str) -> None:
        logger.debug("_on_done: checkout completed at %s", path)
        self._overlay.hide_progress()
        self._log_label.setText(f"Checkout complete: {path}")
        self.checkout_completed.emit(path)
        self.accept()

    def _on_error(self, msg: str) -> None:
        logger.debug("_on_error: %s", msg)
        self._overlay.hide_progress()
        self._ok_btn.setEnabled(True)
        self._log_label.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Checkout Failed", msg)

    def _on_auth_error(self, url: str, path: str, revision: str | None, msg: str) -> None:
        logger.debug("_on_auth_error for %s: %s", url, msg)
        self._overlay.hide_progress()
        cred_dlg = _CredentialDialog(url, self)
        if cred_dlg.exec() == QDialog.DialogCode.Accepted:
            self._username = cred_dlg.username
            self._password = cred_dlg.password
            self._start_worker(url, path, revision)
        else:
            self._ok_btn.setEnabled(True)
            self._log_label.setText("Checkout cancelled: authentication required.")

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.reject()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
