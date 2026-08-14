"""Service & Performance Panel — svnserve status, config snippets, performance settings.

T-407: all sub-tasks (a-e)
"""

from __future__ import annotations
import os
import re
import subprocess

from PySide6.QtCore import QSettings, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton, QVBoxLayout,
    QSlider,
    QTabWidget,
    QWidget,
    QMessageBox,
)

import svn_shared.svn_admin_svc as svc # Added import for svc.check_group_exists and svc.check_user_exists
from svn_shared.exceptions import SvnCommandError # Added import for SvnCommandError

from svn_shared.widgets.pkexec_runner import PkexecRunnerDialog


# ---------------------------------------------------------------------------
# systemd unit template
# ---------------------------------------------------------------------------

_SYSTEMD_UNIT = """\
[Unit]
Description=Subversion Repository Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/svnserve --daemon --foreground --root %%REPO_ROOT%%
Restart=on-failure
User=%%SVN_USER%%

[Install]
WantedBy=multi-user.target
"""

_ASCII_RE = re.compile(r"^[\x20-\x7E]+$")
_PASSWD_COMPLEX_RE = re.compile(
    r"(?=.*[A-Z])(?=.*[a-z])(?=.*\d)|"
    r"(?=.*[A-Z])(?=.*[a-z])(?=.*[^A-Za-z\d])|"
    r"(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d])|"
    r"(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z\d])"
)


def _validate_password(password: str, min_len: int, complexity: bool) -> str | None:
    """Return error string or None if password is valid."""
    if not password:
        return "Password cannot be empty."
    if not _ASCII_RE.match(password):
        return "Password must contain only ASCII printable characters."
    if len(password) < min_len:
        return f"Password must be at least {min_len} characters."
    if complexity and not _PASSWD_COMPLEX_RE.search(password):
        return "Password must use 3 of 4 character types: A-Z, a-z, 0-9, special."
    return None


# ---------------------------------------------------------------------------
# Service status worker
# ---------------------------------------------------------------------------

class _StatusWorker(QThread):
    result = Signal(bool, str)  # is_active, status_text (e.g., "active", "inactive")

    def run(self) -> None:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", "svnserve"],
                capture_output=True, text=True, timeout=5
            )
            active = r.returncode == 0
            status = r.stdout.strip() or r.stderr.strip() or "unknown"
            self.result.emit(active, status)
        except FileNotFoundError:
            # systemctl not available — try process detection
            try:
                r2 = subprocess.run(
                    ["pgrep", "-x", "svnserve"],
                    capture_output=True, text=True, timeout=5
                )
                active = r2.returncode == 0
                self.result.emit(active, "running" if active else "not running")
            except Exception as exc:
                self.result.emit(False, f"detection failed: {exc}")
        except Exception as exc:
            self.result.emit(False, str(exc))


# ---------------------------------------------------------------------------
# Service tab
# ---------------------------------------------------------------------------

class _ServiceTab(QWidget):
    _SVN_USER = "svn"
    _SVN_GROUP = "svnserver"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status_worker: _StatusWorker | None = None
        self._settings = QSettings() # This was missing in the previous context
        self._setup_ui()

    def showEvent(self, event: object) -> None:
        """Update dynamic labels and status when the widget is shown."""
        super().showEvent(event) # type: ignore[misc]
        self._update_config_display()
        self._refresh_status()

    def _update_config_display(self) -> None:
        repo_root = self._settings.value("Server/repo_root", "/var/svn")
        self._config_label.setText(f"The service will be configured with repository root: <b>{repo_root}</b>")

        unit_path = "/etc/systemd/system/svnserve.service"
        if os.path.exists(unit_path):
            self._install_systemd_btn.setText("Update and Enable Service")
            self._install_systemd_btn.setToolTip(f"Overwrite {unit_path} with current settings and re-enable.")
        else:
            self._install_systemd_btn.setText("Install and Enable Service")
            self._install_systemd_btn.setToolTip(f"Create {unit_path} and enable it.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Status indicator
        status_group = QGroupBox("svnserve Status")
        status_layout = QVBoxLayout(status_group)

        self._status_badge = QLabel("Checking…")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setStyleSheet("font-size: 14px; padding: 6px;")
        status_layout.addWidget(self._status_badge)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        # These buttons are now informational; real control is via helper script.
        self._start_btn = QPushButton("▶ Start")
        self._stop_btn = QPushButton("⏹ Stop")
        self._restart_btn = QPushButton("🔄 Restart")
        self._refresh_btn = QPushButton("Refresh Status")

        self._refresh_btn.clicked.connect(self._refresh_status)

        warn = QLabel("⚠ Start/Stop/Restart requires root or sudo privileges.")
        warn.setStyleSheet("color: #856404; font-size: 11px;")
        warn.setWordWrap(True)

        for w in (self._start_btn, self._stop_btn, self._restart_btn, self._refresh_btn):
            btn_layout.addWidget(w)
        status_layout.addWidget(btn_row)
        status_layout.addWidget(warn)
        layout.addWidget(status_group) # This was missing in the previous context

        # Config snippets
        snippets_group = QGroupBox("Configuration Snippets")
        snippets_layout = QVBoxLayout(snippets_group)
        snippets_layout.setSpacing(8)

        systemd_box = QGroupBox("systemd unit file (svnserve.service)")
        systemd_layout = QVBoxLayout(systemd_box)

        self._config_label = QLabel()
        self._config_label.setWordWrap(True)
        systemd_layout.addWidget(self._config_label)

        self._install_systemd_btn = QPushButton()
        self._install_systemd_btn.clicked.connect(self._on_install_systemd_service)
        systemd_layout.addWidget(self._install_systemd_btn)

        snippets_layout.addWidget(systemd_box)
        # The old control buttons are now connected to the helper script.
        self._start_btn.clicked.connect(lambda: self._control("start"))
        self._stop_btn.clicked.connect(lambda: self._control("stop"))
        self._restart_btn.clicked.connect(lambda: self._control("restart"))

        layout.addWidget(snippets_group)
        layout.addStretch()
        self._update_config_display()

    @staticmethod
    def _mono_font():
        from PySide6.QtGui import QFont
        f = QFont("Monospace")
        f.setStyleHint(QFont.StyleHint.TypeWriter)
        f.setPointSize(9)
        return f

    def _refresh_status(self) -> None:
        self._status_badge.setText("Checking…")
        self._status_badge.setStyleSheet("font-size: 14px; padding: 6px;")
        self._status_worker = _StatusWorker()
        self._status_worker.result.connect(self._on_status_result)
        self._status_worker.start()

    def _on_status_result(self, active: bool, status: str) -> None:
        if active:
            self._status_badge.setText(f"✅  svnserve is RUNNING  ({status})")
            self._status_badge.setStyleSheet(
                "font-size:14px; padding:6px; color:#22863a; font-weight:bold;"
            )
        else:
            self._status_badge.setText(f"⛔  svnserve is STOPPED  ({status})")
            self._status_badge.setStyleSheet(
                "font-size:14px; padding:6px; color:#cb2431; font-weight:bold;"
            )

    def _control(self, action: str) -> None:
        # This now uses the helper script for privileged systemctl commands
        reply = QMessageBox.question(
            self, f"Service Control: {action.capitalize()}",
            f"This will attempt to {action} the svnserve service.\n"
            "Administrative privileges are required.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Use the helper script for privileged systemctl commands
            self._run_helper_script([f"{action}_service"])
            self._refresh_status()

    def _run_helper_script(self, args: list[str]) -> None:
        """Runs the privileged helper script via pkexec and shows output."""
        # In a real package, it would be "/usr/bin/svn-server-admin-helper"
        helper_path = "/usr/bin/svn-server-admin-helper"
        # Fallback for development environment: correct path relative to svn_server/
        dev_path = os.path.join(os.path.dirname(__file__), "resources", "system-helper.sh")
        if not os.path.exists(helper_path):
            # Fallback for development environment
            if os.path.exists(dev_path):
                helper_path = dev_path
            else:
                QMessageBox.critical(self, "Error", f"Helper script not found at {helper_path}")
                return

        debug_level = self._settings.value("General/debug_level", 0)
        args.append(str(debug_level))

        dlg = PkexecRunnerDialog(self)
        dlg.run([helper_path] + args)
        self._refresh_status()

    def _on_install_systemd_service(self) -> None:
        repo_root = self._settings.value("Server/repo_root", "/var/svn")
        unit_content = _SYSTEMD_UNIT.replace(
            "%%REPO_ROOT%%", repo_root
        ).replace(
            "%%SVN_USER%%", self._SVN_USER
        )

        unit_path = "/etc/systemd/system/svnserve.service"
        is_update = os.path.exists(unit_path)

        title = "Update Systemd Service" if is_update else "Install Systemd Service"
        message = (
            f"The service file '{unit_path}' already exists. This action will <b>overwrite</b> it to use the current repository root:\n"
            f"<b>{repo_root}</b>\n\n"
            "This is the correct action if you have changed the repository root in Settings or are still getting 'No repository found' errors."
        ) if is_update else (
            f"This will create '{unit_path}' to run as user <b>{self._SVN_USER}</b> with repository root:\n"
            f"<b>{repo_root}</b>\n\n"
            "It will then enable and start the service."
        )
        message += "\n\nAdministrative privileges are required.\nProceed?"

        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Ensure svnserve user and group exist
            if not self._check_and_create_svn_user_group():
                return # Abort if user/group creation failed or was cancelled

            self._run_helper_script(["write_systemd_unit", unit_content])
            self._run_helper_script(["enable_systemd_unit"])

    def _check_and_create_svn_user_group(self) -> bool:
        """
        Checks if the 'svnserve' group and user exist, prompts to create them
        if not, and sets ownership on the repository root.
        Returns True if all steps succeed or are not needed, False otherwise.
        """
        group_name = self._SVN_GROUP
        user_name = self._SVN_USER

        group_exists = svc.check_group_exists(group_name)
        user_exists = svc.check_user_exists(user_name)

        if not group_exists:
            reply = QMessageBox.question(
                self, "Create System Group",
                f"The system group '{group_name}' does not exist. It is required for the svnserve service.\n"
                "Administrative privileges are required to create it.\n\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_helper_script(["add_group", group_name])
            else:
                QMessageBox.warning(self, "Aborted", "Group creation is required to proceed.")
                return False

        if not user_exists:
            repo_root = self._settings.value("Server/repo_root", "/var/svn")
            reply = QMessageBox.question(
                self, "Create System User",
                f"The system user '{user_name}' does not exist. It is required for the svnserve service.\n"
                f"This user will be added to the '{group_name}' group and configured for nologin.\n"
                "Administrative privileges are required to create it.\n\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_helper_script(["add_user", user_name, group_name])
            else:
                QMessageBox.warning(self, "Aborted", "User creation is required to proceed.")
                return False

        # Set ownership on repository root
        repo_root = self._settings.value("Server/repo_root", "")

        is_in_other_home = (repo_root.startswith("/home/") and
                            not repo_root.startswith(f"/home/{self._SVN_USER}/") and
                            repo_root != f"/home/{self._SVN_USER}")

        if is_in_other_home:
            QMessageBox.warning(
                self, "Bad Repository Location",
                f"The repository root <b>{repo_root}</b> is inside a user's home directory. "
                "This is not recommended and will likely cause permission errors for the 'svn' system user, "
                "as home directories are often private.\n\n"
                "Please use a standard system path like <b>/var/svn</b>, <b>/srv/svn</b>, or <b>/home/{self._SVN_USER}</b> instead."
            )
            return False # Abort to prevent a broken setup

        if repo_root:
            if os.path.isdir(repo_root):
                reply = QMessageBox.question(
                    self, "Set Directory Permissions",
                    f"For the svnserve service to work correctly, the user '{user_name}' must have ownership of the repository root directory.\n\n"
                    f"Set ownership of <b>{repo_root}</b> to user <b>{user_name}</b> and group <b>{group_name}</b>?\n\n"
                    "Administrative privileges are required.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
            else:
                reply = QMessageBox.question(
                    self, "Create Repository Root",
                    f"The configured repository root directory does not exist:\n<b>{repo_root}</b>\n\n"
                    f"Create this directory and set its ownership to user <b>{user_name}</b> and group <b>{group_name}</b>?\n\n"
                    "Administrative privileges are required.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )

            if reply == QMessageBox.StandardButton.Yes:
                self._run_helper_script(["set_ownership", repo_root, user_name, group_name])
            else:
                QMessageBox.warning(self, "Aborted", "Repository root creation and/or permissions are required to proceed.")
                return False
        return True

# ---------------------------------------------------------------------------
# Performance tab
# ---------------------------------------------------------------------------

class _PerformanceTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._setup_ui()
        self._load()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        cache_group = QGroupBox("Shared Object Cache")
        cache_layout = QFormLayout(cache_group)

        self._cache_slider = QSlider(Qt.Orientation.Horizontal)
        self._cache_slider.setRange(0, 1024)
        self._cache_slider.setSingleStep(16)
        self._cache_slider.setTickInterval(128)
        self._cache_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._cache_label = QLabel("0 MB")
        self._cache_slider.valueChanged.connect(
            lambda v: self._cache_label.setText(f"{v} MB")
        )

        cache_row = QWidget()
        cache_row_layout = QHBoxLayout(cache_row)
        cache_row_layout.setContentsMargins(0, 0, 0, 0)
        cache_row_layout.addWidget(self._cache_slider)
        cache_row_layout.addWidget(self._cache_label)

        cache_layout.addRow("Cache size:", cache_row)
        cache_layout.addRow("", QLabel(
            "Sets --memory-cache-size for svnserve. 0 = disabled.\n"
            "Recommended: 256–512 MB for most repositories."
        ))
        layout.addWidget(cache_group)

        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch()

    def _load(self) -> None:
        cache = int(self._settings.value("Server/cache_size_mb", 0))
        self._cache_slider.setValue(cache)

    def _save(self) -> None:
        self._settings.setValue("Server/cache_size_mb", self._cache_slider.value())
        self._status.setText("✅ Settings saved.")


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class ServicePanel(QWidget):
    """Service status + performance settings panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(_ServiceTab(), "Service")
        tabs.addTab(_PerformanceTab(), "Performance")
        layout.addWidget(tabs)
