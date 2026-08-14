"""Syntax highlighter for diff output and shell scripts."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument


class DiffHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for unified diff output."""

    def __init__(self, parent: QTextDocument | None = None) -> None:
        super().__init__(parent)

        self._formats: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # Added lines (green).
        fmt_add = QTextCharFormat()
        fmt_add.setForeground(QColor("#22863a"))
        fmt_add.setBackground(QColor("#f0fff4"))
        self._formats.append((QRegularExpression(r"^\+(?!\+\+).*$"), fmt_add))

        # Removed lines (red).
        fmt_del = QTextCharFormat()
        fmt_del.setForeground(QColor("#cb2431"))
        fmt_del.setBackground(QColor("#ffeef0"))
        self._formats.append((QRegularExpression(r"^-(?!--).*$"), fmt_del))

        # Hunk headers (blue).
        fmt_hunk = QTextCharFormat()
        fmt_hunk.setForeground(QColor("#0366d6"))
        fmt_hunk.setFontWeight(QFont.Weight.Bold)
        self._formats.append((QRegularExpression(r"^@@.*@@.*$"), fmt_hunk))

        # File headers.
        fmt_header = QTextCharFormat()
        fmt_header.setFontWeight(QFont.Weight.Bold)
        self._formats.append((QRegularExpression(r"^(---|\+\+\+|Index:|===).*$"), fmt_header))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._formats:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class ShellHighlighter(QSyntaxHighlighter):
    """Basic syntax highlighter for shell/bash scripts."""

    def __init__(self, parent: QTextDocument | None = None) -> None:
        super().__init__(parent)

        self._formats: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # Comments.
        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#6a737d"))
        fmt_comment.setFontItalic(True)
        self._formats.append((QRegularExpression(r"#.*$"), fmt_comment))

        # Strings.
        fmt_string = QTextCharFormat()
        fmt_string.setForeground(QColor("#032f62"))
        self._formats.append((QRegularExpression(r'"[^"]*"'), fmt_string))
        self._formats.append((QRegularExpression(r"'[^']*'"), fmt_string))

        # Variables.
        fmt_var = QTextCharFormat()
        fmt_var.setForeground(QColor("#e36209"))
        self._formats.append((QRegularExpression(r"\$\{?\w+\}?"), fmt_var))

        # Keywords.
        fmt_kw = QTextCharFormat()
        fmt_kw.setForeground(QColor("#d73a49"))
        fmt_kw.setFontWeight(QFont.Weight.Bold)
        keywords = r"\b(if|then|else|elif|fi|for|do|done|while|case|esac|function|return|exit)\b"
        self._formats.append((QRegularExpression(keywords), fmt_kw))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._formats:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
