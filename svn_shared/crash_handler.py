"""Global crash handler and rotating-file application logging.

Usage (in __main__.py, after QApplication is created):

    from svn_shared.crash_handler import install_crash_handler
    logger = install_crash_handler("svn-client")

install_crash_handler sets sys.excepthook so any unhandled exception:
  1. Is written to the rotating log file.
  2. Shows a dialog with the traceback and a Copy-to-Clipboard button.

Log files rotate at 1 MB each; 5 files are kept:
    ~/.local/share/{app_name}/logs/app.log
    ~/.local/share/{app_name}/logs/app.log.1  ... .5
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback
from types import TracebackType

_MAX_BYTES = 1 * 1024 * 1024   # 1 MB per log file
_BACKUP_COUNT = 5               # rotate into 5 backup files


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(app_name: str, debug_level: int = 0) -> logging.Logger:
    """Configure rotating-file + stderr logging. Returns the root app logger."""
    data_home = os.environ.get(
        "XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share")
    )
    log_dir = os.path.join(data_home, app_name, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    # Get the root logger. This ensures that all loggers created via
    # logging.getLogger(__name__) in other modules will propagate their
    # messages up to these handlers.
    logger = logging.getLogger()

    # Remove existing handlers to prevent duplication on re-init
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Determine levels based on debug_level setting
    if debug_level >= 1:  # Levels 1 and 2 have DEBUG enabled on the logger
        logger.setLevel(logging.DEBUG)
    else:  # Level 0
        logger.setLevel(logging.INFO)

    if debug_level >= 2:
        console_level = logging.DEBUG
    elif debug_level == 1:
        console_level = logging.INFO
    else:  # level 0
        console_level = logging.WARNING

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(console_level)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    logger.info(
        "Logging started. Log: %s. Logger level: %s. Console level: %s.",
        log_path, logging.getLevelName(logger.level), logging.getLevelName(console_level))
    return logger


# ---------------------------------------------------------------------------
# Crash dialog
# ---------------------------------------------------------------------------

def _show_crash_dialog(app_name: str, tb_text: str) -> None:
    """Show a modal dialog with the traceback text. Safe to call from excepthook."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import (
            QApplication,
            QDialog,
            QDialogButtonBox,
            QLabel,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
        )

        if not QApplication.instance():
            return  # can't show dialog without a running QApplication

        dlg = QDialog()
        dlg.setWindowTitle(f"{app_name} — Unexpected Error")
        dlg.setMinimumSize(680, 440)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel(
            "<b>An unexpected error occurred.</b><br>"
            "The application may be unstable. The error details have been saved to the "
            "application log file."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        tb_edit = QPlainTextEdit(tb_text)
        tb_edit.setReadOnly(True)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        mono.setPointSize(9)
        tb_edit.setFont(mono)
        layout.addWidget(tb_edit)

        btn_box = QDialogButtonBox()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(tb_text))
        btn_box.addButton(copy_btn, QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = btn_box.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(btn_box)

        dlg.exec()
    except Exception:
        # If the dialog itself crashes, fall back to stderr.
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_crash_handler(app_name: str, debug_level: int = 0) -> logging.Logger:
    """Install sys.excepthook crash dialog and return a configured logger.

    Call once, after QApplication is created and before the main window is shown.
    KeyboardInterrupt is forwarded to the default excepthook (allows Ctrl+C to work).
    """
    logger = setup_logging(app_name, debug_level=debug_level)

    def _excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        tb_text = "".join(tb_lines)
        logger.critical("Unhandled exception:\n%s", tb_text)
        _show_crash_dialog(app_name, tb_text)

    sys.excepthook = _excepthook
    logger.debug("Crash handler installed for app: %s", app_name)
    return logger
