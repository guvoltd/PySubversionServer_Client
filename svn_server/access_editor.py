"""Access Control Editor — users, groups, path-based permissions, server config.

T-401: all sub-tasks (a-m)
"""

from __future__ import annotations
import logging

import os
import re
import subprocess
import json

from PySide6.QtCore import QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QApplication,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
import base64 # Added import

import svn_shared.svn_admin_svc as svc
from svn_shared.config_parser import (
    AuthzRule,
    PasswdEntry,
    SvnserveConfig,
    parse_authz,
    parse_passwd,
    parse_svnserve_conf,
    write_authz,
    write_passwd,
    parse_groups_from_authz, # Added import
    write_svnserve_conf,
)
from svn_shared.exceptions import SvnCommandError, SvnNotFoundError

_PKEXEC_RUNNER_DIALOG_IMPORT_NEEDED = True # Flag to indicate if PkexecRunnerDialog needs to be imported
if _PKEXEC_RUNNER_DIALOG_IMPORT_NEEDED:
    from svn_shared.widgets.pkexec_runner import PkexecRunnerDialog # Added import

logger = logging.getLogger(__name__)

_ASCII_RE = re.compile(r"^[\x20-\x7E]+$")
_PASSWD_COMPLEX_RE = re.compile(
    r"(?=.*[A-Z])(?=.*[a-z])(?=.*\d)|"
    r"(?=.*[A-Z])(?=.*[a-z])(?=.*[^A-Za-z\d])|"
    r"(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d])|"
    r"(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z\d])"
)


def _validate_password(password: str, min_len: int, complexity: bool) -> str | None:
    """Return error string or None if password is valid."""
    # logger.debug("Validating password with min_len=%d, complexity=%s", min_len, complexity)
    if not _ASCII_RE.match(password):
        # err = "Password must contain only ASCII printable characters."
        logger.debug("Password validation failed: %s", err)
        return err
    if len(password) < min_len:
        err = f"Password must be at least {min_len} characters."
        # logger.debug("Password validation failed: %s", err)
        return err
    if complexity and not _PASSWD_COMPLEX_RE.search(password):
        err = "Password must use 3 of 4 character types: A-Z, a-z, 0-9, special."
        # logger.debug("Password validation failed: %s", err)
        return err

    logger.debug("Password validation successful.")
    return None


def _fmt_size(size: int | None) -> str:
    if size is None:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size //= 1024
    return f"{size:.0f} TB"


# ---------------------------------------------------------------------------
# Add/Edit user dialog
# ---------------------------------------------------------------------------

class _UserDialog(QDialog):
    def __init__(
        self,
        min_len: int = 8,
        complexity: bool = False,
        username: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add User" if not username else "Edit Password")
        self.setMinimumWidth(360)
        self.setModal(True)
        self._min_len = min_len
        self._complexity = complexity
        self._edit_mode = bool(username)
        logger.debug("UserDialog created. Edit mode: %s", self._edit_mode)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._user_edit = QLineEdit(username)
        self._user_edit.setEnabled(not self._edit_mode)
        self._user_edit.setPlaceholderText("username")
        form.addRow("Username:", self._user_edit)

        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_edit.setPlaceholderText(f"Min {min_len} chars")
        self._pass_edit.textChanged.connect(self._validate)
        form.addRow("Password:", self._pass_edit)

        self._confirm_edit = QLineEdit()
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_edit.textChanged.connect(self._validate)
        form.addRow("Confirm:", self._confirm_edit)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #cb2431; font-size: 11px;")
        self._error_label.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(self._error_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _validate(self) -> None:
        pw = self._pass_edit.text()
        confirm = self._confirm_edit.text()
        err = _validate_password(pw, self._min_len, self._complexity)
        if err:
            self._error_label.setText(err)
            self._ok_btn.setEnabled(False)
            logger.debug("Validation error set in UI: %s", err)
            return
        if pw != confirm:
            self._error_label.setText("Passwords do not match.")
            self._ok_btn.setEnabled(False)
            logger.debug("Validation error set in UI: Passwords do not match.")
            return
        self._error_label.clear()
        self._ok_btn.setEnabled(bool(self._user_edit.text().strip()))
        logger.debug("Validation passed, OK button enabled: %s", self._ok_btn.isEnabled())

    @property
    def username(self) -> str:
        return self._user_edit.text().strip()

    @property
    def password(self) -> str:
        return self._pass_edit.text()


# ---------------------------------------------------------------------------
# Multi-member selection dialogs
# ---------------------------------------------------------------------------

class _MultiMemberAddDialog(QDialog):
    def __init__(self, group_name: str, candidates: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Add Members to @{group_name}")
        self.setMinimumWidth(320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select members to add:"))

        self._member_list = QListWidget()
        for member in sorted(candidates):
            item = QListWidgetItem(member)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._member_list.addItem(item)
        layout.addWidget(self._member_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def members_to_add(self) -> list[str]:
        added = []
        for i in range(self._member_list.count()):
            item = self._member_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                added.append(item.text())
        return added


class _MultiMemberRemoveDialog(QDialog):
    def __init__(self, group_name: str, members: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Remove Members from @{group_name}")
        self.setMinimumWidth(320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select members to remove:"))

        self._member_list = QListWidget()
        for member in sorted(members):
            item = QListWidgetItem(member)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._member_list.addItem(item)
        layout.addWidget(self._member_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def members_to_remove(self) -> list[str]:
        removed = []
        for i in range(self._member_list.count()):
            item = self._member_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                removed.append(item.text())
        return removed


class _MultiRuleAddDialog(QDialog):
    """Add a permission rule for several users/groups to one path in a single action.

    Same checkable-list pattern as _MultiMemberAddDialog above, plus a single access-level
    picker applied to every rule added — avoids having to add one user at a time and then
    edit each row's access level individually afterward.
    """

    def __init__(self, path: str, candidates: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Add Rules to {path}")
        self.setMinimumWidth(360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select users/groups to add:"))

        self._list = QListWidget()
        for candidate in candidates:
            item = QListWidgetItem(candidate)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        layout.addWidget(self._list)

        access_row = QHBoxLayout()
        access_row.addWidget(QLabel("Access level for all selected:"))
        self._access_combo = QComboBox()
        self._access_combo.addItems(["No Access", "Read Only (r)", "Read/Write (rw)"])
        self._access_combo.setCurrentIndex(1)  # Read Only — matches the prior single-add default
        access_row.addWidget(self._access_combo)
        access_row.addStretch()
        layout.addLayout(access_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected(self) -> list[str]:
        selected = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    @property
    def permission(self) -> str:
        return ["", "r", "rw"][self._access_combo.currentIndex()]


# ---------------------------------------------------------------------------
# Tab 1 — Users (local passwd)
# ---------------------------------------------------------------------------

class _UsersTab(QWidget):
    changed = Signal()
    user_added_locally = Signal(str, str) # username, password

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._users: list[PasswdEntry] = []
        self._min_len = 8
        self._complexity = False
        self._setup_ui()

    def load(self, users: list[PasswdEntry], min_len: int, complexity: bool):
        self._users = list(users)
        self._min_len = min_len
        self._complexity = complexity
        self._refresh_table()

    def get_entries(self) -> list[PasswdEntry]:
        return list(self._users)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Username", "Status"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

    def _refresh_table(self):
        self._table.setRowCount(len(self._users))
        for i, user in enumerate(self._users):
            self._table.setItem(i, 0, QTableWidgetItem(user.username))
            status = "Active" if user.active else "Suspended"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(Qt.GlobalColor.darkGreen if user.active else Qt.GlobalColor.red)
            self._table.setItem(i, 1, status_item)

    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        index = self._table.indexAt(pos)

        if index.isValid():
            idx = index.row()
            self._table.setCurrentCell(idx, 0)
            user = self._users[idx]

            edit_action = QAction("✏ Edit Password...", self)
            edit_action.triggered.connect(self._on_edit)
            menu.addAction(edit_action)

            if user.active:
                suspend_action = QAction("⛔ Suspend User", self)
                suspend_action.triggered.connect(self._on_suspend)
                menu.addAction(suspend_action)
            else:
                activate_action = QAction("✅ Activate User", self)
                activate_action.triggered.connect(self._on_activate)
                menu.addAction(activate_action)

            delete_action = QAction("🗑 Delete User", self)
            delete_action.triggered.connect(self._on_delete)
            menu.addAction(delete_action)
        else:
            add_action = QAction("➕ Add User...", self)
            add_action.triggered.connect(self._on_add)
            menu.addAction(add_action)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_add(self):
        dlg = _UserDialog(self._min_len, self._complexity, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if any(u.username == dlg.username for u in self._users):
                QMessageBox.warning(self, "User Exists", f"User '{dlg.username}' already exists.")
                return
            self._users.append(PasswdEntry(dlg.username, dlg.password, active=True))
            self.user_added_locally.emit(dlg.username, dlg.password)
            self._refresh_table()
            self.changed.emit()

    def _on_edit(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows: return
        idx = rows[0].row()
        user = self._users[idx]
        dlg = _UserDialog(self._min_len, self._complexity, username=user.username, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            user.password = dlg.password
            self.changed.emit()

    def _on_delete(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows: return
        idx = rows[0].row()
        user = self._users[idx]
        if QMessageBox.question(self, "Delete User", f"Delete user '{user.username}'?") == QMessageBox.StandardButton.Yes:
            self._users.pop(idx)
            self._refresh_table()
            self.changed.emit()

    def _on_suspend(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows: return
        idx = rows[0].row()
        self._users[idx].active = False
        self._refresh_table()
        self.changed.emit()

    def _on_activate(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows: return
        idx = rows[0].row()
        self._users[idx].active = True
        self._refresh_table()
        self.changed.emit()

# ---------------------------------------------------------------------------
# Tab 3 — Permissions (path-based authz)
# ---------------------------------------------------------------------------

class _PermissionsTab(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._rules: list[AuthzRule] = []
        self._all_users: list[str] = []
        self._all_groups: list[str] = []
        self._setup_ui()

    def load(self, rules: list[AuthzRule], all_users: list[str], all_groups: list[str]) -> None:
        logger.debug("Loading %d rules, %d users, %d groups into PermissionsTab", len(rules), len(all_users), len(all_groups))
        self._rules = list(rules)
        self._all_users = all_users
        self._all_groups = all_groups
        self._refresh_paths()
        self._rule_table.setRowCount(0)

    def get_rules(self) -> list[AuthzRule]:
        return list(self._rules)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        inherit_note = QLabel(
            "Inheritance: child paths override parent paths per user. "
            "When multiple rules at the same level, broadest access wins."
        )
        inherit_note.setWordWrap(True)
        inherit_note.setStyleSheet(
            "color: #444; background: #f0f0f0; padding: 5px; border: 1px solid #ccc;"
        )
        layout.addWidget(inherit_note)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: path list
        path_widget = QWidget()
        path_layout = QVBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)

        path_tb = QWidget()
        path_tb_layout = QHBoxLayout(path_tb)
        path_tb_layout.setContentsMargins(0, 0, 0, 4)
        add_path_btn = QPushButton("➕ Path")
        add_path_btn.clicked.connect(self._on_add_path)
        self._del_path_btn = QPushButton("🗑 Path")
        self._del_path_btn.clicked.connect(self._on_del_path)
        self._del_path_btn.setEnabled(False)
        path_tb_layout.addWidget(add_path_btn)
        path_tb_layout.addWidget(self._del_path_btn)
        path_tb_layout.addStretch()
        path_layout.addWidget(path_tb)

        self._path_list = QListWidget()
        self._path_list.currentItemChanged.connect(self._on_path_selected)
        path_layout.addWidget(self._path_list)
        splitter.addWidget(path_widget)

        # Right: rules for selected path
        rule_widget = QWidget()
        rule_layout = QVBoxLayout(rule_widget)
        rule_layout.setContentsMargins(0, 0, 0, 0)

        rule_tb = QWidget()
        rule_tb_layout = QHBoxLayout(rule_tb)
        rule_tb_layout.setContentsMargins(0, 0, 0, 4)
        self._add_rule_btn = QPushButton("➕ Rule")
        self._add_rule_btn.clicked.connect(self._on_add_rule)
        self._add_rule_btn.setEnabled(False)
        self._del_rule_btn = QPushButton("🗑 Rule")
        self._del_rule_btn.clicked.connect(self._on_del_rule)
        self._del_rule_btn.setEnabled(False)
        rule_tb_layout.addWidget(self._add_rule_btn)
        rule_tb_layout.addWidget(self._del_rule_btn)
        rule_tb_layout.addStretch()
        rule_layout.addWidget(rule_tb)

        self._rule_table = QTableWidget(0, 2)
        self._rule_table.setHorizontalHeaderLabels(["User / Group", "Access"])
        self._rule_table.horizontalHeader().setStretchLastSection(True)
        self._rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._rule_table.itemSelectionChanged.connect(self._on_rule_selection)
        self._rule_table.itemChanged.connect(self._on_rule_changed)
        rule_layout.addWidget(self._rule_table)
        splitter.addWidget(rule_widget)
        splitter.setSizes([200, 500])
        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _unique_paths(self) -> list[str]:
        seen: list[str] = []
        for r in self._rules:
            if r.section not in seen:
                seen.append(r.section)
        return seen

    def _refresh_paths(self) -> None:
        self._path_list.clear()
        for section in self._unique_paths():
            self._path_list.addItem(section)

    def _refresh_rules(self, section: str) -> None:
        section_rules = [r for r in self._rules if r.section == section]
        self._rule_table.blockSignals(True)
        self._rule_table.setRowCount(len(section_rules))
        for i, rule in enumerate(section_rules):
            self._rule_table.setItem(i, 0, QTableWidgetItem(rule.user))
            combo = QComboBox()
            combo.addItems(["No Access", "Read Only (r)", "Read/Write (rw)"])
            perm_map = {"": 0, "r": 1, "rw": 2}
            combo.setCurrentIndex(perm_map.get(rule.permission, 0))
            combo.currentIndexChanged.connect(
                lambda idx, sec=section, usr=rule.user: self._on_access_changed(sec, usr, idx)
            )
            self._rule_table.setCellWidget(i, 1, combo)
        self._rule_table.blockSignals(False)

    def _on_path_selected(self, current: QListWidgetItem | None, _prev) -> None:
        has = current is not None
        self._del_path_btn.setEnabled(has)
        self._add_rule_btn.setEnabled(has)
        if has:
            logger.debug("Path selected in UI: %s", current.text())
            self._refresh_rules(current.text())
        else:
            self._rule_table.setRowCount(0)

    def _on_rule_selection(self) -> None:
        self._del_rule_btn.setEnabled(bool(self._rule_table.selectedItems()))

    def _on_add_path(self) -> None:
        path, ok = QInputDialog.getText(self, "Add Path", "Path (e.g. / or repo:/trunk):")
        if ok and path.strip():
            section = f"[{path.strip().strip('[]')}]"
            logger.debug("Attempting to add new authz path: %s", section)
            if section not in self._unique_paths():
                logger.info("Adding new authz path: %s", section)
                self._rules.append(AuthzRule(section=section, user="*", permission=""))
                self._refresh_paths()
                self.changed.emit()
            else:
                logger.warning("Attempted to add duplicate authz path: %s", section)

    def _on_del_path(self) -> None:
        item = self._path_list.currentItem()
        if not item:
            return
        section = item.text()
        logger.info("Deleting authz path and all its rules: %s", section)
        self._rules = [r for r in self._rules if r.section != section]
        self._refresh_paths()
        self._rule_table.setRowCount(0)
        self.changed.emit()

    def _on_add_rule(self) -> None:
        logger.debug("Add Rule button clicked.")
        item = self._path_list.currentItem()
        if not item:
            return

        section = item.text()
        existing = {r.user for r in self._rules if r.section == section}
        candidates = [
            c for c in self._all_users + [f"@{g}" for g in self._all_groups] + ["*"]
            if c not in existing
        ]
        if not candidates:
            QMessageBox.information(
                self, "Add Rule", "Every available user and group already has a rule on this path."
            )
            return

        dlg = _MultiRuleAddDialog(section, candidates, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            logger.debug("Add rule dialog cancelled.")
            return

        selected = dlg.selected
        if not selected:
            logger.debug("Add rule dialog accepted with no users/groups selected.")
            return

        permission = dlg.permission
        logger.info(
            "Adding %d rule(s) to '%s' with access '%s': %s",
            len(selected), section, permission or "(none)", selected,
        )
        for user in selected:
            self._rules.append(AuthzRule(section=section, user=user, permission=permission))
        self._refresh_rules(section)
        self.changed.emit()

    def _on_del_rule(self) -> None:
        item = self._path_list.currentItem()
        if not item:
            return
        selected = self._rule_table.selectedItems()
        if not selected:
            return
        row = self._rule_table.row(selected[0])
        section = item.text()
        section_rules = [r for r in self._rules if r.section == section]
        if row < len(section_rules):
            rule = section_rules[row]
            logger.info("Deleting rule: %s -> %s", rule.section, rule.user)
            self._rules.remove(rule)
            self._refresh_rules(section)
            self.changed.emit()

    def _on_rule_changed(self, table_item: QTableWidgetItem) -> None:
        # Username cell edited
        pass

    def _on_access_changed(self, section: str, user: str, idx: int) -> None:
        perm = ["", "r", "rw"][idx]
        for rule in self._rules:
            if rule.section == section and rule.user == user:
                logger.info("Changing permission for '%s' in '%s' to '%s'", user, section, perm)
                rule.permission = perm
                self.changed.emit()
                break


# ---------------------------------------------------------------------------
# Tab 4 — Server Config (svnserve.conf)
# ---------------------------------------------------------------------------

class _ServerConfigTab(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._config: SvnserveConfig | None = None
        self._setup_ui()

    def load(self, config: SvnserveConfig) -> None:
        logger.debug("Loading svnserve.conf into ServerConfigTab")
        self._config = config
        self._anon_combo.setCurrentText(config.anon_access)
        self._auth_combo.setCurrentText(config.auth_access)
        self._realm_edit.setText(config.realm)
        # Password DB is now global and read-only in this view
        global_passwd = self._settings.value("Server/global_passwd_file", "")
        self._passwd_edit.setText(global_passwd)
        self._authz_edit.setText(config.authz_db)

    def get_config(self) -> SvnserveConfig | None:
        if not self._config:
            logger.warning("get_config called before load.")
            return None
        self._config.anon_access = self._anon_combo.currentText()
        self._config.auth_access = self._auth_combo.currentText()
        self._config.realm = self._realm_edit.text().strip()
        self._config.password_db = self._passwd_edit.text().strip() # It's read-only, but we read it back
        self._config.authz_db = self._authz_edit.text().strip()
        return self._config

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        group = QGroupBox("svnserve.conf Settings")
        form = QFormLayout(group)

        self._anon_combo = QComboBox()
        self._anon_combo.addItems(["none", "read", "write"])
        self._anon_combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        form.addRow("Anonymous access:", self._anon_combo)

        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["none", "read", "write"])
        self._auth_combo.setCurrentText("write")
        self._auth_combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        form.addRow("Authenticated access:", self._auth_combo)

        self._realm_edit = QLineEdit()
        self._realm_edit.setPlaceholderText("My SVN Repository")
        self._realm_edit.textChanged.connect(lambda _: self.changed.emit())
        form.addRow("Realm:", self._realm_edit)

        self._passwd_edit = QLineEdit("passwd")
        self._passwd_edit.setReadOnly(True) # Make this read-only
        self._passwd_edit.textChanged.connect(lambda _: self.changed.emit())
        form.addRow("Password DB:", self._passwd_edit)
        self._passwd_edit.setReadOnly(False)
        self._passwd_edit.setToolTip("Path to the password file, relative to the conf/ directory (e.g., 'passwd') or absolute.")

        self._authz_edit = QLineEdit("authz")
        self._authz_edit.textChanged.connect(lambda _: self.changed.emit())
        form.addRow("Authz file:", self._authz_edit)
        self._authz_edit.setToolTip("Path to the authorization file, relative to the conf/ directory.")

        layout.addWidget(group)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class AccessEditor(QWidget):
    """Access control editor for a single SVN repository.

    Saves to svnserve.conf, authz, and passwd files in the repo's conf/ dir.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._SVN_USER = "svn"
        self._SVN_GROUP = "svnserver"

        self._settings = QSettings()
        self._repo_path: str | None = None
        self._dirty = False
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, repo_path: str) -> None:
        logger.info("Loading access editor for repo: %s", repo_path)
        self._repo_path = repo_path
        conf_dir = os.path.join(repo_path, "conf")

        try:
            logger.debug("Loading repository info...")
            info = svc.repo_info(repo_path)

            try:
                hostname = subprocess.check_output(['hostname'], text=True).strip()
                if not hostname:
                    hostname = "localhost"
            except (subprocess.CalledProcessError, FileNotFoundError):
                hostname = "localhost"

            url = f"svn://{hostname}.local/{info.name}"

            self._lbl_path.setText(info.path)
            self._lbl_url.setText(url)
            self._lbl_uuid.setText(info.uuid)
            self._lbl_rev.setText(str(info.head_revision))
            self._lbl_fs.setText(info.fs_type)
            self._lbl_size.setText(_fmt_size(info.size_bytes))
            self._info_group.setTitle(f"Repository — {info.name}")
            self._info_group.setVisible(True)
        except (SvnCommandError, SvnNotFoundError, OSError) as e:
            self._info_group.setVisible(False)
            logger.error("Could not load repository info for %s: %s", repo_path, e)
            QMessageBox.warning(self, "Could not load repository info", str(e))

        # Load global users for permission editor
        global_passwd_file = self._settings.value("Server/global_passwd_file", "")
        global_users = []
        if global_passwd_file and os.path.exists(global_passwd_file):
            logger.debug("Loading global users from: %s", global_passwd_file)
            global_users = [u.username for u in parse_passwd(global_passwd_file) if u.active]
            logger.debug("Found %d active global users.", len(global_users))
        else:
            logger.debug("Global password file not configured or does not exist.")

        # Load local users
        passwd_file = os.path.join(conf_dir, "passwd")
        local_user_entries: list[PasswdEntry] = []
        if os.path.exists(passwd_file):
            try:
                local_user_entries = parse_passwd(passwd_file)
            except Exception as e:
                logger.error("Failed to parse local passwd file %s: %s", passwd_file, e)

        min_len = int(self._settings.value("Server/pw_min_length", 8))
        complexity = self._settings.value("Server/pw_complexity", False, type=bool)
        self._users_tab.load(local_user_entries, min_len, complexity)

        local_users = [u.username for u in local_user_entries if u.active]
        all_available_users = sorted(list(set(global_users + local_users)))
        
        # Load authz (rules + groups)
        authz_file = os.path.join(conf_dir, "authz")
        logger.debug("Loading authz file from: %s", authz_file)
        rules: list[AuthzRule] = []
        groups: dict[str, list[str]] = parse_groups_from_authz(authz_file) # Changed to use new function
        logger.debug("Found %d authz groups.", len(groups))
        if os.path.exists(authz_file):
            rules = parse_authz(authz_file)
            logger.debug("Found %d authz rules.", len(rules))

        # Load svnserve.conf
        conf_file = os.path.join(conf_dir, "svnserve.conf")
        logger.debug("Loading svnserve.conf from: %s", conf_file)
        config = (
            parse_svnserve_conf(conf_file)
            if os.path.exists(conf_file)
            else SvnserveConfig()
        )

        logger.debug("Populating UI tabs with loaded data.")
        self._perms_tab.load(rules, all_available_users, list(groups.keys()))
        self._config_tab.load(config)
        self._dirty = False
        self._save_btn.setEnabled(False)
        logger.info("Finished loading access editor for %s", repo_path)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()

        self._info_tab = self._build_info_tab()
        self._tabs.addTab(self._info_tab, "Repo Info")

        self._users_tab = _UsersTab()
        self._users_tab.changed.connect(self._on_dirty)
        self._users_tab.user_added_locally.connect(self._add_user_to_global_file)
        self._tabs.addTab(self._users_tab, "Users")

        self._perms_tab = _PermissionsTab()
        self._perms_tab.changed.connect(self._on_dirty)
        self._tabs.addTab(self._perms_tab, "Permissions")

        self._config_tab = _ServerConfigTab()
        self._config_tab.changed.connect(self._on_dirty)
        self._tabs.addTab(self._config_tab, "Server Config")

        layout.addWidget(self._tabs)

        # Save button
        save_bar = QWidget()
        save_layout = QHBoxLayout(save_bar)
        save_layout.setContentsMargins(4, 4, 4, 4)
        save_layout.addStretch()
        self._save_btn = QPushButton("💾 Save Changes")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        save_layout.addWidget(self._save_btn)
        layout.addWidget(save_bar)

    def _build_info_tab(self) -> QWidget:
        info_widget = QWidget()
        layout = QVBoxLayout(info_widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self._info_group = QGroupBox("Repository Info")
        self._info_group.setVisible(False) # Hide until loaded
        info_form = QFormLayout(self._info_group)
        self._lbl_path = QLabel("—")

        url_row = QWidget()
        url_layout = QHBoxLayout(url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        self._lbl_url = QLineEdit("—")
        self._lbl_url.setReadOnly(True)
        self._lbl_url.setStyleSheet("background:transparent; border:none;")
        self._copy_url_btn = QPushButton("📋")
        self._copy_url_btn.setFixedSize(24, 24)
        self._copy_url_btn.setToolTip("Copy URL to clipboard")
        self._copy_url_btn.clicked.connect(self._on_copy_url)
        url_layout.addWidget(self._lbl_url)
        url_layout.addWidget(self._copy_url_btn)

        self._lbl_uuid = QLabel("—")
        self._lbl_rev = QLabel("—")
        self._lbl_fs = QLabel("—")
        self._lbl_size = QLabel("—")
        for row_label, widget in (
            ("Path:", self._lbl_path),
            ("Checkout URL:", url_row),
            ("UUID:", self._lbl_uuid),
            ("HEAD rev:", self._lbl_rev),
            ("FS type:", self._lbl_fs),
            ("Size:", self._lbl_size),
        ):
            info_form.addRow(row_label, widget)

        self._fix_perms_btn = QPushButton("Fix Permissions")
        self._fix_perms_btn.setToolTip(
            "Reset ownership and permissions for this repository to allow the 'svn' user access.\n"
            "Use this if you are getting 'No repository found' errors for an existing repository."
        )
        self._fix_perms_btn.clicked.connect(self._on_fix_permissions)
        info_form.addRow("", self._fix_perms_btn)

        layout.addWidget(self._info_group)
        layout.addStretch()
        return info_widget

    def _on_dirty(self) -> None:
        self._dirty = True
        self._save_btn.setEnabled(True)

    def _on_copy_url(self) -> None:
        QApplication.clipboard().setText(self._lbl_url.text())
        self.window().statusBar().showMessage("Checkout URL copied to clipboard", 2000)

    def _on_fix_permissions(self) -> None:
        if not self._repo_path:
            return
        name = os.path.basename(self._repo_path)
        reply = QMessageBox.question(
            self,
            "Fix Repository Permissions",
            f"This will reset the ownership of the repository '{name}' to the '{self._SVN_USER}:{self._SVN_GROUP}' user and group, "
            "and apply recommended directory permissions. This is the correct fix for 'No repository found' errors on an existing repository.\n\n"
            "Administrative privileges are required.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_helper_script(["set_ownership", self._repo_path, self._SVN_USER, self._SVN_GROUP])
            self.window().statusBar().showMessage(f"Permissions fixed for '{name}'.", 5000)

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

    def _add_user_to_global_file(self, username: str, password: str) -> None:
        """
        When a user is added to the local passwd file via the UI, this slot
        is called to also add them to the global password file.
        """
        global_passwd_file = self._settings.value("Server/global_passwd_file", "")
        if not global_passwd_file:
            self.window().statusBar().showMessage("Global password file not configured. User not added globally.", 5000)
            return

        try:
            global_users = parse_passwd(global_passwd_file) if os.path.exists(global_passwd_file) else []
        except Exception as e:
            QMessageBox.critical(self, "Error Reading Global Users", f"Could not read global password file:\n{e}")
            return

        if any(u.username == username for u in global_users):
            logger.debug("User '%s' already exists in global password file. Skipping.", username)
            return

        logger.info("Adding new user '%s' to global password file: %s", username, global_passwd_file)
        global_users.append(PasswdEntry(username, password, active=True))

        try:
            passwd_data = [{"username": u.username, "password": u.password, "active": u.active} for u in global_users]
            encoded_data = base64.b64encode(json.dumps(passwd_data).encode()).decode()
            
            # Use the helper script to write the file with elevated privileges.
            self._run_helper_script(["write_config_via_python", "passwd", global_passwd_file, encoded_data])
            self.window().statusBar().showMessage(f"User '{username}' also added to global password file.", 3000)

        except Exception as e:
            logger.error("Failed to write to global password file: %s", e, exc_info=True)
            QMessageBox.critical(self, "Save Failed", f"Could not save global password file:\n{e}")

    def _expand_group(self, group_name: str, groups: dict[str, list[str]], visited: set[str]) -> set[str]:
        """Recursively expand a group to get all user members, handling circular dependencies."""
        if group_name in visited:
            logger.warning("Circular dependency detected in authz groups involving '@%s'", group_name)
            return set()
        visited.add(group_name)

        members = groups.get(group_name, [])
        users = set()
        for member in members:
            if member.startswith('@'):
                nested_group_name = member[1:]
                users.update(self._expand_group(nested_group_name, groups, visited))
            else:
                users.add(member)
        
        visited.remove(group_name)
        return users

    def _get_users_with_access(self, rules: list[AuthzRule], groups: dict[str, list[str]]) -> tuple[set[str], bool]:
        """
        Parses all authz rules to determine the set of all users who have
        at least read access to at least one path.
        Returns a set of usernames and a boolean indicating if '*' has access.
        """
        users_with_access = set()
        wildcard_has_access = False

        for rule in rules:
            # We only care about rules that grant access. Empty permission means "No Access".
            if rule.permission in ('r', 'rw'):
                user_or_group = rule.user
                if user_or_group == '*':
                    wildcard_has_access = True
                    # If wildcard has access, we can technically stop, but we'll continue
                    # just to be thorough, as the boolean flag is the primary signal.
                    continue 
                
                if user_or_group.startswith('@'):
                    group_name = user_or_group[1:]
                    # Pass a new visited set for each top-level group expansion
                    expanded_users = self._expand_group(group_name, groups, set())
                    users_with_access.update(expanded_users)
                else:
                    users_with_access.add(user_or_group)

        return users_with_access, wildcard_has_access

    def _on_save(self) -> None:
        if not self._repo_path:
            logger.warning("_on_save called with no repo path set.")
            return
        logger.info("Saving access configuration for repo: %s", self._repo_path)
        conf_dir = os.path.join(self._repo_path, "conf")
        os.makedirs(conf_dir, exist_ok=True)

        try:
            authz_path = os.path.join(conf_dir, "authz")
            # Since group editing is removed, re-parse groups from file to preserve them.
            groups = parse_groups_from_authz(authz_path) if os.path.exists(authz_path) else {}
            logger.debug("Getting rules from UI tab.")
            rules = self._perms_tab.get_rules()
            authz_content = self._generate_authz_content(groups, rules)
            logger.debug("Generated authz content (%d lines).", len(authz_content.splitlines()))

            # The user wants to manage the passwd file independently from the authz rules.
            # The previous synchronization logic was too aggressive, as it prevented
            # pre-adding users to the passwd file before granting them permissions.
            # Now, the passwd file will simply reflect the state of the 'Users' tab.
            all_local_users = self._users_tab.get_entries()
            passwd_data = None
            if all_local_users:
                passwd_data = [{"username": u.username, "password": u.password, "active": u.active} for u in all_local_users]
                logger.debug("Generated local passwd data for %d users.", len(all_local_users))

            logger.debug("Getting config from UI tab.")
            config = self._config_tab.get_config()
            config_data = None
            if config:
                config_data = {
                    "anon_access": config.anon_access, "auth_access": config.auth_access,
                    "password_db": config.password_db, "authz_db": config.authz_db,
                    "realm": config.realm
                }
                logger.debug("Generated svnserve.conf data.")

            # Create a single JSON object for all files
            batch_payload = {
                "authz": [{"path": authz_path, "data": authz_content}],
            }
            if passwd_data:
                logger.debug("Adding passwd to batch payload.")
                passwd_path = os.path.join(conf_dir, "passwd")
                batch_payload["passwd"] = [{"path": passwd_path, "data": passwd_data}]

            if config_data:
                logger.debug("Adding svnserve.conf to batch payload.")
                svnserve_conf_path = os.path.join(conf_dir, "svnserve.conf")
                batch_payload["svnserve_conf"] = [{"path": svnserve_conf_path, "data": config_data}]

            logger.debug("Encoding configuration data for helper script:batch_payload={batch_payload}")
            print("Encoding configuration data for helper script:batch_payload={batch_payload}")
            encoded_batch = base64.b64encode(json.dumps(batch_payload).encode()).decode()
            logger.debug("Calling helper script 'write_repo_configs'.")
            self._run_helper_script(["write_repo_configs", encoded_batch])

            self._dirty = False
            self._save_btn.setEnabled(False)
            logger.info("Successfully saved access configuration.")
            QMessageBox.information(self, "Saved", "Access configuration saved.")
        except Exception as exc:
            logger.error("Failed to save access configuration: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Save Failed", str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_authz_content(groups: dict[str, list[str]], rules: list[AuthzRule]) -> str:
        lines = ["[groups]"]
        for grp, members in groups.items():
            lines.append(f"{grp} = {', '.join(members)}")
        lines.append("")

        sections: dict[str, list[tuple[str, str]]] = {}
        for rule in rules:
            key = rule.section.strip("[]")
            sections.setdefault(key, []).append((rule.user, rule.permission))

        for section, entries in sections.items():
            lines.append(f"[{section}]")
            for user, perm in entries:
                lines.append(f"{user} = {perm}")
            lines.append("")

        return "\n".join(lines) + "\n"
