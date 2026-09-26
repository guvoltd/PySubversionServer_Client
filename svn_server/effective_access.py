"""Effective Access Viewer — evaluate authz rules for a user + path.

T-403: all sub-tasks (a-f)
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from svn_shared.config_parser import AuthzRule, parse_authz

_ACCESS_NONE  = ""
_ACCESS_READ  = "r"
_ACCESS_WRITE = "rw"

_LEVEL_ORDER = {_ACCESS_NONE: 0, _ACCESS_READ: 1, _ACCESS_WRITE: 2}

_BADGE_STYLES = {
    _ACCESS_NONE:  "background:#cb2431; color:white; padding:4px 10px; border-radius:4px; font-weight:bold;",
    _ACCESS_READ:  "background:#856404; color:white; padding:4px 10px; border-radius:4px; font-weight:bold;",
    _ACCESS_WRITE: "background:#22863a; color:white; padding:4px 10px; border-radius:4px; font-weight:bold;",
}
_BADGE_TEXT = {
    _ACCESS_NONE:  "No Access",
    _ACCESS_READ:  "Read Only",
    _ACCESS_WRITE: "Read / Write",
}


# ---------------------------------------------------------------------------
# Authz evaluation logic
# ---------------------------------------------------------------------------

def _parse_groups(authz_path: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    in_groups = False
    try:
        with open(authz_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped == "[groups]":
                    in_groups = True
                    continue
                if stripped.startswith("[") and in_groups:
                    in_groups = False
                if in_groups and "=" in stripped and not stripped.startswith("#"):
                    name, _, members = stripped.partition("=")
                    groups[name.strip()] = [m.strip() for m in members.split(",") if m.strip()]
    except OSError:
        pass
    return groups


def _expand_groups(username: str, groups: dict[str, list[str]], _seen: set[str] | None = None) -> set[str]:
    """Return set of all group names the user belongs to (transitive)."""
    if _seen is None:
        _seen = set()
    memberships: set[str] = set()
    for grp_name, members in groups.items():
        if grp_name in _seen:
            continue
        for member in members:
            if member == username:
                memberships.add(grp_name)
                _seen.add(grp_name)
                # Recurse: groups can be members of other groups
                memberships |= _expand_groups(f"@{grp_name}", groups, _seen)
            elif member == f"@{grp_name}":
                pass  # self-reference guard
            elif member.startswith("@") and member[1:] == grp_name:
                pass
    return memberships


def evaluate_access(
    authz_path: str,
    username: str,
    repo_path_arg: str,  # e.g. "/trunk/src" or "myrepo:/trunk"
) -> tuple[str, list[str]]:
    """Evaluate the effective access level for a user at a path.

    Returns:
        (access_level, contributing_rules) where access_level is "", "r", or "rw"
        and contributing_rules is a list of human-readable rule descriptions.
    """
    if not os.path.exists(authz_path):
        return _ACCESS_NONE, ["authz file not found"]

    rules = parse_authz(authz_path)
    groups = _parse_groups(authz_path)
    user_groups = _expand_groups(username, groups)

    # Normalise repo_path_arg: strip leading repo: prefix if present
    if ":" in repo_path_arg:
        repo_name, _, path = repo_path_arg.partition(":")
    else:
        repo_name = ""
        path = repo_path_arg

    if not path.startswith("/"):
        path = "/" + path

    # Walk path hierarchy from root to target
    path_segments = ["/"]
    parts = [p for p in path.split("/") if p]
    for i in range(len(parts)):
        path_segments.append("/" + "/".join(parts[: i + 1]))

    contributing: list[str] = []
    effective = _ACCESS_NONE

    for segment in path_segments:
        # Candidate section names (global or repo-specific)
        candidate_sections: list[str] = []
        if repo_name:
            candidate_sections.append(f"[{repo_name}:{segment}]")
        candidate_sections.append(f"[{segment}]")

        for section in candidate_sections:
            section_rules = [r for r in rules if r.section == section]
            if not section_rules:
                continue

            segment_access = _ACCESS_NONE
            for rule in section_rules:
                applies = False
                if rule.user == "*":
                    applies = True
                elif rule.user == username:
                    applies = True
                elif rule.user.startswith("@") and rule.user[1:] in user_groups:
                    applies = True

                if applies:
                    if _LEVEL_ORDER.get(rule.permission, 0) > _LEVEL_ORDER.get(segment_access, 0):
                        segment_access = rule.permission
                        contributing.append(
                            f"{section} : {rule.user} = {rule.permission or '(none)'}"
                        )

            # Child paths override parent — update effective
            if segment_access != _ACCESS_NONE or section_rules:
                effective = segment_access

    return effective, contributing


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class EffectiveAccess(QWidget):
    """Effective Access Viewer — check what a user can do at a given path."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo_path: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_repo(self, repo_path: str) -> None:
        self._repo_path = repo_path
        self._repo_label.setText(f"Repository: {os.path.basename(repo_path)}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Repo label
        self._repo_label = QLabel("No repository selected.")
        self._repo_label.setStyleSheet("font-style: italic;")
        layout.addWidget(self._repo_label)

        # Email bypass note
        bypass_note = QLabel(
            "ℹ  Email notifications (post-commit hooks) bypass authz rules — "
            "any user can trigger notifications regardless of access level."
        )
        bypass_note.setWordWrap(True)
        bypass_note.setStyleSheet(
            "background: #dbeafe; color: #1e3a8a; padding: 6px; border: 1px solid #93c5fd;"
        )
        layout.addWidget(bypass_note)

        # Inputs
        form_group = QGroupBox("Check Access")
        form = QFormLayout(form_group)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("username")
        form.addRow("Username:", self._user_edit)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("/trunk  or  myrepo:/trunk/src")
        form.addRow("Path:", self._path_edit)

        check_btn = QPushButton("Check Access")
        check_btn.clicked.connect(self._on_check)
        form.addRow("", check_btn)
        layout.addWidget(form_group)

        # Result
        result_group = QGroupBox("Result")
        result_layout = QVBoxLayout(result_group)

        self._badge = QLabel("—")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet("font-size: 16px; padding: 8px;")
        result_layout.addWidget(self._badge)

        result_layout.addWidget(QLabel("Contributing rules:"))
        self._rules_list = QListWidget()
        self._rules_list.setMaximumHeight(160)
        result_layout.addWidget(self._rules_list)

        layout.addWidget(result_group)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_check(self) -> None:
        if not self._repo_path:
            return
        username = self._user_edit.text().strip()
        path = self._path_edit.text().strip()
        if not username or not path:
            return

        authz_path = os.path.join(self._repo_path, "conf", "authz")
        access, contributing = evaluate_access(authz_path, username, path)

        self._badge.setText(_BADGE_TEXT[access])
        self._badge.setStyleSheet(_BADGE_STYLES[access])

        self._rules_list.clear()
        if contributing:
            for rule in contributing:
                self._rules_list.addItem(QListWidgetItem(rule))
        else:
            self._rules_list.addItem(QListWidgetItem("No matching rules found — default: No Access"))
