"""Diff viewer widget — unified and side-by-side modes with line-number gutter.

T-301: all sub-tasks (a-e)
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import svn_shared.svn_client_svc as svc
from svn_shared.exceptions import SvnCommandError
from svn_shared.widgets.syntax_highlighter import DiffHighlighter


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _DiffWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, wc_path: str, file_path: str | None, revision: str | None) -> None:
        super().__init__()
        self._wc_path = wc_path
        self._file_path = file_path
        self._revision = revision

    def run(self) -> None:
        try:
            text = svc.diff(self._wc_path, revision=self._revision, file=self._file_path)
            self.finished.emit(text)
        except SvnCommandError as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Line-number gutter
# ---------------------------------------------------------------------------

class _LineNumberArea(QWidget):
    """Paints line numbers to the left of a CodeEditor."""

    def __init__(self, editor: _CodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        self._editor.paint_line_numbers(event)


class _CodeEditor(QPlainTextEdit):
    """QPlainTextEdit with a line-number gutter on the left."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gutter = _LineNumberArea(self)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Monospace", 10)
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self.setFont(font)

        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self._update_gutter_width()

    # ------------------------------------------------------------------
    # Gutter width
    # ------------------------------------------------------------------

    def line_number_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 6 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    # ------------------------------------------------------------------
    # Paint line numbers
    # ------------------------------------------------------------------

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor("#f6f8fa"))

        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#999"))
                painter.drawText(
                    0, top, self._gutter.width() - 3,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(num + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            num += 1


# ---------------------------------------------------------------------------
# Unified diff widget
# ---------------------------------------------------------------------------

class _UnifiedView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._editor = _CodeEditor()
        self._hl = DiffHighlighter(self._editor.document())
        layout.addWidget(self._editor)

    def set_diff(self, text: str) -> None:
        self._editor.setPlainText(text)
        self._editor.moveCursor(QTextCursor.MoveOperation.Start)


# ---------------------------------------------------------------------------
# Side-by-side diff helpers
# ---------------------------------------------------------------------------

def _parse_side_by_side(diff_text: str) -> tuple[list[str], list[str]]:
    """Split a unified diff into (left_lines, right_lines).

    Left  = original (context + removed).
    Right = modified (context + added).
    Lines that belong only to one side get an empty string on the other.
    """
    left: list[str] = []
    right: list[str] = []

    for line in diff_text.splitlines(keepends=False):
        if line.startswith("---") or line.startswith("+++") or line.startswith("Index:") or line.startswith("==="):
            left.append(line)
            right.append(line)
        elif line.startswith("@@"):
            left.append(line)
            right.append(line)
        elif line.startswith("+"):
            left.append("")
            right.append(line[1:])
        elif line.startswith("-"):
            left.append(line[1:])
            right.append("")
        else:
            ctx = line[1:] if line.startswith(" ") else line
            left.append(ctx)
            right.append(ctx)

    return left, right


class _SideBySideView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._left  = _CodeEditor()
        self._right = _CodeEditor()

        # Synchronise vertical scroll bars
        self._left.verticalScrollBar().valueChanged.connect(
            self._right.verticalScrollBar().setValue
        )
        self._right.verticalScrollBar().valueChanged.connect(
            self._left.verticalScrollBar().setValue
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._left)
        splitter.addWidget(self._right)
        splitter.setSizes([1, 1])
        layout.addWidget(splitter)

        # Highlight added/removed lines with background colours
        self._fmt_add = QTextCharFormat()
        self._fmt_add.setBackground(QColor("#e6ffed"))

        self._fmt_del = QTextCharFormat()
        self._fmt_del.setBackground(QColor("#ffeef0"))

    def set_diff(self, diff_text: str) -> None:
        left_lines, right_lines = _parse_side_by_side(diff_text)

        self._left.setPlainText("\n".join(left_lines))
        self._right.setPlainText("\n".join(right_lines))

        # Colour removed lines on left
        self._apply_bg(self._left, diff_text, removed=True)
        # Colour added lines on right
        self._apply_bg(self._right, diff_text, removed=False)

        self._left.moveCursor(QTextCursor.MoveOperation.Start)
        self._right.moveCursor(QTextCursor.MoveOperation.Start)

    def _apply_bg(self, editor: _CodeEditor, diff_text: str, removed: bool) -> None:
        """Apply background colour to changed lines in the side panel."""
        fmt = self._fmt_del if removed else self._fmt_add
        prefix = "-" if removed else "+"
        other = "+" if removed else "-"

        doc = editor.document()
        cursor = QTextCursor(doc)
        block = doc.begin()
        diff_lines = diff_text.splitlines()
        src_idx = 0

        for block_num in range(doc.blockCount()):
            line = block.text()
            # Advance through original diff to find matching marker
            while src_idx < len(diff_lines):
                dl = diff_lines[src_idx]
                if dl.startswith(prefix) and dl[1:] == line:
                    cursor = QTextCursor(block)
                    cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                    cursor.setBlockCharFormat(fmt)
                    src_idx += 1
                    break
                elif dl.startswith(other):
                    src_idx += 1
                    continue
                else:
                    src_idx += 1
                    break
            block = block.next()


# ---------------------------------------------------------------------------
# Main DiffViewer widget
# ---------------------------------------------------------------------------

class DiffViewer(QWidget):
    """Shows SVN diff output in unified or side-by-side mode.

    Usage:
        viewer.load_diff(diff_text)
        viewer.load_from_wc(wc_path, file_path="src/foo.py", revision="BASE")
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wc_path: str | None = None
        self._worker: _DiffWorker | None = None
        self._current_diff: str = ""
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_diff(self, diff_text: str) -> None:
        """Display an already-fetched diff string."""
        self._current_diff = diff_text
        self._header_label.setText("")
        self._apply_to_current_view(diff_text)

    def load_from_wc(
        self,
        wc_path: str,
        file_path: str | None = None,
        revision: str | None = None,
    ) -> None:
        """Fetch and display diff for wc_path (optionally scoped to file_path and revision)."""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self._wc_path = wc_path
        label = file_path or wc_path
        rev_label = f" vs r{revision}" if revision else " vs BASE"
        self._header_label.setText(f"{label}{rev_label}")
        self._header_label.setStyleSheet("color: #666; padding: 2px 6px;")

        self._worker = _DiffWorker(wc_path, file_path, revision)
        self._worker.finished.connect(self.load_diff)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))

        self._unified_btn = QPushButton("Unified")
        self._unified_btn.setCheckable(True)
        self._unified_btn.setChecked(True)
        self._unified_btn.setFixedHeight(24)
        self._unified_btn.clicked.connect(lambda: self._set_mode("unified"))

        self._side_btn = QPushButton("Side by Side")
        self._side_btn.setCheckable(True)
        self._side_btn.setFixedHeight(24)
        self._side_btn.clicked.connect(lambda: self._set_mode("side_by_side"))

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(24)
        copy_btn.clicked.connect(self._copy_diff)

        font_up = QPushButton("A+")
        font_up.setFixedWidth(32)
        font_up.setFixedHeight(24)
        font_up.clicked.connect(lambda: self._adjust_font(+1))

        font_dn = QPushButton("A-")
        font_dn.setFixedWidth(32)
        font_dn.setFixedHeight(24)
        font_dn.clicked.connect(lambda: self._adjust_font(-1))

        self._header_label = QLabel()
        self._header_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        toolbar.addWidget(self._unified_btn)
        toolbar.addWidget(self._side_btn)
        toolbar.addSeparator()
        toolbar.addWidget(copy_btn)
        toolbar.addSeparator()
        toolbar.addWidget(font_dn)
        toolbar.addWidget(font_up)
        toolbar.addSeparator()
        toolbar.addWidget(self._header_label)

        layout.addWidget(toolbar)

        # Stacked pages: 0=unified, 1=side-by-side
        self._stack = QStackedWidget()
        self._unified_view = _UnifiedView()
        self._side_view = _SideBySideView()
        self._stack.addWidget(self._unified_view)
        self._stack.addWidget(self._side_view)
        layout.addWidget(self._stack)

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        if mode == "unified":
            self._unified_btn.setChecked(True)
            self._side_btn.setChecked(False)
            self._stack.setCurrentIndex(0)
            if self._current_diff:
                self._unified_view.set_diff(self._current_diff)
        else:
            self._side_btn.setChecked(True)
            self._unified_btn.setChecked(False)
            self._stack.setCurrentIndex(1)
            if self._current_diff:
                self._side_view.set_diff(self._current_diff)

    def _apply_to_current_view(self, text: str) -> None:
        if self._stack.currentIndex() == 0:
            self._unified_view.set_diff(text)
        else:
            self._side_view.set_diff(text)

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _copy_diff(self) -> None:
        QApplication.clipboard().setText(self._current_diff)

    def _adjust_font(self, delta: int) -> None:
        for editor in (self._unified_view._editor, self._side_view._left, self._side_view._right):
            f = editor.font()
            f.setPointSize(max(6, f.pointSize() + delta))
            editor.setFont(f)

    def _on_error(self, msg: str) -> None:
        self._header_label.setText(f"Error: {msg}")
        self._header_label.setStyleSheet("color: red; padding: 2px 6px;")
