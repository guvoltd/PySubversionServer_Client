"""Settings dialog for the SVN Server Admin application."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QMessageBox,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from svn_shared.widgets.pkexec_runner import PkexecRunnerDialog


class ServerSettingsDialog(QDialog):
    """Settings dialog persisting to QSettings under 'General/' and 'Server/' keys."""

    theme_changed = Signal(str)  # emits new theme value when it changes on OK

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — SVN Server Admin")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._settings = QSettings()
        self._setup_ui()
        self._load()

    _SVN_USER = "svn"
    _SVN_GROUP = "svnserver"

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(self._build_appearance_group())
        layout.addWidget(self._build_repository_group())
        layout.addWidget(self._build_password_group())
        layout.addWidget(self._build_notifications_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_appearance_group(self) -> QGroupBox:
        group = QGroupBox("Appearance")
        form = QFormLayout(group)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Light", "Dark", "Auto (system)"])
        self._theme_combo.setToolTip("Choose the application colour theme")
        form.addRow("Theme:", self._theme_combo)

        self._debug_level_combo = QComboBox()
        self._debug_level_combo.addItems([
            "0 - Default (Info to file, Warnings to console)",
            "1 - Verbose (Debug to file, Info to console)",
            "2 - Full Debug (Debug to file and console)"
        ])
        self._debug_level_combo.setToolTip("Set application logging verbosity. Requires restart.")
        form.addRow("Debug level:", self._debug_level_combo)
        return group

    def _build_repository_group(self) -> QGroupBox:
        group = QGroupBox("Repository")
        form = QFormLayout(group)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self._repo_root_edit = QLineEdit()
        self._repo_root_edit.setPlaceholderText("/var/svn")
        self._repo_root_edit.setToolTip(
            "Default root directory scanned for repositories when the app starts"
        )
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_root)
        row_layout.addWidget(self._repo_root_edit)
        row_layout.addWidget(browse)
        form.addRow("Repository root:", row)

        # Global password file
        gp_row = QWidget()
        gp_layout = QHBoxLayout(gp_row)
        gp_layout.setContentsMargins(0, 0, 0, 0)
        self._global_passwd_edit = QLineEdit()
        self._global_passwd_edit.setPlaceholderText("/etc/svn/passwd")
        self._global_passwd_edit.setToolTip("Path to a global password file shared by all repositories.")
        gp_browse = QPushButton("Browse…")
        gp_browse.setFixedWidth(80)
        gp_browse.clicked.connect(self._browse_global_passwd)
        gp_layout.addWidget(self._global_passwd_edit)
        gp_layout.addWidget(gp_browse)
        form.addRow("Global password file:", gp_row)

        # Global authz file
        ga_row = QWidget()
        ga_layout = QHBoxLayout(ga_row)
        ga_layout.setContentsMargins(0, 0, 0, 0)
        self._global_authz_edit = QLineEdit()
        self._global_authz_edit.setPlaceholderText("/etc/svn/authz")
        self._global_authz_edit.setToolTip("Path to a global authorization file for groups.")
        ga_browse = QPushButton("Browse…")
        ga_browse.setFixedWidth(80)
        ga_browse.clicked.connect(self._browse_global_authz)
        ga_layout.addWidget(self._global_authz_edit)
        ga_layout.addWidget(ga_browse)
        form.addRow("Global authz file:", ga_row)

        self._default_backend_combo = QComboBox()
        self._default_backend_combo.addItems(["FSFS", "FSX"])
        self._default_backend_combo.setToolTip(
            "Filesystem backend used when creating new repositories"
        )
        form.addRow("Default backend:", self._default_backend_combo)

        return group

    def _build_password_group(self) -> QGroupBox:
        group = QGroupBox("Password Policy  (applied when adding or editing users)")
        form = QFormLayout(group)

        self._min_length_spin = QSpinBox()
        self._min_length_spin.setRange(1, 64)
        self._min_length_spin.setSuffix(" characters")
        self._min_length_spin.setToolTip("Minimum number of characters required for passwords")
        form.addRow("Minimum length:", self._min_length_spin)

        self._complexity_check = QCheckBox(
            "Require complexity  (3 of 4: uppercase, lowercase, digits, special)"
        )
        self._complexity_check.setToolTip(
            "Password must satisfy at least three of: A-Z, a-z, 0-9, special ASCII characters.\n"
            "All passwords are restricted to ASCII characters to prevent HTTP Basic auth "
            "encoding issues across different SVN clients."
        )
        form.addRow("", self._complexity_check)

        return group

    def _build_notifications_group(self) -> QGroupBox:
        group = QGroupBox("Notifications")
        form = QFormLayout(group)

        self._admin_email_edit = QLineEdit()
        self._admin_email_edit.setPlaceholderText("admin@example.com")
        self._admin_email_edit.setToolTip(
            "Default recipient for background job notifications (backup, verify).\n"
            "Requires an SMTP profile to be configured in the SMTP Manager."
        )
        form.addRow("Admin email:", self._admin_email_edit)

        return group

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    _THEME_VALUES = ["light", "dark", "auto"]
    _BACKEND_VALUES = ["fsfs", "fsx"]

    def _load(self) -> None:
        s = self._settings

        theme = s.value("General/theme", "light")
        idx = self._THEME_VALUES.index(theme) if theme in self._THEME_VALUES else 0
        self._theme_combo.setCurrentIndex(idx)

        self._debug_level_combo.setCurrentIndex(
            int(s.value("General/debug_level", 0)))

        self._repo_root_edit.setText(s.value("Server/repo_root", ""))

        self._global_passwd_edit.setText(s.value("Server/global_passwd_file", "/etc/svn/passwd"))

        self._global_authz_edit.setText(s.value("Server/global_authz_file", "/etc/svn/authz"))

        backend = s.value("Server/default_backend", "fsfs")
        bidx = self._BACKEND_VALUES.index(backend) if backend in self._BACKEND_VALUES else 0
        self._default_backend_combo.setCurrentIndex(bidx)

        self._min_length_spin.setValue(int(s.value("Server/pw_min_length", 8)))
        self._complexity_check.setChecked(
            s.value("Server/pw_complexity", False, type=bool)
        )

        self._admin_email_edit.setText(s.value("Server/admin_email", ""))

    def _on_accept(self) -> None:
        s = self._settings

        new_theme = self._THEME_VALUES[self._theme_combo.currentIndex()]
        old_theme = s.value("General/theme", "light")
        s.setValue("General/theme", new_theme)

        new_debug_level = self._debug_level_combo.currentIndex()
        old_debug_level = int(s.value("General/debug_level", 0))
        s.setValue("General/debug_level", new_debug_level)

        repo_root = self._repo_root_edit.text().strip()

        # The service runs as 'svn', so it can access its own home dir, but not others.
        svn_user_home = "/home/svn"
        is_in_other_home = (repo_root.startswith("/home/") and
                            not repo_root.startswith(svn_user_home + "/") and
                            repo_root != svn_user_home)

        if is_in_other_home:
            QMessageBox.warning(
                self,
                "Bad Repository Location",
                "Storing repositories inside a regular user's home directory (e.g., /home/uv) is not recommended.\n\n"
                "The 'svnserve' process runs as a dedicated system user ('svn') which typically cannot access "
                "private home directories, leading to 'Permission Denied' errors.\n\n"
                "Please choose a standard system path like <b>/var/svn</b>, <b>/srv/svn</b>, or the svn user's home (<b>/home/svn</b>)."
            )
            return  # Abort saving settings

        if repo_root and not os.path.isdir(repo_root):
            reply = QMessageBox.question(
                self,
                "Create Repository Root",
                f"The configured repository root directory does not exist:\n<b>{repo_root}</b>\n\n"
                f"Do you want to create this directory and set its ownership for the '{self._SVN_USER}' user?\n\n"
                "Administrative privileges will be required.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_helper_script(
                    ["set_ownership", repo_root, self._SVN_USER, self._SVN_GROUP]
                )
                # After running, check if it was successful
                if not os.path.isdir(repo_root):
                    QMessageBox.warning(self, "Creation Failed", "Failed to create the repository root directory. Please check permissions or logs.")
                    return
            else:
                QMessageBox.warning(self, "Aborted", "Repository root does not exist. Settings not saved.")
                return

        s.setValue("Server/repo_root", repo_root)

        s.setValue(
            "Server/global_passwd_file", self._global_passwd_edit.text().strip() or "/etc/svn/passwd"
        )

        s.setValue(
            "Server/global_authz_file", self._global_authz_edit.text().strip() or "/etc/svn/authz"
        )

        s.setValue(
            "Server/default_backend",
            self._BACKEND_VALUES[self._default_backend_combo.currentIndex()],
        )

        s.setValue("Server/pw_min_length", self._min_length_spin.value())
        s.setValue("Server/pw_complexity", self._complexity_check.isChecked())

        s.setValue("Server/admin_email", self._admin_email_edit.text().strip())

        if new_debug_level != old_debug_level:
            QMessageBox.information(self, "Restart Required",
                                    "Debug level changes will take effect on next application start.")

        self.accept()

        if new_theme != old_theme:
            self.theme_changed.emit(new_theme)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Repository Root Directory",
            self._repo_root_edit.text() or os.path.expanduser("~"),
        )
        if path:
            self._repo_root_edit.setText(path)

    def _browse_global_passwd(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Global Password File",
            self._global_passwd_edit.text() or "/etc/",
            "All files (*)"
        )
        if path:
            self._global_passwd_edit.setText(path)

    def _browse_global_authz(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Global Authz File",
            self._global_authz_edit.text() or "/etc/",
            "All files (*)"
        )
        if path:
            self._global_authz_edit.setText(path)

    def _run_helper_script(self, args: list[str]) -> None:
        """Runs the privileged helper script via pkexec and shows output."""
        # In a real package, it would be "/usr/bin/svn-server-admin-helper"
        helper_path = "/usr/bin/svn-server-admin-helper"
        # Fallback for development environment
        dev_path = os.path.join(
            os.path.dirname(__file__), "resources", "system-helper.sh"
        )
        if not os.path.exists(helper_path):
            if os.path.exists(dev_path):
                helper_path = dev_path
            else:
                QMessageBox.critical(self, "Error", f"Helper script not found at {helper_path}")
                return

        debug_level = self._settings.value("General/debug_level", 0)
        args.append(str(debug_level))

        dlg = PkexecRunnerDialog(self)
        dlg.run([helper_path] + args)
