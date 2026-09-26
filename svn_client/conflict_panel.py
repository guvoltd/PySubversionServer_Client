"""Conflict resolution panel — mine/theirs/base viewer and resolution actions.

T-306: all sub-tasks (a-d)
"""

from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.svn_client_svc import StatusEntry
from svn_shared.exceptions import SvnCommandError
from svn_shared.widgets.syntax_highlighter import DiffHighlighter

from svn_client.diff_viewer import _CodeEditor

# Conflict type descriptions
_CONFLICT_GUIDANCE: dict[str, str] = {
    "conflicted": (
        "Text conflict: both you and someone else changed the same lines in this file.\n"
        "Review the markers below, resolve by choosing a version or editing manually,\n"
        "then click Mark Resolved."
    ),
    "obstructed": (
        "Tree conflict: an unversioned file or directory exists where SVN expects a versioned item.\n"
        "Remove or rename the obstruction, then click Mark Resolved."
    ),
    "missing": (
        "Tree conflict: SVN expects this file to exist but it is missing from disk.\n"
        "Use 'Use Theirs' to restore it from the repository, or delete it from version control."
    ),
}


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return f"(cannot read {path})"


def _conflict_versions(wc_path: str, rel_path: str) -> tuple[str, str, str]:
    """Return (mine, theirs, base) content for a conflicted file."""
    abs_path = os.path.join(wc_path, rel_path) if not os.path.isabs(rel_path) else rel_path
    base = abs_path + ".merge-left.r0"    # SVN leaves .merge-left (BASE) and .merge-right (THEIRS)
    theirs = abs_path + ".merge-right.r0"
    # Try standard conflict file suffixes; SVN version affects names
    if not os.path.exists(base):
        # Fallback: look for any *.r<n> files
        d = os.path.dirname(abs_path)
        name = os.path.basename(abs_path)
        candidates = sorted([
            f for f in os.listdir(d)
            if f.startswith(name + ".r") or f.startswith(name + ".mine")
        ]) if os.path.isdir(d) else []
        mine_files = [c for c in candidates if ".mine" in c]
        base_files = [c for c in candidates if ".r" in c and ".mine" not in c]
        base = os.path.join(d, base_files[0]) if base_files else abs_path
        theirs = os.path.join(d, base_files[-1]) if len(base_files) > 1 else base
        mine_f = os.path.join(d, mine_files[0]) if mine_files else abs_path

        return _read_file(mine_f), _read_file(theirs), _read_file(base)

    return _read_file(abs_path), _read_file(theirs), _read_file(base)


# ---------------------------------------------------------------------------
# Single-file panel with three side-by-side panes
# ---------------------------------------------------------------------------

class _ThreeWayView(QWidget):
    """Shows Mine / Theirs / Base in three editor panes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Column headers
        headers = QWidget()
        h_layout = QHBoxLayout(headers)
        h_layout.setContentsMargins(0, 0, 0, 0)
        for title in ("Mine (working)", "Theirs (repository)", "Base (common ancestor)"):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "font-weight: bold; background: #f0f0f0; color: #333; "
                "padding: 3px; border: 1px solid #ddd;"
            )
            h_layout.addWidget(lbl)
        layout.addWidget(headers)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._mine_editor   = _CodeEditor()
        self._theirs_editor = _CodeEditor()
        self._base_editor   = _CodeEditor()

        # Sync scroll across all three
        for src in (self._mine_editor, self._theirs_editor, self._base_editor):
            for dst in (self._mine_editor, self._theirs_editor, self._base_editor):
                if src is not dst:
                    src.verticalScrollBar().valueChanged.connect(
                        dst.verticalScrollBar().setValue
                    )

        for editor in (self._mine_editor, self._theirs_editor, self._base_editor):
            splitter.addWidget(editor)

        layout.addWidget(splitter)

    def show_versions(self, mine: str, theirs: str, base: str) -> None:
        self._mine_editor.setPlainText(mine)
        self._theirs_editor.setPlainText(theirs)
        self._base_editor.setPlainText(base)

    def clear(self) -> None:
        for editor in (self._mine_editor, self._theirs_editor, self._base_editor):
            editor.clear()


# ---------------------------------------------------------------------------
# Conflict panel
# ---------------------------------------------------------------------------

class ConflictPanel(QWidget):
    """Conflict resolution panel.

    Shows conflicted files on the left with Mine/Theirs/Base panes on the right.

    Signals:
        resolved(wc_path, rel_path): emitted after a file is marked resolved.
    """

    resolved = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wc_path: str | None = None
        self._current_path: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, wc_path: str, entries: list[StatusEntry]) -> None:
        """Populate the panel with conflicted entries."""
        self._wc_path = wc_path
        self._file_list.clear()
        conflicts = [e for e in entries if e.status in {"conflicted", "obstructed", "missing"}]
        for entry in conflicts:
            item = QListWidgetItem(
                f"[{entry.status[0].upper()}]  {os.path.basename(entry.path)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            item.setData(Qt.ItemDataRole.UserRole + 1, entry.status)
            item.setToolTip(entry.path)
            self._file_list.addItem(item)

        if not conflicts:
            self._guidance_label.setText("No conflicts detected in this working copy.")
            self._action_bar.setEnabled(False)
            self._three_way.clear()
        else:
            self._file_list.setCurrentRow(0)
            self._action_bar.setEnabled(True)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Guidance banner
        self._guidance_label = QLabel("Select a conflicted file to resolve it.")
        self._guidance_label.setWordWrap(True)
        self._guidance_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._guidance_label.setStyleSheet(
            "padding: 8px; background: #fff8e1; border-bottom: 1px solid #f0c000; color: #444;"
        )
        layout.addWidget(self._guidance_label)

        # Main splitter: file list (left) | three-way view (right)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        self._file_list = QListWidget()
        self._file_list.setMaximumWidth(240)
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        main_splitter.addWidget(self._file_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self._three_way = _ThreeWayView()
        right_layout.addWidget(self._three_way)

        # Action buttons
        self._action_bar = QWidget()
        action_layout = QHBoxLayout(self._action_bar)
        action_layout.setContentsMargins(4, 4, 4, 4)

        use_mine_btn = QPushButton("Use Mine")
        use_mine_btn.setToolTip("Accept your local version of the file")
        use_mine_btn.clicked.connect(self._use_mine)

        use_theirs_btn = QPushButton("Use Theirs")
        use_theirs_btn.setToolTip("Accept the repository version of the file")
        use_theirs_btn.clicked.connect(self._use_theirs)

        edit_btn = QPushButton("Edit Manually")
        edit_btn.setToolTip("Open the conflicted file in $EDITOR or xdg-open")
        edit_btn.clicked.connect(self._edit_manually)

        resolve_btn = QPushButton("Mark Resolved")
        resolve_btn.setToolTip("Tell SVN the conflict has been resolved (after editing)")
        resolve_btn.setStyleSheet("QPushButton { color: white; background: #22863a; } "
                                  "QPushButton:hover { background: #1a6b2e; }")
        resolve_btn.clicked.connect(self._mark_resolved)

        action_layout.addWidget(use_mine_btn)
        action_layout.addWidget(use_theirs_btn)
        action_layout.addWidget(edit_btn)
        action_layout.addStretch()
        action_layout.addWidget(resolve_btn)
        right_layout.addWidget(self._action_bar)

        main_splitter.addWidget(right)
        main_splitter.setSizes([220, 680])
        layout.addWidget(main_splitter)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_file_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if not current or not self._wc_path:
            self._three_way.clear()
            return
        rel_path = current.data(Qt.ItemDataRole.UserRole)
        status = current.data(Qt.ItemDataRole.UserRole + 1)
        self._current_path = rel_path
        guidance = _CONFLICT_GUIDANCE.get(status, "Review the conflict and resolve it manually.")
        self._guidance_label.setText(guidance)
        try:
            mine, theirs, base = _conflict_versions(self._wc_path, rel_path)
            self._three_way.show_versions(mine, theirs, base)
        except Exception as exc:
            self._guidance_label.setText(f"Cannot read conflict files: {exc}")
            self._three_way.clear()

    def _use_mine(self) -> None:
        self._resolve_with("mine-full")

    def _use_theirs(self) -> None:
        self._resolve_with("theirs-full")

    def _resolve_with(self, accept: str) -> None:
        if not self._wc_path or not self._current_path:
            return
        try:
            from svn_shared.svn_command import run_sync
            run_sync(
                ["svn", "resolve", f"--accept={accept}", self._current_path],
                cwd=self._wc_path,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Resolve Failed", str(exc))
            return
        self._remove_current_item()
        self.resolved.emit(self._wc_path, self._current_path)

    def _edit_manually(self) -> None:
        if not self._wc_path or not self._current_path:
            return
        abs_path = (
            os.path.join(self._wc_path, self._current_path)
            if not os.path.isabs(self._current_path)
            else self._current_path
        )
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        if editor:
            subprocess.Popen([editor, abs_path])
        else:
            subprocess.Popen(["xdg-open", abs_path])

    def _mark_resolved(self) -> None:
        if not self._wc_path or not self._current_path:
            return
        try:
            svc.resolve(self._wc_path, self._current_path)
        except SvnCommandError as exc:
            QMessageBox.warning(self, "Mark Resolved Failed", str(exc))
            return
        self._remove_current_item()
        self.resolved.emit(self._wc_path, self._current_path)

    def _remove_current_item(self) -> None:
        row = self._file_list.currentRow()
        if row >= 0:
            self._file_list.takeItem(row)
        if self._file_list.count() == 0:
            self._guidance_label.setText("All conflicts resolved.")
            self._action_bar.setEnabled(False)
            self._three_way.clear()
