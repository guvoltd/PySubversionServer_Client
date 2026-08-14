"""Log viewer widget — revision log table, detail panel, search and pagination.

T-302: all sub-tasks (a-e)
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSettings,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.svn_client_svc import LogEntry
from svn_shared.exceptions import SvnCommandError
from svn_shared.widgets.search_bar import SearchBar


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _LogWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, wc_path: str, limit: int, start_rev: int | None = None) -> None:
        super().__init__()
        self._wc_path = wc_path
        self._limit = limit
        self._start_rev = start_rev

    def run(self) -> None:
        try:
            rev_range = f"1:{self._start_rev - 1}" if self._start_rev and self._start_rev > 1 else None
            entries = svc.log(self._wc_path, limit=self._limit, revision_range=rev_range)
            self.finished.emit(entries)
        except SvnCommandError as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------

_HEADERS = ["Rev", "Author", "Date", "Message"]


class _LogModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[LogEntry] = []
        self._filtered: list[LogEntry] = []
        self._filter = ""

    # QAbstractTableModel interface
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._filtered)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._filtered):
            return None
        entry = self._filtered[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(entry.revision)
            if col == 1:
                return entry.author
            if col == 2:
                return entry.date.strftime("%Y-%m-%d %H:%M") if entry.date != datetime.min else ""
            if col == 3:
                # First line of message, truncated
                first = entry.message.strip().split("\n")[0]
                return first[:120] + ("…" if len(first) > 120 else "")

        if role == Qt.ItemDataRole.ToolTipRole and col == 3:
            return entry.message.strip()

        if role == Qt.ItemDataRole.UserRole:
            return entry  # full LogEntry for detail panel

        return None

    # Data management
    def set_entries(self, entries: list[LogEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self._apply_filter()
        self.endResetModel()

    def append_entries(self, entries: list[LogEntry]) -> None:
        new_revs = {e.revision for e in self._entries}
        added = [e for e in entries if e.revision not in new_revs]
        if not added:
            return
        self.beginResetModel()
        self._entries.extend(added)
        self._apply_filter()
        self.endResetModel()

    def entry_at(self, row: int) -> LogEntry | None:
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None

    def oldest_revision(self) -> int | None:
        if self._entries:
            return min(e.revision for e in self._entries)
        return None

    def set_filter(self, text: str) -> None:
        self.beginResetModel()
        self._filter = text.lower().strip()
        self._apply_filter()
        self.endResetModel()

    def _apply_filter(self) -> None:
        if not self._filter:
            self._filtered = list(self._entries)
            return
        self._filtered = [
            e for e in self._entries
            if self._filter in e.author.lower()
            or self._filter in e.message.lower()
            or self._filter in str(e.revision)
        ]


# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------

class _DetailPanel(QWidget):
    """Shows full message and changed paths for a selected log entry."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._rev_label = QLabel("Select a revision to see details.")
        self._rev_label.setStyleSheet("font-weight: bold; color: #444;")
        layout.addWidget(self._rev_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._msg_edit = QTextEdit()
        self._msg_edit.setReadOnly(True)
        self._msg_edit.setPlaceholderText("Commit message")
        self._msg_edit.setMaximumHeight(120)
        splitter.addWidget(self._msg_edit)

        self._paths_list = QListWidget()
        self._paths_list.setMaximumHeight(120)
        splitter.addWidget(self._paths_list)

        splitter.setSizes([400, 300])
        layout.addWidget(splitter)

    def show_entry(self, entry: LogEntry) -> None:
        self._rev_label.setText(
            f"r{entry.revision}  ·  {entry.author}  ·  "
            f"{entry.date.strftime('%Y-%m-%d %H:%M') if entry.date != datetime.min else ''}"
        )
        self._msg_edit.setPlainText(entry.message.strip())
        self._paths_list.clear()
        for cp in entry.changed_paths:
            item = QListWidgetItem(f"[{cp.action}]  {cp.path}")
            self._paths_list.addItem(item)

    def clear(self) -> None:
        self._rev_label.setText("Select a revision to see details.")
        self._msg_edit.clear()
        self._paths_list.clear()


# ---------------------------------------------------------------------------
# Main LogViewer widget
# ---------------------------------------------------------------------------

class LogViewer(QWidget):
    """Revision log table with detail panel, search filter, and pagination.

    Signals:
        diff_requested(revision, wc_path): user double-clicked a row.
    """

    diff_requested = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wc_path: str | None = None
        self._worker: _LogWorker | None = None
        self._model = _LogModel()
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, wc_path: str, limit: int | None = None) -> None:
        """Fetch log for the given working-copy path."""
        if self._worker and self._worker.isRunning():
            return
        self._wc_path = wc_path
        if limit is None:
            s = QSettings()
            limit = int(s.value("Client/log_limit", 100))
        self._load_limit = limit
        self._status_label.setText("Loading log…")
        self._more_btn.setEnabled(False)
        worker = _LogWorker(wc_path, limit)
        worker.finished.connect(self._on_loaded)
        worker.error.connect(self._on_error)
        worker.start()
        self._worker = worker

    def load_more(self) -> None:
        """Fetch the next page of revisions."""
        if not self._wc_path or (self._worker and self._worker.isRunning()):
            return
        oldest = self._model.oldest_revision()
        if oldest is None or oldest <= 1:
            self._more_btn.setEnabled(False)
            return
        self._status_label.setText("Loading more…")
        self._more_btn.setEnabled(False)
        s = QSettings()
        limit = int(s.value("Client/log_limit", 100))
        worker = _LogWorker(self._wc_path, limit, start_rev=oldest)
        worker.finished.connect(self._on_more_loaded)
        worker.error.connect(self._on_error)
        worker.start()
        self._worker = worker

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search bar + Load More button
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 4, 4, 4)

        self._search = SearchBar("Filter by author, message, or revision…")
        self._search.search_changed.connect(self._on_filter)
        top_layout.addWidget(self._search)

        self._more_btn = QPushButton("Load More")
        self._more_btn.setFixedWidth(100)
        self._more_btn.setEnabled(False)
        self._more_btn.clicked.connect(self.load_more)
        top_layout.addWidget(self._more_btn)

        layout.addWidget(top_bar)

        # Main splitter: log table (top) / detail panel (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Log table
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)
        self._table.doubleClicked.connect(self._on_double_click)
        splitter.addWidget(self._table)

        # Detail panel
        self._detail = _DetailPanel()
        splitter.addWidget(self._detail)

        splitter.setSizes([400, 160])
        layout.addWidget(splitter)

        # Status bar
        self._status_label = QLabel("Open a working copy to view log.")
        self._status_label.setStyleSheet("padding: 2px 6px; color: #666; font-size: 12px;")
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_loaded(self, entries: list) -> None:
        self._model.set_entries(entries)
        count = len(entries)
        self._status_label.setText(f"{count} revision(s) loaded.")
        self._more_btn.setEnabled(count > 0 and (self._model.oldest_revision() or 1) > 1)

    def _on_more_loaded(self, entries: list) -> None:
        self._model.append_entries(entries)
        oldest = self._model.oldest_revision() or 1
        self._status_label.setText(f"{self._model.rowCount()} revision(s) loaded.")
        self._more_btn.setEnabled(oldest > 1)

    def _on_error(self, msg: str) -> None:
        self._status_label.setText(f"Error: {msg}")
        self._more_btn.setEnabled(False)

    def _on_filter(self, text: str) -> None:
        self._model.set_filter(text)
        self._status_label.setText(f"{self._model.rowCount()} revision(s) shown.")

    def _on_selection(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._detail.clear()
            return
        entry = self._model.entry_at(rows[0].row())
        if entry:
            self._detail.show_entry(entry)

    def _on_double_click(self, index: QModelIndex) -> None:
        entry = self._model.entry_at(index.row())
        if entry and self._wc_path:
            self.diff_requested.emit(entry.revision, self._wc_path)
