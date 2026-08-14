"""Status tree widget — working copy file status with icons and context menu.

T-300: all sub-tasks (a-e)
"""

from __future__ import annotations

import os

from PySide6.QtCore import QModelIndex, Qt, QThread, Signal
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QMenu,
    QMessageBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.exceptions import SvnCommandError

# status → (badge letter, badge colour, readable label)
_STATUS_META: dict[str, tuple[str, str, str]] = {
    "modified":    ("M", "#c8800a", "Modified"),
    "added":       ("A", "#22863a", "Added"),
    "deleted":     ("D", "#cb2431", "Deleted"),
    "conflicted":  ("C", "#e36209", "Conflicted"),
    "unversioned": ("?", "#6a737d", "Unversioned"),
    "missing":     ("!", "#cb2431", "Missing"),
    "external":    ("X", "#0366d6", "External"),
    "ignored":     ("I", "#bbb",    "Ignored"),
    "obstructed":  ("~", "#e36209", "Obstructed"),
    "replaced":    ("R", "#c8800a", "Replaced"),
    "normal":      (" ", "#ffffff", "Normal"),
}

# statuses that are pre-checked for commit
_AUTO_CHECK = {"modified", "added", "deleted", "replaced"}


def _make_badge(letter: str, color: str, size: int = 18) -> QPixmap:
    """Return a small rounded coloured badge QPixmap with a white letter."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 4, 4)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(11)
    painter.setFont(font)
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, letter)
    painter.end()
    return px


# Pre-render all badges once
_BADGE_CACHE: dict[str, QPixmap] = {}


def _badge(status: str) -> QPixmap:
    if status not in _BADGE_CACHE:
        letter, color, _ = _STATUS_META.get(status, ("?", "#6a737d", ""))
        _BADGE_CACHE[status] = _make_badge(letter, color)
    return _BADGE_CACHE[status]


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _StatusWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, wc_path: str) -> None:
        super().__init__()
        self._wc_path = wc_path

    def run(self) -> None:
        try:
            self.finished.emit(svc.status(self._wc_path))
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Column indices
# ---------------------------------------------------------------------------

_COL_PATH   = 0  # checkbox + icon + relative path
_COL_STATUS = 1  # status label
_COL_REV    = 2  # base revision


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class StatusTree(QWidget):
    """Working-copy status tree.

    Signals:
        diff_requested(wc_path, rel_path)  – user double-clicked or chose Diff
        log_requested(wc_path, rel_path)   – user chose Show Log from context menu
        status_loaded(entries)             – refresh completed
    """

    diff_requested = Signal(str, str)
    log_requested  = Signal(str, str)
    status_loaded  = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wc_path: str | None = None
        self._worker: _StatusWorker | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_wc_path(self, path: str) -> None:
        """Set working copy root and trigger a refresh."""
        self._wc_path = path
        self.refresh()

    def refresh(self) -> None:
        """Reload status from SVN (runs in background thread)."""
        if not self._wc_path:
            return
        if self._worker and self._worker.isRunning():
            return
        self._info_label.setText("Refreshing…")
        self._worker = _StatusWorker(self._wc_path)
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def checked_paths(self) -> list[str]:
        """Return relative paths of items checked for commit."""
        paths: list[str] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row, _COL_PATH)
            if item and item.checkState() == Qt.CheckState.Checked:
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return paths

    def check_all(self, checked: bool = True) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self._model.rowCount()):
            item = self._model.item(row, _COL_PATH)
            if item:
                item.setCheckState(state)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._info_label = QLabel("Open a working copy to see changes.")
        self._info_label.setStyleSheet("padding: 3px 6px; color: #666; font-size: 12px;")
        layout.addWidget(self._info_label)

        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Path", "Status", "Rev"])

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.doubleClicked.connect(self._on_double_click)

        self._tree.setColumnWidth(_COL_STATUS, 100)
        self._tree.setColumnWidth(_COL_REV, 55)

        layout.addWidget(self._tree)

    # ------------------------------------------------------------------
    # Slots — data
    # ------------------------------------------------------------------

    def _on_loaded(self, entries: list) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for entry in entries:
            letter, color, label = _STATUS_META.get(entry.status, ("?", "#6a737d", entry.status))

            # Column 0 — path with badge icon and checkbox
            display = os.path.relpath(entry.path, self._wc_path or "") if self._wc_path else entry.path
            path_item = QStandardItem(display)
            path_item.setData(entry.path, Qt.ItemDataRole.UserRole)
            path_item.setIcon(_badge(entry.status))  # type: ignore[arg-type]
            path_item.setToolTip(entry.path)
            path_item.setCheckable(True)
            path_item.setCheckState(
                Qt.CheckState.Checked if entry.status in _AUTO_CHECK else Qt.CheckState.Unchecked
            )

            # Column 1 — status label
            status_item = QStandardItem(label)
            status_item.setForeground(QColor(color))

            # Column 2 — revision
            rev_item = QStandardItem(str(entry.revision) if entry.revision is not None else "")

            self._model.appendRow([path_item, status_item, rev_item])

        count = self._model.rowCount()
        self._info_label.setText(
            f"{count} changed file(s)" if count else "Working copy is clean."
        )
        self._tree.resizeColumnToContents(_COL_PATH)
        self.status_loaded.emit(entries)

    def _on_error(self, msg: str) -> None:
        self._info_label.setText(f"Error: {msg}")

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        index = self._tree.indexAt(pos)
        if not index.isValid():
            return
        path_item = self._model.item(index.row(), _COL_PATH)
        if not path_item:
            return
        rel_path = path_item.data(Qt.ItemDataRole.UserRole)
        wc = self._wc_path or ""

        menu = QMenu(self)
        menu.addAction("Show Diff",
                       lambda: self.diff_requested.emit(wc, rel_path))
        menu.addAction("Show Log",
                       lambda: self.log_requested.emit(wc, rel_path))
        menu.addSeparator()
        menu.addAction("Add to Version Control",
                       lambda: self._do_add([rel_path]))
        menu.addAction("Remove from Version Control",
                       lambda: self._do_remove([rel_path]))
        menu.addAction("Revert…",
                       lambda: self._do_revert([rel_path]))
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_double_click(self, index: QModelIndex) -> None:
        path_item = self._model.item(index.row(), _COL_PATH)
        if path_item and self._wc_path:
            self.diff_requested.emit(self._wc_path, path_item.data(Qt.ItemDataRole.UserRole))

    # ------------------------------------------------------------------
    # SVN operations (sync — acceptable for quick operations)
    # ------------------------------------------------------------------

    def _do_add(self, paths: list[str]) -> None:
        if not self._wc_path:
            return
        try:
            svc.add(paths, cwd=self._wc_path)
        except SvnCommandError as exc:
            QMessageBox.warning(self, "Add Failed", str(exc))
        else:
            self.refresh()

    def _do_remove(self, paths: list[str]) -> None:
        if not self._wc_path:
            return
        try:
            svc.remove(paths, cwd=self._wc_path)
        except SvnCommandError as exc:
            QMessageBox.warning(self, "Remove Failed", str(exc))
        else:
            self.refresh()

    def _do_revert(self, paths: list[str]) -> None:
        if not self._wc_path:
            return
        reply = QMessageBox.question(
            self, "Revert",
            f"Revert {len(paths)} file(s)? Local changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            svc.revert(paths, cwd=self._wc_path)
        except SvnCommandError as exc:
            QMessageBox.warning(self, "Revert Failed", str(exc))
        else:
            self.refresh()
