"""SVN Server Admin main window and application setup."""

from __future__ import annotations

import os
import getpass
import grp
import pwd
import shutil

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from svn_server.settings_dialog import ServerSettingsDialog
from svn_server.repo_manager import RepoManager
from svn_server.access_editor import AccessEditor
from svn_server.hook_manager import HookManager
from svn_server.effective_access import EffectiveAccess
from svn_server.smtp_manager import SmtpManager
from svn_server.backup_panel import BackupPanel
from svn_server.job_scheduler import JobScheduler
from svn_server.service_panel import ServicePanel
from svn_shared.widgets.pkexec_runner import PkexecRunnerDialog

# Right-panel stack page indices
_PAGE_WELCOME  = 0
_PAGE_DETAIL   = 1   # per-repo tabs
# page 2 = SmtpManager, page 3 = JobScheduler, page 4 = ServicePanel

# Default shortcut definitions — loaded from QSettings at startup.
# Users may override via QSettings key  Server/shortcuts/<action_key>.
_DEFAULT_SHORTCUTS: dict[str, str] = {
    "set_root":     "Ctrl+O",
    "quit":         "Ctrl+Q",
    "refresh":      "F5",
    "create_repo":  "Ctrl+N",
    "backup":       "Ctrl+Shift+B",
    "jobs":         "Ctrl+J",
    "smtp":         "Ctrl+M",
    "service":      "Ctrl+Shift+S",
    "settings":     "Ctrl+,",
    "shortcuts":    "Ctrl+Shift+K",
}


def _shortcut(key: str) -> QKeySequence:
    default = _DEFAULT_SHORTCUTS.get(key, "")
    override = QSettings().value(f"Server/shortcuts/{key}", default)
    return QKeySequence(override)


class _ShortcutsDialog:
    """Read/write shortcut configuration dialog (opened from Tools menu)."""

    @staticmethod
    def open(parent: QWidget) -> None:
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QHeaderView,
            QTableWidget, QTableWidgetItem, QVBoxLayout, QLabel as _Label,
        )

        settings = QSettings()
        dlg = QDialog(parent)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumSize(480, 400)
        layout = QVBoxLayout(dlg)

        note = _Label(
            "Double-click a shortcut cell to edit. "
            "Use standard notation: Ctrl+K, Shift+F5, etc."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        rows = list(_DEFAULT_SHORTCUTS.items())
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)

        _LABELS = {
            "set_root":    "Set Repository Root…",
            "quit":        "Quit",
            "refresh":     "Refresh",
            "create_repo": "Create Repository…",
            "backup":      "Backup / Dump…",
            "jobs":        "Jobs…",
            "smtp":        "SMTP Profiles…",
            "service":     "Service Panel",
            "settings":    "Settings…",
            "shortcuts":   "Keyboard Shortcuts…",
        }
        for row, (key, default) in enumerate(rows):
            label_item = QTableWidgetItem(_LABELS.get(key, key))
            label_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row, 0, label_item)
            current = settings.value(f"Server/shortcuts/{key}", default)
            table.setItem(row, 1, QTableWidgetItem(str(current)))
        layout.addWidget(table)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        reset_btn = btn_box.addButton("Reset Defaults", QDialogButtonBox.ButtonRole.ResetRole)

        def _save() -> None:
            for row, (key, _) in enumerate(rows):
                val = table.item(row, 1).text().strip()
                if val:
                    settings.setValue(f"Server/shortcuts/{key}", val)
                else:
                    settings.remove(f"Server/shortcuts/{key}")
            QMessageBox.information(
                parent, "Shortcuts Saved",
                "Shortcut changes will take effect the next time the application starts."
            )

        def _reset() -> None:
            for row, (key, default) in enumerate(rows):
                settings.remove(f"Server/shortcuts/{key}")
                table.item(row, 1).setText(default)
            QMessageBox.information(parent, "Shortcuts Reset", "Default shortcuts restored. Restart to apply.")

        btn_box.accepted.connect(_save)
        btn_box.rejected.connect(dlg.reject)
        reset_btn.clicked.connect(_reset)
        layout.addWidget(btn_box)
        dlg.exec()


class ServerMainWindow(QMainWindow):
    """Main window for the SVN Server Admin application."""

    _SVN_GROUP = "svnserver"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle("SVN Server Admin")
        self.setMinimumSize(1100, 680)

        self._settings = QSettings()
        self._repo_root: str = self._settings.value("Server/repo_root", "")
        self._current_repo: str | None = None

        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._load_theme()
        self._restore_geometry()

        # Re-open last root on startup
        if self._repo_root and os.path.isdir(self._repo_root):
            self._open_root(self._repo_root)

        self._check_user_group_membership()
        self._check_firewall_configuration()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # File
        file_menu = menu_bar.addMenu("&File")
        set_root = QAction("Set &Repository Root…", self)
        set_root.setShortcut(_shortcut("set_root"))
        set_root.setToolTip(
            f"Set the root directory containing repositories ({_shortcut('set_root').toString()})"
        )
        set_root.triggered.connect(self._on_set_root)
        file_menu.addAction(set_root)
        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(_shortcut("quit"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View
        view_menu = menu_bar.addMenu("&View")
        refresh = QAction("&Refresh", self)
        refresh.setShortcut(_shortcut("refresh"))
        refresh.setToolTip(f"Refresh repository list ({_shortcut('refresh').toString()})")
        refresh.triggered.connect(self._on_refresh)
        view_menu.addAction(refresh)

        service_action = QAction("&Service Panel", self)
        service_action.setShortcut(_shortcut("service"))
        service_action.setToolTip(
            f"Open service status panel ({_shortcut('service').toString()})"
        )
        service_action.triggered.connect(lambda: self._content.setCurrentIndex(4))
        view_menu.addAction(service_action)

        # Admin
        admin_menu = menu_bar.addMenu("&Admin")
        create_action = QAction("&Create Repository…", self)
        create_action.setShortcut(_shortcut("create_repo"))
        create_action.setToolTip(
            f"Create a new SVN repository ({_shortcut('create_repo').toString()})"
        )
        create_action.triggered.connect(self._on_create_repo)
        admin_menu.addAction(create_action)
        admin_menu.addSeparator()

        backup_action = QAction("&Backup / Dump…", self)
        backup_action.setShortcut(_shortcut("backup"))
        backup_action.setToolTip(
            f"Open backup panel for the selected repository ({_shortcut('backup').toString()})"
        )
        backup_action.triggered.connect(self._on_show_backup)
        admin_menu.addAction(backup_action)

        jobs_action = QAction("&Jobs…", self)
        jobs_action.setShortcut(_shortcut("jobs"))
        jobs_action.setToolTip(
            f"Open background job scheduler ({_shortcut('jobs').toString()})"
        )
        jobs_action.triggered.connect(self._on_show_jobs)
        admin_menu.addAction(jobs_action)

        # Tools
        tools_menu = menu_bar.addMenu("&Tools")

        smtp_action = QAction("&SMTP Profiles…", self)
        smtp_action.setShortcut(_shortcut("smtp"))
        smtp_action.setToolTip(
            f"Manage outgoing e-mail profiles ({_shortcut('smtp').toString()})"
        )
        smtp_action.triggered.connect(self._on_show_smtp)
        tools_menu.addAction(smtp_action)

        effective_action = QAction("&Effective Access…", self)
        effective_action.setToolTip("Check effective path access for a user")
        effective_action.triggered.connect(self._on_show_effective)
        tools_menu.addAction(effective_action)

        tools_menu.addSeparator()

        settings_action = QAction("&Settings…", self)
        settings_action.setShortcut(_shortcut("settings"))
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

        shortcuts_action = QAction("&Keyboard Shortcuts…", self)
        shortcuts_action.setShortcut(_shortcut("shortcuts"))
        shortcuts_action.setToolTip("View and configure keyboard shortcuts")
        shortcuts_action.triggered.connect(lambda: _ShortcutsDialog.open(self))
        tools_menu.addAction(shortcuts_action)

        # Help
        menu_bar.addMenu("&Help").addAction(QAction("&About SVN Server Admin", self))

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        set_root_tb = toolbar.addAction("📁 Set Root")
        set_root_tb.setToolTip(
            f"Set repository root directory  ({_shortcut('set_root').toString()})"
        )
        set_root_tb.triggered.connect(self._on_set_root)

        create_tb = toolbar.addAction("➕ Create")
        create_tb.setToolTip(
            f"Create a new repository  ({_shortcut('create_repo').toString()})"
        )
        create_tb.triggered.connect(self._on_create_repo)

        refresh_tb = toolbar.addAction("🔄 Refresh")
        refresh_tb.setToolTip(f"Refresh repository list  ({_shortcut('refresh').toString()})")
        refresh_tb.triggered.connect(self._on_refresh)

        backup_tb = toolbar.addAction("💾 Backup")
        backup_tb.setToolTip(
            f"Open backup / dump panel  ({_shortcut('backup').toString()})"
        )
        backup_tb.triggered.connect(self._on_show_backup)

        jobs_tb = toolbar.addAction("⏰ Jobs")
        jobs_tb.setToolTip(
            f"Open background job scheduler  ({_shortcut('jobs').toString()})"
        )
        jobs_tb.triggered.connect(self._on_show_jobs)

        toolbar.addSeparator()

        service_tb = toolbar.addAction("🖥 Service")
        service_tb.setToolTip(
            f"Open service status panel  ({_shortcut('service').toString()})"
        )
        service_tb.triggered.connect(lambda: self._content.setCurrentIndex(4))

        settings_tb = toolbar.addAction("⚙ Settings")
        settings_tb.setToolTip(f"Open settings  ({_shortcut('settings').toString()})")
        settings_tb.triggered.connect(self._on_open_settings)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: repo manager
        self._repo_manager = RepoManager()
        self._repo_manager.setMinimumWidth(220)
        self._repo_manager.repo_selected.connect(self._on_repo_selected)
        splitter.addWidget(self._repo_manager)

        # Right: stacked (welcome | per-repo tabs)
        self._content = QStackedWidget()

        # Page 0: welcome
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        self._welcome_label = QLabel(
            "Set a repository root to get started.\n\nFile → Set Repository Root  (Ctrl+O)"
        )
        self._welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_label.setStyleSheet("font-size: 14px;")
        welcome_layout.addWidget(self._welcome_label)
        self._content.addWidget(welcome)

        # Page 1: per-repo tabbed detail area
        self._detail_tabs = QTabWidget()

        self._access_editor = AccessEditor()
        self._detail_tabs.addTab(self._access_editor, "Access Control")

        self._hook_manager = HookManager()
        self._detail_tabs.addTab(self._hook_manager, "Hooks")

        self._backup_panel = BackupPanel()
        self._detail_tabs.addTab(self._backup_panel, "Backup")

        self._effective_access = EffectiveAccess()
        self._detail_tabs.addTab(self._effective_access, "Effective Access")

        self._content.addWidget(self._detail_tabs)

        # Global panels — accessible from menu/toolbar without a repo selected
        self._smtp_manager = SmtpManager()
        self._content.addWidget(self._smtp_manager)   # page 2

        self._job_scheduler = JobScheduler()
        self._content.addWidget(self._job_scheduler)  # page 3

        self._service_panel = ServicePanel()
        self._content.addWidget(self._service_panel)  # page 4

        self._content.setCurrentIndex(_PAGE_WELCOME)
        splitter.addWidget(self._content)
        splitter.setSizes([550, 550])
        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        status_bar = QStatusBar()
        self._root_label = QLabel("No repository root set")
        status_bar.addPermanentWidget(self._root_label)
        self.setStatusBar(status_bar)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _load_theme(self) -> None:
        theme = self._settings.value("General/theme", "light")
        style_dir = os.path.join(
            os.path.dirname(__file__), "..", "svn_shared", "resources", "styles"
        )
        qss_file = os.path.join(style_dir, f"{theme}.qss")
        if os.path.exists(qss_file):
            with open(qss_file) as f:
                self.setStyleSheet(f.read())

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        geometry = self._settings.value("ServerWindow/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: object) -> None:
        self._settings.setValue("ServerWindow/geometry", self.saveGeometry())
        super().closeEvent(event)  # type: ignore[misc]

    def _check_firewall_configuration(self) -> None:
        """On first startup, if ufw is present, ask to add a firewall rule for svnserve."""
        settings_key = "Server/firewall_rule_prompted"
        if self._settings.value(settings_key, False, type=bool):
            return  # We've already prompted the user once.

        # Only prompt if ufw is installed.
        if not shutil.which("ufw"):
            self._settings.setValue(settings_key, True)  # Don't prompt again if ufw isn't here.
            return

        reply = QMessageBox.question(
            self,
            "Network Access Configuration",
            "To allow other computers on your network to access this SVN server, a firewall rule is needed.\n\n"
            "Do you want to add a rule to allow incoming connections for Subversion (TCP port 3690) now?\n\n"
            "This requires administrative privileges.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        # Whether they say yes or no, don't ask again next time.
        self._settings.setValue(settings_key, True)

        if reply == QMessageBox.StandardButton.Yes:
            self._run_helper_script(["add_firewall_rule"])

    def _check_user_group_membership(self) -> None:
        """On startup, check if the user is in the svnserver group and prompt to add them if not."""
        try:
            # 1. Check if svnserver group exists. If not, do nothing.
            #    The user will be prompted to create it in the Service Panel.
            all_system_groups = [g.gr_name for g in grp.getgrall()]
            if self._SVN_GROUP not in all_system_groups:
                return

            # 2. Check if current user is already in the group.
            username = getpass.getuser()
            user_groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]
            primary_group_gid = pwd.getpwnam(username).pw_gid
            primary_group = grp.getgrgid(primary_group_gid).gr_name
            user_groups.append(primary_group)

            if self._SVN_GROUP in user_groups:
                return  # User is already a member, nothing to do.

            # 3. If not a member, ask to add them.
            reply = QMessageBox.question(
                self,
                "Permissions Setup",
                f"For the best experience, your user account (<b>{username}</b>) should be a member of the '<b>{self._SVN_GROUP}</b>' group. "
                "This allows you to create and manage repositories in the repository root (e.g., /var/svn) without running this application as root.\n\n"
                f"Do you want to add '<b>{username}</b>' to the '<b>{self._SVN_GROUP}</b>' group now?\n\n"
                "Administrative privileges are required. You will need to log out and log back in for the change to take effect.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_helper_script(["add_user_to_group", username, self._SVN_GROUP])

        except (KeyError, AttributeError, ImportError):
            # Could happen if user/group doesn't exist, or modules not available on some minimal systems.
            # Fail silently on any error during this optional check.
            pass

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

    # ------------------------------------------------------------------
    # Root management
    # ------------------------------------------------------------------

    def _open_root(self, root: str) -> None:
        self._repo_root = root
        self._root_label.setText(f"Root: {root}")
        self._settings.setValue("Server/repo_root", root)
        self._job_scheduler.set_repo_root(root)
        self._repo_manager.set_root(root)
        # Show welcome until a repo is actually selected
        self._content.setCurrentIndex(_PAGE_WELCOME)
        self._welcome_label.setText(
            f"Repository root: {root}\n\nSelect a repository from the left panel."
        )

    def _on_repo_selected(self, repo_path: str) -> None:
        self._current_repo = repo_path
        self._access_editor.load(repo_path)
        self._hook_manager.load(repo_path)
        self._backup_panel.set_repo(repo_path)
        self._effective_access.set_repo(repo_path)
        self._content.setCurrentIndex(_PAGE_DETAIL)
        self._detail_tabs.setCurrentIndex(0)
        self.statusBar().showMessage(f"Selected: {repo_path}", 3000)

    # ------------------------------------------------------------------
    # Toolbar / menu slots
    # ------------------------------------------------------------------

    def _on_set_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Set Repository Root")
        if path:
            self._open_root(path)

    def _on_refresh(self) -> None:
        self._repo_manager.refresh()

    def _on_create_repo(self) -> None:
        # Delegate directly to the repo manager's public method.
        self._repo_manager.create_repository()

    def _on_show_backup(self) -> None:
        if self._current_repo:
            self._content.setCurrentIndex(_PAGE_DETAIL)
            self._detail_tabs.setCurrentIndex(
                self._detail_tabs.indexOf(self._backup_panel)
            )
        else:
            QMessageBox.information(self, "Select Repository", "Select a repository first.")

    def _on_show_jobs(self) -> None:
        self._content.setCurrentIndex(3)

    def _on_show_smtp(self) -> None:
        self._content.setCurrentIndex(2)

    def _on_show_effective(self) -> None:
        if not self._current_repo:
            QMessageBox.information(self, "Select Repository", "Select a repository first.")
            return
        self._content.setCurrentIndex(_PAGE_DETAIL)
        self._detail_tabs.setCurrentIndex(
            self._detail_tabs.indexOf(self._effective_access)
        )

    def _on_open_settings(self) -> None:
        dlg = ServerSettingsDialog(self)
        dlg.theme_changed.connect(self._apply_theme)
        dlg.exec()
        repo_root = self._settings.value("Server/repo_root", "")
        if repo_root and repo_root != self._repo_root:
            self._open_root(repo_root)

    def _apply_theme(self, theme: str) -> None:
        self._settings.setValue("General/theme", theme)
        self._load_theme()
