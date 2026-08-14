"""Progress overlay widget — shows a spinner/progress bar over content."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class ProgressOverlay(QWidget):
    """Semi-transparent overlay with a progress bar and status label.

    Usage:
        overlay = ProgressOverlay(parent_widget)
        overlay.show_progress("Checking out repository...")
        overlay.set_progress(50)
        overlay.hide_progress()
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self.setStyleSheet("background-color: rgba(0, 0, 0, 120); border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("Working...")
        self._label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setFixedWidth(300)
        self._progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: white;
                background-color: rgba(255, 255, 255, 30);
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._progress, alignment=Qt.AlignmentFlag.AlignCenter)

    def show_progress(self, message: str = "Working...", indeterminate: bool = False) -> None:
        """Show the overlay with a message."""
        self._label.setText(message)
        if indeterminate:
            self._progress.setMaximum(0)  # Indeterminate mode.
        else:
            self._progress.setMaximum(100)
            self._progress.setValue(0)
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.setVisible(True)
        self.raise_()

    def set_progress(self, value: int) -> None:
        """Set progress bar value (0-100)."""
        self._progress.setValue(value)

    def set_message(self, message: str) -> None:
        """Update the status message."""
        self._label.setText(message)

    def hide_progress(self) -> None:
        """Hide the overlay."""
        self.setVisible(False)

    def resizeEvent(self, event: object) -> None:
        """Keep overlay sized to parent."""
        if self.parent():
            self.setGeometry(self.parent().rect())
