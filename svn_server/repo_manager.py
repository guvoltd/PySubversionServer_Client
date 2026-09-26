"""Repository Manager panel — create, list, delete, import SVN repositories.

T-400: all sub-tasks (a-g)
"""

from __future__ import annotations
import base64
import json
import logging
import os
import subprocess
from datetime import datetime
 
from PySide6.QtCore import QPoint, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QInputDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QRadioButton,
    QApplication,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_admin_svc as svc
from svn_shared.config_parser import AuthzRule, PasswdEntry, parse_authz, parse_groups_from_authz, parse_passwd
from svn_shared.exceptions import ConfigParseError, SvnCommandError, SvnNotFoundError
from svn_shared.widgets.pkexec_runner import PkexecRunnerDialog
from svn_shared.widgets.progress_overlay import ProgressOverlay

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_size(size: int | None) -> str:
    if size is None:
        return "unknown"
    #for unit in ("B", "KB", "MB", "GB"):
    #    if size < 1024:
    #        return f"{size:.0f} {unit}"
    #    size //= 1024
    #return f"{size:.0f} TB"
    if size == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    f_size = float(size)
    i = 0
    while f_size >= 1024 and i < len(units) - 1:
        f_size /= 1024
        i += 1
    return f"{f_size:.1f} {units[i]}" if i > 0 else f"{f_size:.0f} {units[i]}"

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


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _Worker(QThread):
    finished = Signal(object)  # result (varies)
    error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(result)
        except (SvnCommandError, SvnNotFoundError, OSError) as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Create dialog
# ---------------------------------------------------------------------------

class _CreateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Repository")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("my-repo")
        self._name_edit.textChanged.connect(self._validate)
        form.addRow("Name:", self._name_edit)

        self._fsfs_radio = QRadioButton("FSFS (default, recommended)")
        self._fsx_radio = QRadioButton("FSX (experimental)")
        self._fsfs_radio.setChecked(True)
        form.addRow("Backend:", self._fsfs_radio)
        form.addRow("", self._fsx_radio)

        self._std_layout = QCheckBox("Create trunk / branches / tags structure")
        self._std_layout.setChecked(True)
        form.addRow("", self._std_layout)

        self._configure_access_cb = QCheckBox("Configure access control after creation")
        self._configure_access_cb.setChecked(True)
        form.addRow("", self._configure_access_cb)

        layout.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Create")
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _validate(self) -> None:
        self._ok_btn.setEnabled(bool(self._name_edit.text().strip()))

    @property
    def repo_name(self) -> str:
        return self._name_edit.text().strip()

    @property
    def fs_type(self) -> str:
        return "fsfs" if self._fsfs_radio.isChecked() else "fsx"

    @property
    def standard_layout(self) -> bool:
        return self._std_layout.isChecked()

    @property
    def configure_access(self) -> bool:
        return self._configure_access_cb.isChecked()

from svn_server.access_editor import _UserDialog, _validate_password, _MultiMemberAddDialog, _MultiMemberRemoveDialog



# ---------------------------------------------------------------------------
# Initial rights dialog
# ---------------------------------------------------------------------------

class _InitialRightsDialog(QDialog):
    def __init__(self, users: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Initial Repository Permissions")
        self.setMinimumWidth(320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select users to grant full read/write access:"))

        self._user_list = QListWidget()
        for user in users:
            item = QListWidgetItem(user)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._user_list.addItem(item)
        layout.addWidget(self._user_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_users(self) -> list[str]:
        selected = []
        for i in range(self._user_list.count()):
            item = self._user_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected


# ---------------------------------------------------------------------------
# Global Groups Tab
# ---------------------------------------------------------------------------

class _GroupsGlobalManagerTab(QWidget):
    """A tab for managing groups in a global authz file."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._repo_manager = parent
        self._settings = QSettings()
        self._groups: dict[str, list[str]] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Group / Member"])
        self._tree.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._tree)

        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

    def showEvent(self, event):
        self.load_groups()
        super().showEvent(event)

    def load_groups(self):
        authz_file = self._settings.value("Server/global_authz_file", "")
        if not authz_file:
            self._tree.clear()
            self._tree.setEnabled(False)
            QMessageBox.warning(self, "Not Configured", "A global authz file path has not been set.\nPlease configure it in File > Settings.")
            return

        if not os.path.exists(authz_file):
            # Don't prompt to create here, as it's less critical than the passwd file.
            # Saving will create it.
            self._groups = {}
        else:
            try:
                self._groups = parse_groups_from_authz(authz_file)
            except (ConfigParseError, OSError) as e:
                QMessageBox.critical(self, "Error Loading Groups", str(e))
                self._groups = {}

        self._tree.setEnabled(True)
        self._refresh_tree()

    def _refresh_tree(self):
        self._tree.clear()
        for grp_name, members in sorted(self._groups.items()):
            grp_item = QTreeWidgetItem([f"@{grp_name}"])
            grp_item.setData(0, Qt.ItemDataRole.UserRole, ("group", grp_name))
            for member in sorted(members):
                mem_item = QTreeWidgetItem([member])
                mem_item.setData(0, Qt.ItemDataRole.UserRole, ("member", grp_name, member))
                grp_item.addChild(mem_item)
            self._tree.addTopLevelItem(grp_item)
            grp_item.setExpanded(True)

    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        item = self._tree.itemAt(pos)

        if item:
            self._tree.setCurrentItem(item)

        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None

        if data and data[0] == "group":
            add_member_action = QAction("➕ Add Member...", self)
            add_member_action.triggered.connect(self._on_add_member)
            menu.addAction(add_member_action)

            remove_members_action = QAction("🗑 Remove Members...", self)
            remove_members_action.triggered.connect(self._on_remove_members)
            menu.addAction(remove_members_action)

            rename_group_action = QAction("✏ Rename Group...", self)
            rename_group_action.triggered.connect(self._on_rename_group)
            menu.addAction(rename_group_action)
            delete_group_action = QAction("🗑 Delete Group", self)
            delete_group_action.triggered.connect(self._on_delete_group)
            menu.addAction(delete_group_action)
        # No actions for member items directly anymore
        elif not data: # Clicked on empty space
            new_group_action = QAction("➕ New Group...", self)
            new_group_action.triggered.connect(self._on_new_group)
            menu.addAction(new_group_action)

        menu.addSeparator()
        refresh_action = QAction("🔄 Refresh", self)
        refresh_action.triggered.connect(self.load_groups)
        menu.addAction(refresh_action)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_selection(self):
        # This is now handled by the context menu logic, but we keep it for potential future use.
        pass

    def _selected_group_and_member(self) -> tuple[str | None, str | None]:
        items = self._tree.selectedItems()
        if not items: return None, None
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if data[0] == "group": return data[1], None
        if data[0] == "member": return data[1], data[2]
        return None, None

    def _on_new_group(self):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if ok and name.strip():
            name = name.strip().lstrip("@")
            if name in self._groups:
                QMessageBox.warning(self, "Duplicate", f"Group '@{name}' already exists.")
                return
            self._groups[name] = []
            self._save_groups()

    def _on_rename_group(self):
        grp, _ = self._selected_group_and_member()
        if not grp: return
        new_name, ok = QInputDialog.getText(self, "Rename Group", "New name:", text=grp)
        if ok and new_name.strip() and new_name.strip() != grp:
            new_name = new_name.strip().lstrip("@")
            members = self._groups.pop(grp)
            self._groups[new_name] = members
            self._save_groups()

    def _on_delete_group(self):
        grp, _ = self._selected_group_and_member()
        if not grp: return
        if QMessageBox.question(self, "Delete Group", f"Delete group '@{grp}'?") == QMessageBox.StandardButton.Yes:
            self._groups.pop(grp, None)
            self._save_groups()

    def _on_add_member(self):
        grp, _ = self._selected_group_and_member()
        if not grp: return

        passwd_file = self._settings.value("Server/global_passwd_file", "")
        if not passwd_file or not os.path.exists(passwd_file):
            QMessageBox.warning(self, "Cannot Add Member", "Global password file is not configured or does not exist.\nCannot retrieve user list.")
            return

        try:
            all_users = [u.username for u in parse_passwd(passwd_file) if u.active]
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load user list:\n{e}")
            return

        current_members = self._groups.get(grp, [])
        candidates = sorted([u for u in all_users if u not in current_members])

        if not candidates:
            QMessageBox.information(self, "No Users to Add", f"All available users are already in the group '@{grp}'.")
            return

        dlg = _MultiMemberAddDialog(grp, candidates, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            to_add = dlg.members_to_add
            if not to_add:
                return
            logger.info("Adding %d members to group '%s'", len(to_add), grp)
            self._groups[grp].extend(to_add)
            self._save_groups()

    def _on_remove_members(self):
        grp, _ = self._selected_group_and_member()
        if not grp: return
        current_members = self._groups.get(grp, [])
        if not current_members:
            QMessageBox.information(self, "No Members", f"The group '@{grp}' has no members to remove.")
            return

        dlg = _MultiMemberRemoveDialog(grp, current_members, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            to_remove = dlg.members_to_remove
            if not to_remove:
                return
            self._groups[grp] = [m for m in current_members if m not in to_remove]
            self._save_groups()

    def _save_groups(self):
        authz_file = self._settings.value("Server/global_authz_file", "")
        if not authz_file:
            QMessageBox.critical(self, "Save Failed", "Global authz file is not configured in Settings.")
            return

        try:
            # Preserve existing path rules in the global file
            existing_rules = parse_authz(authz_file) if os.path.exists(authz_file) else []
            # Generate new content with updated groups and existing rules
            authz_content = _generate_authz_content(self._groups, existing_rules)
            encoded_data = base64.b64encode(authz_content.encode()).decode()
            self._repo_manager._run_helper_script(["write_config_via_python", "authz", authz_file, encoded_data])
            self.load_groups()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save global authz file:\n{e}")


# ---------------------------------------------------------------------------
# Global Users Tab
# ---------------------------------------------------------------------------

class _UsersGlobalManagerTab(QWidget):
    """A tab for managing users in a global password file."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # The initial parent is the RepoManager. Store it before it gets reparented by the QTabWidget.
        self._repo_manager = parent
        self._settings = QSettings()
        self._users: list[PasswdEntry] = []
        self._setup_ui()

    def _sync_user_update(self, username: str, new_password: str | None = None, new_active_status: bool | None = None):
        """Synchronizes a user's password or status change across all repositories."""
        if not self._repo_manager._root or (new_password is None and new_active_status is None):
            return

        logger.info("Scanning for repositories to sync for user '%s'.", username)
        self._repo_manager.window().statusBar().showMessage(f"Scanning repositories for user '{username}'...")

        try:
            all_repos = svc.list_repos(self._repo_manager._root)
        except (SvnCommandError, OSError) as e:
            logger.error("Could not list repositories for synchronization: %s", e)
            QMessageBox.warning(self, "Sync Warning", f"Could not list repositories to sync user changes:\n{e}")
            return

        batch_payload = {}
        repos_to_change = set()

        # --- Scanning Phase: Find all required changes first ---
        for repo in all_repos:
            conf_dir = os.path.join(repo.path, "conf")
            
            # Check for password update
            if new_password is not None:
                local_passwd_path = os.path.join(conf_dir, "passwd")
                if os.path.exists(local_passwd_path):
                    try:
                        local_users = parse_passwd(local_passwd_path)
                        user_found = False
                        for u in local_users:
                            if u.username == username:
                                u.password = new_password
                                user_found = True
                        
                        if user_found:
                            logger.debug("Preparing password sync for '%s' in repo '%s'.", username, repo.name)
                            passwd_data = [{"username": u.username, "password": u.password, "active": u.active} for u in local_users]
                            # passwd_json_data = json.dumps(passwd_data)
                            # key = f"passwd_{repo.name.replace('-', '_')}"
                            key = f"passwd"
                            if key not in batch_payload:
                                batch_payload[key] = []
                            batch_payload[key].append({"path": local_passwd_path, "data": passwd_data})
                            repos_to_change.add(repo.name)
                    except Exception as e:
                        logger.error("Failed to prepare password sync for '%s' in repo '%s': %s", username, repo.name, e)

            # Check for access revocation
            if new_active_status is not None:
                local_authz_path = os.path.join(conf_dir, "authz")
                if os.path.exists(local_authz_path):
                    try:
                        rules, groups = parse_authz(local_authz_path), parse_groups_from_authz(local_authz_path)
                        user_has_access = False
                        for r in rules:
                            if r.user == username and r.permission:
                                r.permission = ""
                                user_has_access = True
                        
                        if user_has_access:
                            authz_content = _generate_authz_content(groups, rules)
                            # key = f"authz_{repo.name.replace('-', '_')}"
                            key = f"authz"
                            if key not in batch_payload:
                                batch_payload[key] = []
                            batch_payload[key].append({"path": local_authz_path, "data": authz_content})    
                            repos_to_change.add(repo.name)
                    except Exception as e:
                        logger.error("Failed to prepare status sync for '%s' in repo '%s': %s", username, repo.name, e)

        # --- Confirmation and Execution Phase ---
        if not batch_payload:
            self._repo_manager.window().statusBar().showMessage(f"User '{username}' not found in any repository configurations. No sync needed.", 5000)
            return

        repo_list_str = "\n".join(f"- {r}" for r in sorted(list(repos_to_change)))
        # reply = QMessageBox.question(
        #     self, "Confirm Synchronization",
        #     f"User '<code>{username}</code>' will be updated in the following repositories:\n\n{repo_list_str}\n\nThis requires administrative privileges. Proceed?",
        #     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        # )

        # if reply == QMessageBox.StandardButton.No:
        #     self._repo_manager.window().statusBar().showMessage("Synchronization cancelled by user.", 3000)
        #     return

        try:
            logger.info("Executing batch update for user '%s' across %d repositories.", username, len(repos_to_change))
            self._repo_manager.window().statusBar().showMessage(f"Applying changes for '{username}'...")
            
            encoded_batch = base64.b64encode(json.dumps(batch_payload).encode()).decode()
            self._repo_manager._run_helper_script(["write_repo_configs", encoded_batch])
            
            self._repo_manager.window().statusBar().showMessage(f"Synchronization for '{username}' complete. Updated {len(repos_to_change)} repo(s).", 5000)
        except Exception as e:
            logger.error("Batch synchronization failed for user '%s': %s", username, e, exc_info=True)
            QMessageBox.critical(self, "Synchronization Failed", f"An error occurred during synchronization:\n{e}")

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

    def showEvent(self, event):
        self.load_users()
        super().showEvent(event)

    def load_users(self):
        passwd_file = self._settings.value("Server/global_passwd_file", "")
        if not passwd_file:
            self._table.setRowCount(0)
            self._table.setEnabled(False)
            QMessageBox.warning(self, "Not Configured", "A global password file path has not been set.\nPlease configure it in File > Settings.")
            return
        
        if not os.path.exists(passwd_file):
            reply = QMessageBox.question(
                self, "Create Global Password File",
                f"The configured global password file does not exist:\n<b>{passwd_file}</b>\n\n"
                "Do you want to create it now?\n\nAdministrative privileges are required.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Use the helper to create an empty, valid passwd file
                self._save_users(is_creation=True)
            else:
                self._table.setRowCount(0)
                self._table.setEnabled(False)
                return

        self._table.setEnabled(True)
        try:
            self._users = parse_passwd(passwd_file) if os.path.exists(passwd_file) else []
            self._refresh_table()
        except (ConfigParseError, OSError) as e:
            QMessageBox.critical(self, "Error Loading Users", str(e))

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
            # Right-clicked on a user item
            idx = index.row()
            # Ensure the row is selected for the handlers to work
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
            # Right-clicked on empty area
            add_action = QAction("➕ Add User...", self)
            add_action.triggered.connect(self._on_add)
            menu.addAction(add_action)

        menu.addSeparator()
        refresh_action = QAction("🔄 Refresh", self)
        refresh_action.triggered.connect(self.load_users)
        menu.addAction(refresh_action)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_add(self):
        min_len = int(self._settings.value("Server/pw_min_length", 8))
        complexity = self._settings.value("Server/pw_complexity", False, type=bool)
        dlg = _UserDialog(min_len, complexity, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            username = dlg.username
            if any(u.username == username for u in self._users):
                QMessageBox.warning(self, "User Exists", f"User '{dlg.username}' already exists.")
                return
            self._users.append(PasswdEntry(username, dlg.password, active=True))
            self._save_users()

    def _on_edit(self):
        idx = self._table.selectionModel().selectedRows()[0].row()
        user = self._users[idx]
        min_len = int(self._settings.value("Server/pw_min_length", 8))
        complexity = self._settings.value("Server/pw_complexity", False, type=bool)
        dlg = _UserDialog(min_len, complexity, username=user.username, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_password = dlg.password
            user.password = dlg.password
            update_info = {"username": user.username, "new_password": new_password}
            self._save_users(updated_user_info=update_info)

    def _on_delete(self):
        idx = self._table.selectionModel().selectedRows()[0].row()
        user = self._users[idx]
        if QMessageBox.question(self, "Delete User", f"Delete user '{user.username}'?") == QMessageBox.StandardButton.Yes:
            username_to_delete = user.username
            self._users.pop(idx)
            update_info = {"username": username_to_delete, "new_active_status": False}
            self._save_users(updated_user_info=update_info)

    def _on_suspend(self):
        idx = self._table.selectionModel().selectedRows()[0].row()
        user = self._users[idx]
        user.active = False
        update_info = {"username": user.username, "new_active_status": False}
        self._save_users(updated_user_info=update_info)

    def _on_activate(self):
        idx = self._table.selectionModel().selectedRows()[0].row()
        user = self._users[idx]
        user.active = True
        # Activating a user does not automatically restore permissions for security reasons.
        # We only save the global file and do not sync to repos.
        self._save_users()

    def _save_users(self, is_creation: bool = False, updated_user_info: dict | None = None):
        passwd_file = self._settings.value("Server/global_passwd_file", "")
        if not passwd_file:
            QMessageBox.critical(self, "Save Failed", "Global password file is not configured in Settings.")
            return

        # If we are creating the file, the user list might be empty.
        users_to_save = self._users if not is_creation else []

        try:
            # This is a list of dicts, which is what the helper expects
            passwd_data = [{"username": u.username, "password": u.password, "active": u.active} for u in users_to_save]
            encoded_data = base64.b64encode(json.dumps(passwd_data).encode()).decode()
            
            # Use the same privileged writer as AccessEditor
            self._repo_manager._run_helper_script(["write_config_via_python", "passwd", passwd_file, encoded_data])

            if updated_user_info:
                self._sync_user_update(**updated_user_info)

            self.load_users() # Reload to reflect changes
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save password file:\n{e}")


# ---------------------------------------------------------------------------
# Delete confirmation dialog
# ---------------------------------------------------------------------------

class _FirstDeleteConfirmationDialog(QDialog):
    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Delete Repository")
        self.setModal(True)
        layout = QVBoxLayout(self)

        warn = QLabel(
            f"<b>Permanently delete repository '<code>{name}</code>'?</b><br><br>"
            "This action cannot be undone."
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        self._backup_cb = QCheckBox("Create a hot-copy backup before deleting")
        self._backup_cb.setChecked(True)
        layout.addWidget(self._backup_cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        delete_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        delete_btn.setText("Delete")
        delete_btn.setStyleSheet("QPushButton { color: white; background: #cb2431; }")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def backup_first(self) -> bool:
        return self._backup_cb.isChecked()


class _NoBackupWarningDialog(QDialog):
    def __init__(self, repo_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Warning: No Backup Selected")
        self.setModal(True)

        layout = QVBoxLayout(self)

        warn = QLabel(
            f"You are about to delete repository '<code>{repo_name}</code>' "
            "<b>WITHOUT creating a hot-copy backup.</b><br><br>"
            "This may result in <b>permanent data loss</b> if anything goes wrong.<br>"
            "Are you sure you want to proceed without a backup?"
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        continue_btn = buttons.button(QDialogButtonBox.StandardButton.Yes)
        continue_btn.setText("Continue Without Backup")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.No)
        cancel_btn.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class _FinalDeleteConfirmationDialog(QDialog):
    def __init__(self, repo_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Repository Deletion")
        self.setModal(True)
        self._repo_name = repo_name

        layout = QVBoxLayout(self)

        warn = QLabel(
            f"To confirm deletion of repository '<code>{repo_name}</code>', "
            "please type its name into the field below."
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(repo_name)
        self._name_input.textChanged.connect(self._validate)
        layout.addWidget(self._name_input)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #cb2431; font-size: 11px;")
        layout.addWidget(self._error_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Delete")
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._validate() # Initial validation

    def _validate(self) -> None:
        entered_name = self._name_input.text().strip()
        self._ok_btn.setEnabled(entered_name == self._repo_name)
        self._error_label.setText("" if entered_name == self._repo_name else "Repository name does not match. Enter the exact repository name to continue.")


# ---------------------------------------------------------------------------
# Import dump dialog
# ---------------------------------------------------------------------------

class _ImportDumpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import from Dump File")
        self.setMinimumWidth(440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        dump_row = QWidget()
        dump_layout = QHBoxLayout(dump_row)
        dump_layout.setContentsMargins(0, 0, 0, 0)
        self._dump_edit = QLineEdit()
        self._dump_edit.setPlaceholderText("Path to .svndump or .svndump.gz file")
        self._dump_edit.textChanged.connect(self._validate)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse)
        dump_layout.addWidget(self._dump_edit)
        dump_layout.addWidget(browse)
        form.addRow("Dump file:", dump_row)

        self._new_repo_cb = QCheckBox("Create new repository with this name:")
        self._new_repo_cb.setChecked(True)
        self._new_repo_cb.toggled.connect(self._on_new_toggle)
        form.addRow("", self._new_repo_cb)

        self._new_name_edit = QLineEdit()
        self._new_name_edit.setPlaceholderText("imported-repo")
        self._new_name_edit.textChanged.connect(self._validate)
        form.addRow("New name:", self._new_name_edit)

        warn = QLabel(
            "Note: dump/load does not preserve hook scripts or authz settings."
        )
        warn.setStyleSheet("color: #856404; background: #fff3cd; padding: 6px; border: 1px solid #ffc107;")
        warn.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(warn)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Import")
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Dump File", "", "Dump files (*.svndump *.svndump.gz);;All files (*)"
        )
        if path:
            self._dump_edit.setText(path)

    def _on_new_toggle(self, checked: bool) -> None:
        self._new_name_edit.setEnabled(checked)
        self._validate()

    def _validate(self) -> None:
        dump_ok = bool(self._dump_edit.text().strip())
        name_ok = bool(self._new_name_edit.text().strip()) if self._new_repo_cb.isChecked() else True
        self._ok_btn.setEnabled(dump_ok and name_ok)

    @property
    def dump_file(self) -> str:
        return self._dump_edit.text().strip()

    @property
    def create_new(self) -> bool:
        return self._new_repo_cb.isChecked()

    @property
    def new_name(self) -> str:
        return self._new_name_edit.text().strip()


# ---------------------------------------------------------------------------
# Hot copy dialog
# ---------------------------------------------------------------------------

class _HotCopyDialog(QDialog):
    def __init__(self, src_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hot Copy")
        self.setMinimumWidth(440)
        self.setModal(True)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Hot copy preserves all hook scripts and permissions.\n"
            f"Source: <b>{src_name}</b>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        dest_row = QWidget()
        dest_layout = QHBoxLayout(dest_row)
        dest_layout.setContentsMargins(0, 0, 0, 0)
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Destination path")
        self._dest_edit.textChanged.connect(self._validate)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse)
        dest_layout.addWidget(self._dest_edit)
        dest_layout.addWidget(browse)
        form.addRow("Destination:", dest_row)
        layout.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Hot Copy")
        self._ok_btn.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Destination")
        if path:
            self._dest_edit.setText(path)

    def _validate(self) -> None:
        self._ok_btn.setEnabled(bool(self._dest_edit.text().strip()))

    @property
    def dest_path(self) -> str:
        return self._dest_edit.text().strip()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class RepoManager(QWidget):
    """Repository Manager — list, create, delete, import SVN repositories.

    Signals:
        repo_selected(repo_path): emitted when user selects a repo.
    """

    repo_selected = Signal(str)
    repo_deleted = Signal(str) # Emitted when a repository is successfully deleted
    
    _SVN_USER = "svn"
    _SVN_GROUP = "svnserver"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._root: str | None = None
        self._repos: list[RepoInfo] = []
        self._worker: _Worker | None = None # This was already here
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_root(self, root: str) -> None:
        logger.debug("Setting repository root to: %s", root)
        self._root = root
        self.refresh()

    def refresh(self) -> None:
        if not self._root:
            logger.warning("Refresh called with no root set.")
            return
        self._set_buttons_enabled(False)
        self._overlay.show_progress("Loading repositories…", indeterminate=True)
        self._worker = _Worker(svc.list_repos, self._root)
        self._worker.finished.connect(self._on_list_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # --- Tab 1: Repositories ---
        repo_tab_widget = QWidget()
        repo_tab_layout = QVBoxLayout(repo_tab_widget)
        repo_tab_layout.setContentsMargins(4, 4, 4, 4)
        repo_tab_layout.setSpacing(4)

        # Toolbar
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(4)

        self._create_btn = QPushButton("➕ Create")
        self._create_btn.clicked.connect(self.create_repository)
        self._delete_btn = QPushButton("🗑 Delete")
        self._delete_btn.clicked.connect(self._on_delete)
        self._refresh_btn = QPushButton("🔄 Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        self._import_dump_btn = QPushButton("📥 Import Dump…")
        self._import_dump_btn.clicked.connect(self._on_import_dump)
        self._hotcopy_btn = QPushButton("📋 Hot Copy…")
        self._hotcopy_btn.clicked.connect(self._on_hotcopy)

        for btn in (self._create_btn, self._delete_btn, self._refresh_btn,
                    self._import_dump_btn, self._hotcopy_btn):
            tb_layout.addWidget(btn)
        tb_layout.addStretch()
        repo_tab_layout.addWidget(toolbar)

        # Repo list
        self._repo_list = QListWidget()
        self._repo_list.currentItemChanged.connect(self._on_selection_changed)
        
        self._empty_label = QLabel("Set a repository root to list repositories.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("font-size: 13px;")

        repo_tab_layout.addWidget(self._repo_list)
        repo_tab_layout.addWidget(self._empty_label)

        self._tabs.addTab(repo_tab_widget, "Repositories")

        # --- Tab 3: Global Users ---
        self._users_tab = _UsersGlobalManagerTab(self)
        self._tabs.addTab(self._users_tab, "Users")

        # --- Tab 4: Global Groups ---
        self._groups_tab = _GroupsGlobalManagerTab(self)
        self._tabs.addTab(self._groups_tab, "Groups")
        
        self._delete_btn.setEnabled(False)
        self._hotcopy_btn.setEnabled(False)

        self._overlay = ProgressOverlay(self)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._create_btn.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)
        self._import_dump_btn.setEnabled(enabled)

    def _run_helper_script(self, args: list[str]) -> None:
        """Runs the privileged helper script via pkexec and shows output."""
        # In a real package, it would be "/usr/bin/svn-server-admin-helper"
        helper_path = "/usr/bin/svn-server-admin-helper" # This was already here
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
    # ------------------------------------------------------------------
    # Slots — list loading
    # ------------------------------------------------------------------

    def _on_list_done(self, repos: list[svc.RepoInfo]) -> None:
        logger.debug("Repository list loaded. Found %d repos.", len(repos))
        self._overlay.hide_progress()
        self._set_buttons_enabled(True)
        self._repos = repos
        self._repo_list.clear() # This was already here

        for repo in repos:
            size_str = _fmt_size(repo.size_bytes)
            item = QListWidgetItem(f"{repo.name}  (r{repo.head_revision}, {size_str})")
            item.setData(Qt.ItemDataRole.UserRole, repo.path)
            self._repo_list.addItem(item)
        
        if not repos:
            self._repo_list.setVisible(False)
            self._empty_label.setText("No repositories found in this root.")
            self._empty_label.setVisible(True)
        else:
            self._repo_list.setVisible(True)
            self._empty_label.setVisible(False)

    def _on_selection_changed(self, current: QListWidgetItem | None, _prev) -> None:
        has = current is not None
        self._delete_btn.setEnabled(has)
        self._hotcopy_btn.setEnabled(has)
        if not has:
            return

        path = current.data(Qt.ItemDataRole.UserRole)
        # Find cached info from the list loaded by refresh()
        info = next((r for r in self._repos if r.path == path), None)
        if info:
            self.repo_selected.emit(info.path)

    def _on_error(self, msg: str) -> None:
        logger.error("An error occurred in RepoManager worker: %s", msg)
        self._overlay.hide_progress()
        self._set_buttons_enabled(True)
        QMessageBox.critical(self, "Error", msg)

    # ------------------------------------------------------------------
    # Slots — create
    # ------------------------------------------------------------------

    def create_repository(self) -> None:
        """Public slot to initiate repository creation."""
        if not self._root:
            QMessageBox.information(self, "No Root", "Set a repository root first.")
            return

        dlg = _CreateDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        repo_path = os.path.join(self._root, dlg.repo_name)

        # Pre-flight check to avoid confusing errors from the helper script
        if os.path.exists(repo_path):
            QMessageBox.warning(self, "Creation Failed", f"A file or directory already exists at:\n{repo_path}")
            return

        self._overlay.show_progress(f"Creating '{dlg.repo_name}'…", indeterminate=True)
        self._set_buttons_enabled(False)

        # The creation logic is moved into the privileged helper script to avoid
        # permission issues when the GUI user doesn't have write access to the repo root.
        args = [
            "create_repo",
            repo_path,
            dlg.fs_type,
            "true" if dlg.standard_layout else "false",
            self._SVN_USER,
            self._SVN_GROUP,
        ]
        self._run_helper_script(args)

        self._overlay.hide_progress()
        self._set_buttons_enabled(True)

        if os.path.isdir(repo_path):
            self.window().statusBar().showMessage(f"Repository '{dlg.repo_name}' created successfully.", 5000)

            # After creation, optionally set initial user permissions
            if dlg.configure_access:
                self._configure_initial_rights(repo_path, dlg.repo_name)
            else:
                # If not configuring rights, at least write a default svnserve.conf
                self._write_default_svnserve_conf(repo_path)

            # Now refresh the list to show the new repo
            self.refresh()

    def _configure_initial_rights(self, repo_path: str, repo_name: str) -> None:
        """Write default svnserve.conf and open a dialog to set initial user rights."""
        self._write_default_svnserve_conf(repo_path)

        global_passwd_file = self._settings.value("Server/global_passwd_file", "")
        if not global_passwd_file or not os.path.exists(global_passwd_file):
            # Silently skip if no global password file is configured
            return

        try:
            users = [u.username for u in parse_passwd(global_passwd_file) if u.active]
            if not users:
                return

            rights_dlg = _InitialRightsDialog(users, self)
            if rights_dlg.exec() == QDialog.DialogCode.Accepted:
                selected_users = rights_dlg.selected_users
                if not selected_users:
                    return

                # Build authz content
                lines = [f"[{repo_name}:/]"]
                for user in selected_users:
                    lines.append(f"{user} = rw")
                lines.append("* = ") # Deny others
                authz_content = "\n".join(lines)
                authz_path = os.path.join(repo_path, "conf", "authz")

                # Use helper to write the file
                encoded_content = base64.b64encode(authz_content.encode()).decode()
                self._run_helper_script(["write_config_via_python", "authz", authz_path, encoded_content])
                self.window().statusBar().showMessage(f"Initial permissions set for {len(selected_users)} user(s).", 3000)

        except (OSError, SvnCommandError, ConfigParseError) as e:
            QMessageBox.warning(self, "Could Not Set Permissions", f"Failed to read global user list or write authz file:\n{e}")

    def _write_default_svnserve_conf(self, repo_path: str) -> None:
        """Writes a default svnserve.conf pointing to the global password file."""
        global_passwd_file = self._settings.value("Server/global_passwd_file", "")
        if not global_passwd_file:
            # add logging or warning here if needed
            logger.warning("Global password file not configured.")
            return # Can't do it if not configured

        # Note: svnserve.conf paths are relative to the repo's conf/ dir,
        # unless they are absolute paths. We will use an absolute path for robustness.
        config_data = {
            "anon-access": "none",
            "auth-access": "write",
            "password-db": global_passwd_file,
            "authz-db": "authz", # This one is relative to conf/
            "realm": os.path.basename(repo_path)
        }
        config_json_data = json.dumps(config_data)
        svnserve_conf_path = os.path.join(repo_path, "conf", "svnserve.conf")
        encoded_data = base64.b64encode(config_json_data.encode()).decode()
        self._run_helper_script(["write_config_via_python", "svnserve_conf", svnserve_conf_path, encoded_data])

    def _on_fix_permissions(self) -> None:
        item = self._repo_list.currentItem()
        if not item: return
        path = item.data(Qt.ItemDataRole.UserRole)
        name = os.path.basename(path)
        reply = QMessageBox.question(
            self,
            "Fix Repository Permissions",
            f"This will reset the ownership of the repository '{name}' to the '{self._SVN_USER}:{self._SVN_GROUP}' user and group, "
            "and apply recommended directory permissions. This is the correct fix for 'No repository found' errors on an existing repository.\n\n"
            "Administrative privileges are required.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_helper_script(["set_ownership", path, self._SVN_USER, self._SVN_GROUP])
            # No need to call refresh() as permissions aren't visible in the UI,
            # but we can show a status message.
            self.window().statusBar().showMessage(f"Permissions fixed for '{name}'.", 5000)


    # ------------------------------------------------------------------
    # Slots — delete
    # ------------------------------------------------------------------

    def _on_delete(self) -> None:
        item = self._repo_list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        name = os.path.basename(path)
        logger.info("Initiating deletion process for repository: %s", name)

        # 1. First Deletion Confirmation (with backup option)
        first_dlg = _FirstDeleteConfirmationDialog(name, self)
        if first_dlg.exec() != QDialog.DialogCode.Accepted:
            logger.debug("Deletion cancelled at first confirmation for %s.", name)
            return

        backup_first = first_dlg.backup_first

        # 2. Hot Backup Validation (if backup not selected)
        if not backup_first:
            logger.warning("User chose to delete repository %s WITHOUT backup.", name)
            no_backup_dlg = _NoBackupWarningDialog(name, self)
            if no_backup_dlg.exec() != QDialog.DialogCode.Accepted:
                logger.debug("Deletion cancelled at no-backup warning for %s.", name)
                return

        # 3. Second and Final Delete Confirmation (type name)
        final_confirm_dlg = _FinalDeleteConfirmationDialog(name, self)
        if final_confirm_dlg.exec() != QDialog.DialogCode.Accepted:
            logger.debug("Deletion cancelled at final name confirmation for %s.", name)
            return

        # 5. Repository Deletion
        logger.info("Proceeding with deletion of repository: %s (backup_first=%s)", name, backup_first)
        self._set_buttons_enabled(False) # Disable buttons to prevent duplicate requests

        try:
            args = ["delete_repo", path, "true" if backup_first else "false"]
            # This call is synchronous and shows a modal dialog with progress/errors from the helper.
            self._run_helper_script(args)

            if not os.path.exists(path):
                self._on_delete_done(name, path)
            else:
                self._on_delete_error(name, "Deletion script ran, but the repository directory still exists. Check logs for details.")
        except Exception as e:
            self._on_delete_error(name, str(e))

    def _on_delete_done(self, name: str, path: str) -> None:
        logger.info("Repository '%s' deleted successfully.", name)
        self._set_buttons_enabled(True)
        QMessageBox.information(self, "Deleted", f"Repository '<code>{name}</code>' was deleted successfully.")
        self.refresh() # Refresh the list to remove the deleted repo
        self.repo_deleted.emit(path) # Notify parent that a repo was deleted

    def _on_delete_error(self, name: str, msg: str) -> None:
        logger.error("Failed to delete repository '%s': %s", name, msg)
        self._set_buttons_enabled(True)
        QMessageBox.critical(self, "Deletion Failed", f"Unable to delete repository '<code>{name}</code>'.\nError: {msg}")

    # ------------------------------------------------------------------
    # Slots — import dump
    # ------------------------------------------------------------------

    def _on_import_dump(self) -> None:
        if not self._root:
            return
        dlg = _ImportDumpDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        dump_file = dlg.dump_file
        if dlg.create_new:
            repo_path = os.path.join(self._root, dlg.new_name)
            self._overlay.show_progress("Creating repository…", indeterminate=True)
            try:
                # Using the helper script for creation
                args = ["create_repo", repo_path, "fsfs", "false", self._SVN_USER, self._SVN_GROUP]
                self._run_helper_script(args)
                if os.path.isdir(repo_path):
                    self._do_load(repo_path, dump_file)
                else:
                    self._on_error("Repository creation failed during import.")
            except Exception as e:
                self._on_error(str(e))
        else:
            item = self._repo_list.currentItem()
            if not item:
                QMessageBox.warning(self, "No Repository", "Select a repository to load into.")
                return
            self._do_load(item.data(Qt.ItemDataRole.UserRole), dump_file)

    def _do_load(self, repo_path: str, dump_file: str) -> None:
        # Repositories are owned by svn:svnserver (see create_repo/set_ownership),
        # so `svnadmin load` running as the desktop user can't create the
        # temporary files it needs inside db/ -- it fails with a permission
        # error. Route through the privileged helper (same as repo creation)
        # so the load runs as root, then have it restore svn:svnserver
        # ownership afterward.
        if not os.path.isfile(dump_file):
            self._on_error(f"Dump file not found: {dump_file}")
            return
        self._run_helper_script(
            ["load_dump", repo_path, dump_file, self._SVN_USER, self._SVN_GROUP]
        )
        self.refresh()

    # ------------------------------------------------------------------
    # Slots — hot copy
    # ------------------------------------------------------------------

    def _on_hotcopy(self) -> None:
        item = self._repo_list.currentItem()
        if not item:
            return
        src_path = item.data(Qt.ItemDataRole.UserRole)
        dlg = _HotCopyDialog(os.path.basename(src_path), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # svnadmin hotcopy refuses to write into an existing non-empty directory, so a
        # raw user-picked folder (likely already containing other files/backups) would
        # fail immediately, and reusing the same folder for a later hotcopy of the same
        # or another repo would also fail. Nest each hotcopy under a unique, timestamped
        # subfolder instead — see also backup_panel.py's _HotCopyTab for the same fix.
        repo_name = os.path.basename(src_path.rstrip(os.sep))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(dlg.dest_path, f"{repo_name}_{stamp}")
        self._overlay.show_progress("Creating hot copy…", indeterminate=True)
        self._worker = _Worker(svc.hotcopy, src_path, dest)
        self._worker.finished.connect(lambda _: (
            self._overlay.hide_progress(),
            QMessageBox.information(self, "Hot Copy Complete", f"Copied to:\n{dest}"),
        ))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
