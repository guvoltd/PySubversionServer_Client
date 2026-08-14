"""Hook Manager — install, enable, disable SVN repository hooks.

T-402: all sub-tasks (a-g)
"""

from __future__ import annotations
import logging

import base64
import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import svn_shared.hook_templates as tmpl
from svn_shared.hook_templates import HookInfo, HookTemplate
from svn_shared.widgets.pkexec_runner import PkexecRunnerDialog
from svn_shared.widgets.syntax_highlighter import ShellHighlighter

logger = logging.getLogger(__name__)

# All 9 standard SVN hook names
_ALL_HOOKS = [
    "start-commit",
    "pre-commit",
    "post-commit",
    "pre-lock",
    "post-lock",
    "pre-unlock",
    "post-unlock",
    "pre-revprop-change",
    "post-revprop-change",
]

# Parameter reference for each hook
_HOOK_PARAMS: dict[str, str] = {
    "start-commit": "$1 = repos path\n$2 = username\n$3 = capabilities",
    "pre-commit": "$1 = repos path\n$2 = transaction name",
    "post-commit": "$1 = repos path\n$2 = revision number",
    "pre-lock": "$1 = repos path\n$2 = path being locked\n$3 = username\n$4 = comment\n$5 = steal-lock flag",
    "post-lock": "$1 = repos path\n$2 = username",
    "pre-unlock": "$1 = repos path\n$2 = path being unlocked\n$3 = username\n$4 = lock token\n$5 = break-lock flag",
    "post-unlock": "$1 = repos path\n$2 = username",
    "pre-revprop-change": "$1 = repos path\n$2 = revision\n$3 = username\n$4 = property name\n$5 = action (M/D/A)",
    "post-revprop-change": "$1 = repos path\n$2 = revision\n$3 = username\n$4 = property name\n$5 = action (M/D/A)",
}

_STATUS_COLORS = {
    "Enabled":      "#22863a",
    "Disabled":     "#856404",
    "Not installed": "#6a737d",
}


class HookManager(QWidget):
    """Hook editor panel for a single SVN repository.

    Loads all 9 hook types, shows enable/disable status, lets the user
    edit hook content with ShellHighlighter and load from built-in templates.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        logger.debug("HookManager instance created.")
        self._settings = QSettings()
        self._repo_path: str | None = None
        self._hook_info: dict[str, HookInfo] = {}  # name -> HookInfo
        self._current_hook: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, repo_path: str) -> None:
        logger.info("Loading hooks for repository: %s", repo_path)
        self._repo_path = repo_path
        installed = {h.name: h for h in tmpl.list_hooks(repo_path)}
        self._hook_info = {}
        logger.debug("Found %d installed hooks from hook_templates.list_hooks.", len(installed))

        self._hook_list.clear()
        for hook_name in _ALL_HOOKS:
            info = installed.get(hook_name)
            if info:
                logger.debug("Processing hook '%s': status is %s.", hook_name, "Enabled" if info.enabled else "Disabled")
                self._hook_info[hook_name] = info
                status = "Enabled" if info.enabled else "Disabled"
            else:
                logger.debug("Processing hook '%s': status is Not installed.", hook_name)
                status = "Not installed"
            item = QListWidgetItem(hook_name)
            color = _STATUS_COLORS[status]
            item.setToolTip(f"Status: {status}")
            item.setForeground(Qt.GlobalColor.black)
            item.setData(Qt.ItemDataRole.UserRole, hook_name)
            item.setData(Qt.ItemDataRole.UserRole + 1, status)
            # Append status badge to text
            item.setText(f"{hook_name}   [{status}]")
            self._hook_list.addItem(item)

        self._hook_list.setCurrentRow(0)
        logger.debug("Hook list UI populated.")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: hook list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(QLabel("<b>SVN Hooks</b>"))

        self._hook_list = QListWidget()
        self._hook_list.setMaximumWidth(240)
        self._hook_list.currentItemChanged.connect(self._on_hook_selected)
        left_layout.addWidget(self._hook_list)
        splitter.addWidget(left)

        # Right: editor area
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(4)

        # Toolbar row
        editor_tb = QWidget()
        editor_tb_layout = QHBoxLayout(editor_tb)
        editor_tb_layout.setContentsMargins(0, 0, 0, 0)

        self._enable_btn = QPushButton("✅ Enable")
        self._enable_btn.clicked.connect(self._on_enable)
        self._disable_btn = QPushButton("⛔ Disable")
        self._disable_btn.clicked.connect(self._on_disable)
        self._save_btn = QPushButton("💾 Save")
        self._save_btn.clicked.connect(self._on_save)
        editor_tb_layout.addWidget(self._enable_btn)
        editor_tb_layout.addWidget(self._disable_btn)
        editor_tb_layout.addStretch()

        editor_tb_layout.addWidget(QLabel("Template:"))
        self._template_combo = QComboBox()
        self._template_combo.addItem("— select template —")
        for t in tmpl.list_templates():
            self._template_combo.addItem(t.name, t)
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        editor_tb_layout.addWidget(self._template_combo)
        editor_tb_layout.addWidget(self._save_btn)
        right_layout.addWidget(editor_tb)

        # Editor
        self._editor = QPlainTextEdit()
        self._editor.setFont(self._monospace_font())
        self._highlighter = ShellHighlighter(self._editor.document())
        right_layout.addWidget(self._editor)

        # Collapsible params reference
        self._params_group = QGroupBox("Hook Parameters Reference")
        self._params_group.setCheckable(True)
        self._params_group.setChecked(False)
        params_layout = QVBoxLayout(self._params_group)
        self._params_label = QLabel()
        self._params_label.setStyleSheet("font-family: monospace; font-size: 12px; color: #444;")
        params_layout.addWidget(self._params_label)
        right_layout.addWidget(self._params_group)

        splitter.addWidget(right)
        splitter.setSizes([220, 780])
        layout.addWidget(splitter)

    @staticmethod
    def _monospace_font():
        from PySide6.QtGui import QFont
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(10)
        return font

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_hook_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if not current or not self._repo_path:
            logger.debug("_on_hook_selected called with no item or repo path, returning.")
            return
        hook_name = current.data(Qt.ItemDataRole.UserRole)
        status = current.data(Qt.ItemDataRole.UserRole + 1)
        self._current_hook = hook_name
        logger.debug("Hook selected: %s, Status: %s", hook_name, status)

        # Load content
        info = self._hook_info.get(hook_name)
        if info and os.path.exists(info.path):
            logger.debug("Loading content from existing hook file: %s", info.path)
            with open(info.path, errors="replace") as f:
                self._editor.setPlainText(f.read())
        else:
            logger.debug("No existing hook file found, populating editor with default template.")
            self._editor.setPlainText(
                f"#!/bin/bash\n# {hook_name} hook\n# Add your hook logic here.\nexit 0\n"
            )

        # Update params
        self._params_label.setText(_HOOK_PARAMS.get(hook_name, ""))

        # Button state
        self._enable_btn.setEnabled(status == "Disabled")
        self._disable_btn.setEnabled(status == "Enabled")

    def _on_template_selected(self, idx: int) -> None:
        if idx <= 0:
            logger.debug("Template dropdown reset, no action taken.")
            return
        template: HookTemplate = self._template_combo.itemData(idx)
        if template:
            logger.debug("Template selected: %s", template.name)
            reply = QMessageBox.question(
                self, "Load Template",
                f"Replace editor content with template '{template.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                logger.info("Loading template '%s' into editor.", template.name)
                self._editor.setPlainText(template.content)
            else:
                logger.debug("User cancelled loading template.")
        self._template_combo.setCurrentIndex(0)

    def _on_save(self) -> None:
        if not self._repo_path or not self._current_hook:
            return
        content = self._editor.toPlainText()
        logger.info("Saving hook '%s' for repo '%s'.", self._current_hook, self._repo_path)
        encoded = base64.b64encode(content.encode()).decode()
        self._run_helper_script(["write_hook", self._repo_path, self._current_hook, encoded])
        self.load(self._repo_path)

    def _on_enable(self) -> None:
        if not self._repo_path or not self._current_hook:
            return
        logger.info("Enabling hook '%s' for repo '%s'.", self._current_hook, self._repo_path)
        self._run_helper_script(["enable_hook", self._repo_path, self._current_hook])
        self.load(self._repo_path)

    def _on_disable(self) -> None:
        if not self._repo_path or not self._current_hook:
            return
        logger.info("Disabling hook '%s' for repo '%s'.", self._current_hook, self._repo_path)
        self._run_helper_script(["disable_hook", self._repo_path, self._current_hook])
        self.load(self._repo_path)

    def _run_helper_script(self, args: list[str]) -> None:
        """Runs the privileged helper script via pkexec and shows output.

        Repositories (and their hooks/ directory) are owned by svn:svnserver with no
        group-write bit, so hook writes/enable/disable can't be done directly by the
        invoking desktop user — see system-helper.sh's write_hook/enable_hook/disable_hook.
        """
        helper_path = "/usr/bin/svn-server-admin-helper"
        dev_path = os.path.join(os.path.dirname(__file__), "resources", "system-helper.sh")
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
