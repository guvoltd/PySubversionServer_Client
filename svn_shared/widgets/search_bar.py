"""Reusable search/filter bar widget."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class SearchBar(QWidget):
    """A search bar with text input, clear button, and search signal.

    Signals:
        search_changed: Emitted when the search text changes (debounced by Enter or clear).
        search_submitted: Emitted when the user presses Enter.
    """

    search_changed = Signal(str)
    search_submitted = Signal(str)

    def __init__(self, placeholder: str = "Search...", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setClearButtonEnabled(True)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_return)
        layout.addWidget(self._input)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(60)
        self._clear_btn.clicked.connect(self.clear)
        layout.addWidget(self._clear_btn)

    def text(self) -> str:
        """Get current search text."""
        return self._input.text()

    def clear(self) -> None:
        """Clear the search input."""
        self._input.clear()

    def set_focus(self) -> None:
        """Set keyboard focus to the search input."""
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _on_text_changed(self, text: str) -> None:
        self.search_changed.emit(text)

    def _on_return(self) -> None:
        self.search_submitted.emit(self._input.text())
