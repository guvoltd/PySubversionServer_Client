"""
A dialog for running a command with pkexec and displaying its output.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class PkexecRunnerDialog(QDialog):
    """A dialog that runs a command via pkexec and displays its output."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("System Configuration")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        layout.addWidget(self._text_edit)

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self._button_box.accepted.connect(self.accept)
        layout.addWidget(self._button_box)

        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)

    def _on_stdout(self) -> None:
        self._text_edit.appendPlainText(self._process.readAllStandardOutput().data().decode().strip())

    def _on_stderr(self) -> None:
        self._text_edit.appendPlainText(self._process.readAllStandardError().data().decode().strip())

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        if status == QProcess.ExitStatus.CrashExit:
            self._text_edit.appendPlainText("\nError: The process crashed.")
        elif code != 0:
            self._text_edit.appendPlainText(f"\nError: The process exited with code {code}.")

    def run(self, command: list[str]) -> int:
        """Run the command with pkexec and execute the dialog."""
        self._text_edit.clear()
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        full_command = ["pkexec"] + command
        self._process.start(full_command[0], full_command[1:])

        return self.exec()