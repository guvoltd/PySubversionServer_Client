"""SVN Client main window and application setup."""

from __future__ import annotations

import os

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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from svn_client.settings_dialog import ClientSettingsDialog
from svn_client.status_tree import StatusTree
from svn_client.diff_viewer import DiffViewer
from svn_client.log_viewer import LogViewer
from svn_client.conflict_panel import ConflictPanel
from svn_client.checkout_dialog import CheckoutDialog
from svn_client.commit_dialog import CommitDialog
from svn_client.branch_dialog import BranchDialog

import svn_shared.svn_client_svc as svc
from svn_shared.exceptions import SvnCommandError

# QStackedWidget page indices
_PAGE_WELCOME  = 0
_PAGE_DIFF     = 1
_PAGE_LOG      = 2
_PAGE_CONFLICT = 3

# Default shortcut definitions — loaded from QSettings at startup.
# Users may override via QSettings key  Client/shortcuts/<action_key>.
_DEFAULT_SHORTCUTS: dict[str, str] = {
    "open_wc":       "Ctrl+O",
    "checkout":      "Ctrl+Shift+O",
    "quit":          "Ctrl+Q",
    "refresh":       "F5",
    "update":        "Ctrl+U",
    "commit":        "Ctrl+Return",
    "log":           "Ctrl+L",
    "diff":          "Ctrl+D",
    "conflicts":     "Ctrl+Shift+X",
    "branch":        "Ctrl+B",
    "revert":        "Ctrl+Shift+Z",
    "settings":      "Ctrl+,",
    "shortcuts":     "Ctrl+Shift+K",
}


def _shortcut(key: str) -> QKeySequence:
    """Return the effective QKeySequence for a named shortcut action."""
    default = _DEFAULT_SHORTCUTS.get(key, "")
    override = QSettings().value(f"Client/shortcuts/{key}", default)
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
        dlg.setMinimumSize(480, 440)
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
            "open_wc":   "Open Working Copy",
            "checkout":  "Checkout…",
            "quit":      "Quit",
            "refresh":   "Refresh",
            "update":    "Update",
            "commit":    "Commit…",
            "log":       "Show Log",
            "diff":      "Show Diff",
            "conflicts": "Show Conflicts",
            "branch":    "Branch / Tag…",
            "revert":    "Revert…",
            "settings":  "Settings…",
            "shortcuts": "Keyboard Shortcuts…",
        }
        for row, (key, default) in enumerate(rows):
            label_item = QTableWidgetItem(_LABELS.get(key, key))
            label_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # not editable
            table.setItem(row, 0, label_item)
            current = settings.value(f"Client/shortcuts/{key}", default)
            table.setItem(row, 1, QTableWidgetItem(str(current)))
        layout.addWidget(table)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        reset_btn = btn_box.addButton("Reset Defaults", QDialogButtonBox.ButtonRole.ResetRole)

        def _save() -> None:
            # Iterate through the rows and save the new shortcut values
            for row, (key, _) in enumerate(rows):
                val = table.item(row, 1).text().strip()
                if val:
                    settings.setValue(f"Client/shortcuts/{key}", val)
                else:
                    settings.remove(f"Client/shortcuts/{key}")
            QMessageBox.information(
                parent, "Shortcuts Saved",
                "Shortcut changes will take effect the next time the application starts."
            )

        def _reset() -> None:
            for row, (key, default) in enumerate(rows):
                # Remove override from settings and restore default in the table
                settings.remove(f"Client/shortcuts/{key}")
                table.item(row, 1).setText(default)
            QMessageBox.information(parent, "Shortcuts Reset", "Default shortcuts restored. Restart to apply.")

        btn_box.accepted.connect(_save)
        btn_box.rejected.connect(dlg.reject)
        reset_btn.clicked.connect(_reset)
        layout.addWidget(btn_box)
        dlg.exec()


class ClientMainWindow(QMainWindow):
    """Main window for the SVN Client application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVN Client")
        self.setMinimumSize(1000, 640)

        self._settings = QSettings()
        self._wc_path: str | None = None

        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._load_theme()
        self._restore_geometry()

        # Re-open last working copy on startup
        last = self._settings.value("Client/default_wc_path", "")
        if last and os.path.isdir(last):
            self._open_wc(last)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        open_wc = QAction("&Open Working Copy…", self)
        open_wc.setShortcut(_shortcut("open_wc"))
        open_wc.setToolTip(f"Open an existing working copy ({_shortcut('open_wc').toString()})")
        open_wc.triggered.connect(self._on_open_wc)
        file_menu.addAction(open_wc)

        self._checkout_action = QAction("&Checkout…", self)
        self._checkout_action.setShortcut(_shortcut("checkout"))
        self._checkout_action.setToolTip(
            f"Checkout a repository to a new working copy ({_shortcut('checkout').toString()})"
        )
        self._checkout_action.triggered.connect(self._on_checkout)
        file_menu.addAction(self._checkout_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(_shortcut("quit"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu (placeholder)
        menu_bar.addMenu("&Edit")

        # View menu
        view_menu = menu_bar.addMenu("&View")

        refresh = QAction("&Refresh", self)
        refresh.setShortcut(_shortcut("refresh"))
        refresh.setToolTip(f"Refresh working copy status ({_shortcut('refresh').toString()})")
        refresh.triggered.connect(self._on_refresh)
        view_menu.addAction(refresh)

        view_menu.addSeparator()

        show_diff = QAction("Show &Diff", self)
        show_diff.setShortcut(_shortcut("diff"))
        show_diff.setToolTip(
            f"Show diff for the current working copy ({_shortcut('diff').toString()})"
        )
        show_diff.triggered.connect(self._on_show_diff)
        view_menu.addAction(show_diff)

        show_log = QAction("Show &Log", self)
        show_log.setShortcut(_shortcut("log"))
        show_log.setToolTip(f"Show commit log ({_shortcut('log').toString()})")
        show_log.triggered.connect(self._on_show_log)
        view_menu.addAction(show_log)

        show_conflicts = QAction("Show &Conflicts", self)
        show_conflicts.setShortcut(_shortcut("conflicts"))
        show_conflicts.setToolTip(
            f"Show conflicted files ({_shortcut('conflicts').toString()})"
        )
        show_conflicts.triggered.connect(self._on_show_conflicts)
        view_menu.addAction(show_conflicts)

        # SVN menu
        svn_menu = menu_bar.addMenu("&SVN")

        self._update_action = QAction("&Update", self)
        self._update_action.setShortcut(_shortcut("update"))
        self._update_action.setToolTip(
            f"Update working copy to HEAD ({_shortcut('update').toString()})"
        )
        self._update_action.triggered.connect(self._on_update)
        svn_menu.addAction(self._update_action)

        self._commit_action = QAction("&Commit…", self)
        self._commit_action.setShortcut(_shortcut("commit"))
        self._commit_action.setToolTip(
            f"Commit pending changes ({_shortcut('commit').toString()})"
        )
        self._commit_action.triggered.connect(self._on_commit)
        svn_menu.addAction(self._commit_action)

        log_action = QAction("&Log…", self)
        log_action.setShortcut(_shortcut("log"))
        log_action.triggered.connect(self._on_show_log)
        svn_menu.addAction(log_action)

        svn_menu.addSeparator()

        self._branch_action = QAction("&Branch / Tag…", self)
        self._branch_action.setShortcut(_shortcut("branch"))
        self._branch_action.setToolTip(
            f"Create branch, tag, or switch working copy ({_shortcut('branch').toString()})"
        )
        self._branch_action.triggered.connect(self._on_branch)
        svn_menu.addAction(self._branch_action)

        svn_menu.addSeparator()

        self._revert_action = QAction("&Revert…", self)
        self._revert_action.setShortcut(_shortcut("revert"))
        self._revert_action.setToolTip(
            f"Revert checked files to BASE ({_shortcut('revert').toString()})"
        )
        self._revert_action.triggered.connect(self._on_revert)
        svn_menu.addAction(self._revert_action)

        # Tools menu
        tools_menu = menu_bar.addMenu("&Tools")

        settings_action = QAction("&Settings…", self)
        settings_action.setShortcut(_shortcut("settings"))
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

        shortcuts_action = QAction("&Keyboard Shortcuts…", self)
        shortcuts_action.setShortcut(_shortcut("shortcuts"))
        shortcuts_action.setToolTip("View and configure keyboard shortcuts")
        shortcuts_action.triggered.connect(lambda: _ShortcutsDialog.open(self))
        tools_menu.addAction(shortcuts_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(QAction("&About SVN Client", self))

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        update_tb = toolbar.addAction("🔄 Update")
        update_tb.setToolTip(f"Update to HEAD  ({_shortcut('update').toString()})")
        update_tb.triggered.connect(self._on_update)

        commit_tb = toolbar.addAction("✅ Commit")
        commit_tb.setToolTip(f"Commit changes  ({_shortcut('commit').toString()})")
        commit_tb.triggered.connect(self._on_commit)

        log_tb = toolbar.addAction("📋 Log")
        log_tb.setToolTip(f"View commit log  ({_shortcut('log').toString()})")
        log_tb.triggered.connect(self._on_show_log)

        diff_tb = toolbar.addAction("⟺ Diff")
        diff_tb.setToolTip(f"Show working copy diff  ({_shortcut('diff').toString()})")
        diff_tb.triggered.connect(self._on_show_diff)

        branch_tb = toolbar.addAction("🔀 Branch")
        branch_tb.setToolTip(f"Branch / tag / switch  ({_shortcut('branch').toString()})")
        branch_tb.triggered.connect(self._on_branch)

        toolbar.addSeparator()

        refresh_tb = toolbar.addAction("↺ Refresh")
        refresh_tb.setToolTip(f"Refresh status  ({_shortcut('refresh').toString()})")
        refresh_tb.triggered.connect(self._on_refresh)

        settings_tb = toolbar.addAction("⚙ Settings")
        settings_tb.setToolTip(f"Open settings  ({_shortcut('settings').toString()})")
        settings_tb.triggered.connect(self._on_open_settings)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: status tree
        self._status_tree = StatusTree()
        self._status_tree.setMinimumWidth(200)
        self._status_tree.diff_requested.connect(self._on_diff_requested)
        self._status_tree.log_requested.connect(self._on_log_requested)
        splitter.addWidget(self._status_tree)

        # Right: stacked content area
        self._content = QStackedWidget()

        # Page 0: welcome
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        self._welcome_label = QLabel(
            "Open a working copy to get started.\n\nFile → Open Working Copy  (Ctrl+O)"
        )
        self._welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_label.setStyleSheet("font-size: 14px;")
        welcome_layout.addWidget(self._welcome_label)
        self._content.addWidget(welcome)          # index 0

        # Page 1: diff viewer
        self._diff_viewer = DiffViewer()
        self._content.addWidget(self._diff_viewer)  # index 1

        # Page 2: log viewer
        self._log_viewer = LogViewer()
        self._log_viewer.diff_requested.connect(self._on_log_diff_requested)
        self._content.addWidget(self._log_viewer)   # index 2

        # Page 3: conflict panel
        self._conflict_panel = ConflictPanel()
        self._conflict_panel.resolved.connect(self._on_conflict_resolved)
        self._content.addWidget(self._conflict_panel)  # index 3

        splitter.addWidget(self._content)
        splitter.setSizes([260, 740])
        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        status_bar = QStatusBar()
        self._wc_label = QLabel("No working copy open")
        status_bar.addPermanentWidget(self._wc_label)
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
        geometry = self._settings.value("ClientWindow/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: object) -> None:
        self._settings.setValue("ClientWindow/geometry", self.saveGeometry())
        super().closeEvent(event)  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Working copy management
    # ------------------------------------------------------------------

    def _open_wc(self, path: str) -> None:
        self._wc_path = path
        self._wc_label.setText(f"Working Copy: {path}")
        self._welcome_label.setText(f"Working copy: {path}\n\nLoading status…")
        self._content.setCurrentIndex(_PAGE_WELCOME)
        self._status_tree.set_wc_path(path)

    def _handle_svn_error(self, title: str, exc: SvnCommandError) -> None:
        """Centralized error handling for SvnCommandError."""
        QMessageBox.critical(
            self, title,
            f"An SVN command failed:\n\nCommand: {exc.command}\nError: {exc.stderr.strip()}"
        )

    # ------------------------------------------------------------------
    # Toolbar / menu slots
    # ------------------------------------------------------------------

    def _on_open_wc(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Working Copy")
        if path:
            self._open_wc(path)

    def _on_refresh(self) -> None:
        self._status_tree.refresh()

    def _on_checkout(self) -> None:
        dlg = CheckoutDialog(self)
        dlg.checkout_completed.connect(self._open_wc)
        dlg.exec()

    def _on_update(self) -> None:
        if not self._wc_path:
            QMessageBox.information(self, "No Working Copy", "Open a working copy first.")
            return
        self.statusBar().showMessage("Updating…")
        try:
            svc.update(self._wc_path)
        except SvnCommandError as exc:
            self._handle_svn_error("Update Failed", exc)
        else:
            self.statusBar().showMessage("Update complete.", 3000)
            self._status_tree.refresh()

    def _on_commit(self) -> None:
        if not self._wc_path:
            QMessageBox.information(self, "No Working Copy", "Open a working copy first.")
            return
        try:
            entries = svc.status(self._wc_path)
        except SvnCommandError as exc:
            self._handle_svn_error("Status Failed", exc)
            return
        dlg = CommitDialog(self._wc_path, entries, self)
        dlg.commit_completed.connect(self._on_committed)
        dlg.exec()

    def _on_committed(self, revision: int) -> None:
        self.statusBar().showMessage(f"Committed revision {revision}.", 4000)
        self._status_tree.refresh()

    def _on_show_diff(self) -> None:
        if not self._wc_path:
            return
        self._diff_viewer.load_from_wc(self._wc_path)
        self._content.setCurrentIndex(_PAGE_DIFF)

    def _on_show_log(self) -> None:
        if not self._wc_path:
            QMessageBox.information(self, "No Working Copy", "Open a working copy first.")
            return
        self._log_viewer.load(self._wc_path)
        self._content.setCurrentIndex(_PAGE_LOG)

    def _on_show_conflicts(self) -> None:
        if not self._wc_path:
            return
        try:
            entries = svc.status(self._wc_path)
        except SvnCommandError as exc:
            self._handle_svn_error("Status Failed", exc)
            return
        self._conflict_panel.load(self._wc_path, entries)
        self._content.setCurrentIndex(_PAGE_CONFLICT)

    def _on_branch(self) -> None:
        if not self._wc_path:
            QMessageBox.information(self, "No Working Copy", "Open a working copy first.")
            return
        dlg = BranchDialog(self._wc_path, self)
        dlg.operation_completed.connect(self._status_tree.refresh)
        dlg.exec()

    def _on_revert(self) -> None:
        if not self._wc_path:
            return
        checked = self._status_tree.checked_paths()
        if not checked:
            QMessageBox.information(self, "Nothing Selected",
                                    "Check files in the status tree to revert.")
            return
        reply = QMessageBox.question(
            self, "Revert",
            f"Revert {len(checked)} file(s)? Local changes will be permanently lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                svc.revert(checked, cwd=self._wc_path)
            except SvnCommandError as exc:
                self._handle_svn_error("Revert Failed", exc)
            else:
                self._status_tree.refresh()

    def _on_open_settings(self) -> None:
        dlg = ClientSettingsDialog(self)
        dlg.theme_changed.connect(self._apply_theme)
        dlg.exec()

    def _apply_theme(self, theme: str) -> None:
        self._settings.setValue("General/theme", theme)
        self._load_theme()

    # ------------------------------------------------------------------
    # Signals from child widgets
    # ------------------------------------------------------------------

    def _on_diff_requested(self, wc_path: str, rel_path: str) -> None:
        self._diff_viewer.load_from_wc(wc_path, file_path=rel_path)
        self._content.setCurrentIndex(_PAGE_DIFF)

    def _on_log_requested(self, wc_path: str, rel_path: str) -> None:
        self._log_viewer.load(wc_path)
        self._content.setCurrentIndex(_PAGE_LOG)

    def _on_log_diff_requested(self, revision: int, wc_path: str) -> None:
        self._diff_viewer.load_from_wc(wc_path, revision=str(revision))
        self._content.setCurrentIndex(_PAGE_DIFF)

    def _on_conflict_resolved(self, wc_path: str, rel_path: str) -> None:
        self.statusBar().showMessage(f"Resolved: {rel_path}", 3000)
        self._status_tree.refresh()
