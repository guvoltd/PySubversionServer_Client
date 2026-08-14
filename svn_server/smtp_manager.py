"""SMTP Profile Manager — create and test named email notification profiles.

T-404: all sub-tasks (a-f)
"""

from __future__ import annotations

import json
import smtplib
import ssl
from email.mime.text import MIMEText

from PySide6.QtCore import QSettings, QThread, Signal
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
    QVBoxLayout,
    QWidget,
)

_SETTINGS_KEY = "Server/smtp_profiles"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

def _load_profiles() -> list[dict]:
    s = QSettings()
    raw = s.value(_SETTINGS_KEY, "[]")
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []


def _save_profiles(profiles: list[dict]) -> None:
    QSettings().setValue(_SETTINGS_KEY, json.dumps(profiles))


# ---------------------------------------------------------------------------
# Test email worker
# ---------------------------------------------------------------------------

class _TestWorker(QThread):
    success = Signal(str)
    error = Signal(str)

    def __init__(self, profile: dict, to_addr: str) -> None:
        super().__init__()
        self._p = profile
        self._to = to_addr

    def run(self) -> None:
        try:
            msg = MIMEText("This is a test message from SVN Server Admin.")
            msg["Subject"] = "[SVN Server Admin] Test Email"
            msg["From"] = self._p.get("from_addr", "svn@localhost")
            msg["To"] = self._to

            host = self._p.get("host", "localhost")
            port = int(self._p.get("port", 25))
            tls = self._p.get("tls", "None")
            username = self._p.get("username", "")
            password = self._p.get("password", "")

            if tls == "SSL/TLS":
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=ctx) as smtp:
                    if username:
                        smtp.login(username, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port) as smtp:
                    if tls == "STARTTLS":
                        smtp.starttls()
                    if username:
                        smtp.login(username, password)
                    smtp.send_message(msg)

            self.success.emit(f"Test email sent to {self._to}")
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Add/Edit profile dialog
# ---------------------------------------------------------------------------

class _ProfileDialog(QDialog):
    def __init__(self, profile: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SMTP Profile" if not profile else "Edit SMTP Profile")
        self.setMinimumWidth(420)
        self.setModal(True)
        p = profile or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(p.get("name", ""))
        self._name_edit.setPlaceholderText("My Mail Server")
        self._name_edit.textChanged.connect(self._validate)
        form.addRow("Profile name:", self._name_edit)

        self._desc_edit = QLineEdit(p.get("description", ""))
        self._desc_edit.setPlaceholderText("Optional description")
        form.addRow("Description:", self._desc_edit)

        self._host_edit = QLineEdit(p.get("host", ""))
        self._host_edit.setPlaceholderText("smtp.example.com")
        self._host_edit.textChanged.connect(self._validate)
        form.addRow("SMTP server:", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(int(p.get("port", 25)))
        form.addRow("Port:", self._port_spin)

        self._tls_combo = QComboBox()
        self._tls_combo.addItems(["None", "STARTTLS", "SSL/TLS"])
        self._tls_combo.setCurrentText(p.get("tls", "None"))
        self._tls_combo.currentTextChanged.connect(self._on_tls_changed)
        form.addRow("Encryption:", self._tls_combo)

        self._from_edit = QLineEdit(p.get("from_addr", ""))
        self._from_edit.setPlaceholderText("svn@example.com")
        form.addRow("From address:", self._from_edit)

        auth_group = QGroupBox("Authentication")
        auth_form = QFormLayout(auth_group)
        self._anon_cb = QCheckBox("Anonymous (no authentication)")
        self._anon_cb.setChecked(not p.get("username"))
        self._anon_cb.toggled.connect(self._on_anon_toggled)

        self._user_edit = QLineEdit(p.get("username", ""))
        self._user_edit.setPlaceholderText("username")
        self._pass_edit = QLineEdit(p.get("password", ""))
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_edit.setPlaceholderText("password")
        auth_form.addRow("", self._anon_cb)
        auth_form.addRow("Username:", self._user_edit)
        auth_form.addRow("Password:", self._pass_edit)

        layout.addLayout(form)
        layout.addWidget(auth_group)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._on_anon_toggled(self._anon_cb.isChecked())
        self._validate()

    def _validate(self) -> None:
        ok = bool(self._name_edit.text().strip() and self._host_edit.text().strip())
        self._ok_btn.setEnabled(ok)

    def _on_tls_changed(self, tls: str) -> None:
        if tls == "SSL/TLS":
            self._port_spin.setValue(465)
        elif tls == "STARTTLS":
            self._port_spin.setValue(587)
        else:
            self._port_spin.setValue(25)

    def _on_anon_toggled(self, anon: bool) -> None:
        self._user_edit.setEnabled(not anon)
        self._pass_edit.setEnabled(not anon)

    def get_profile(self) -> dict:
        return {
            "name": self._name_edit.text().strip(),
            "description": self._desc_edit.text().strip(),
            "host": self._host_edit.text().strip(),
            "port": self._port_spin.value(),
            "tls": self._tls_combo.currentText(),
            "from_addr": self._from_edit.text().strip(),
            "username": "" if self._anon_cb.isChecked() else self._user_edit.text().strip(),
            "password": "" if self._anon_cb.isChecked() else self._pass_edit.text(),
        }


# ---------------------------------------------------------------------------
# Send test dialog
# ---------------------------------------------------------------------------

class _SendTestDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Send Test Email")
        self.setModal(True)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._to_edit = QLineEdit()
        self._to_edit.setPlaceholderText("recipient@example.com")
        self._to_edit.textChanged.connect(self._validate)
        form.addRow("Send to:", self._to_edit)
        layout.addLayout(form)
        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Send")
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _validate(self) -> None:
        self._ok_btn.setEnabled("@" in self._to_edit.text())

    @property
    def to_address(self) -> str:
        return self._to_edit.text().strip()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class SmtpManager(QWidget):
    """SMTP Profile Manager — add/edit/delete named profiles and send test emails."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profiles: list[dict] = []
        self._worker: _TestWorker | None = None
        self._setup_ui()
        self._load_profiles()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        tb = QWidget()
        tb_layout = QHBoxLayout(tb)
        tb_layout.setContentsMargins(0, 0, 0, 0)

        add_btn = QPushButton("➕ Add Profile")
        add_btn.clicked.connect(self._on_add)
        self._edit_btn = QPushButton("✏ Edit")
        self._edit_btn.clicked.connect(self._on_edit)
        self._edit_btn.setEnabled(False)
        self._del_btn = QPushButton("🗑 Delete")
        self._del_btn.clicked.connect(self._on_delete)
        self._del_btn.setEnabled(False)
        self._test_btn = QPushButton("📧 Send Test Email…")
        self._test_btn.clicked.connect(self._on_send_test)
        self._test_btn.setEnabled(False)

        for w in (add_btn, self._edit_btn, self._del_btn, self._test_btn):
            tb_layout.addWidget(w)
        tb_layout.addStretch()
        layout.addWidget(tb)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection)
        layout.addWidget(self._list)

        # Detail panel
        self._detail_group = QGroupBox("Profile Details")
        detail_form = QFormLayout(self._detail_group)
        self._d_host   = QLabel("—")
        self._d_port   = QLabel("—")
        self._d_tls    = QLabel("—")
        self._d_from   = QLabel("—")
        self._d_auth   = QLabel("—")
        for label, widget in (
            ("Host:", self._d_host), ("Port:", self._d_port),
            ("Encryption:", self._d_tls), ("From:", self._d_from),
            ("Auth:", self._d_auth),
        ):
            detail_form.addRow(label, widget)
        self._detail_group.setVisible(False)
        layout.addWidget(self._detail_group)

        self._test_result = QLabel()
        self._test_result.setWordWrap(True)
        layout.addWidget(self._test_result)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_profiles(self) -> None:
        self._profiles = _load_profiles()
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for p in self._profiles:
            name = p.get("name", "Unnamed")
            desc = p.get("description", "")
            item = QListWidgetItem(f"{name}  —  {desc}" if desc else name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._list.addItem(item)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_selection(self, current: QListWidgetItem | None, _prev) -> None:
        has = current is not None
        self._edit_btn.setEnabled(has)
        self._del_btn.setEnabled(has)
        self._test_btn.setEnabled(has)
        if not has:
            self._detail_group.setVisible(False)
            return
        p = current.data(Qt.ItemDataRole.UserRole)
        self._d_host.setText(p.get("host", "—"))
        self._d_port.setText(str(p.get("port", "—")))
        self._d_tls.setText(p.get("tls", "None"))
        self._d_from.setText(p.get("from_addr", "—"))
        self._d_auth.setText("Anonymous" if not p.get("username") else p.get("username"))
        self._detail_group.setVisible(True)

    def _on_add(self) -> None:
        dlg = _ProfileDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._profiles.append(dlg.get_profile())
            _save_profiles(self._profiles)
            self._refresh_list()

    def _on_edit(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        p = item.data(Qt.ItemDataRole.UserRole)
        idx = next((i for i, x in enumerate(self._profiles) if x is p), -1)
        dlg = _ProfileDialog(profile=p, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and idx >= 0:
            self._profiles[idx] = dlg.get_profile()
            _save_profiles(self._profiles)
            self._refresh_list()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        p = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, "Delete Profile",
                                     f"Delete profile '{p.get('name')}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._profiles = [x for x in self._profiles if x is not p]
            _save_profiles(self._profiles)
            self._refresh_list()
            self._detail_group.setVisible(False)

    def _on_send_test(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        p = item.data(Qt.ItemDataRole.UserRole)
        dlg = _SendTestDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._test_result.setText("Sending test email…")
        self._test_btn.setEnabled(False)
        self._worker = _TestWorker(p, dlg.to_address)
        self._worker.success.connect(self._on_test_success)
        self._worker.error.connect(self._on_test_error)
        self._worker.start()

    def _on_test_success(self, msg: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_result.setText(f"✅ {msg}")
        self._test_result.setStyleSheet("color: #22863a;")

    def _on_test_error(self, msg: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_result.setText(f"❌ {msg}")
        self._test_result.setStyleSheet("color: #cb2431;")
