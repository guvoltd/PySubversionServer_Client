"""Settings dialog for the SVN Client application."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ClientSettingsDialog(QDialog):
    """Settings dialog persisting to QSettings under 'General/' and 'Client/' keys."""

    theme_changed = Signal(str)  # emits new theme value when it changes on OK

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — SVN Client")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._settings = QSettings()
        self._setup_ui()
        self._load()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(self._build_appearance_group())
        layout.addWidget(self._build_wc_group())
        layout.addWidget(self._build_diff_group())
        layout.addWidget(self._build_log_group())
        layout.addWidget(self._build_status_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_appearance_group(self) -> QGroupBox:
        group = QGroupBox("Appearance")
        form = QFormLayout(group)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Light", "Dark", "Auto (system)"])
        self._theme_combo.setToolTip("Choose the application colour theme")
        form.addRow("Theme:", self._theme_combo)
        return group

    def _build_wc_group(self) -> QGroupBox:
        group = QGroupBox("Working Copy")
        form = QFormLayout(group)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self._default_wc_edit = QLineEdit()
        self._default_wc_edit.setPlaceholderText("Leave empty to use last opened path")
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_wc)
        row_layout.addWidget(self._default_wc_edit)
        row_layout.addWidget(browse)
        form.addRow("Default path:", row)
        return group

    def _build_diff_group(self) -> QGroupBox:
        group = QGroupBox("Diff Viewer")
        form = QFormLayout(group)
        self._diff_mode_combo = QComboBox()
        self._diff_mode_combo.addItems(["Side by Side", "Unified"])
        self._diff_mode_combo.setToolTip("Default display mode when opening the diff viewer")
        form.addRow("Default mode:", self._diff_mode_combo)
        return group

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("Revision Log")
        form = QFormLayout(group)
        self._log_limit_spin = QSpinBox()
        self._log_limit_spin.setRange(10, 5000)
        self._log_limit_spin.setSingleStep(50)
        self._log_limit_spin.setSuffix(" revisions")
        self._log_limit_spin.setToolTip("Maximum number of log entries fetched per request")
        form.addRow("Fetch limit:", self._log_limit_spin)
        return group

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Status Tree")
        v = QVBoxLayout(group)
        self._show_unversioned_check = QCheckBox("Show unversioned files (?)")
        self._show_unversioned_check.setToolTip(
            "Display files not tracked by SVN in the status tree"
        )
        v.addWidget(self._show_unversioned_check)
        return group

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    _THEME_VALUES = ["light", "dark", "auto"]

    def _load(self) -> None:
        s = self._settings
        theme = s.value("General/theme", "light")
        idx = self._THEME_VALUES.index(theme) if theme in self._THEME_VALUES else 0
        self._theme_combo.setCurrentIndex(idx)

        self._default_wc_edit.setText(s.value("Client/default_wc_path", ""))

        diff_mode = s.value("Client/diff_mode", "side_by_side")
        self._diff_mode_combo.setCurrentIndex(0 if diff_mode == "side_by_side" else 1)

        self._log_limit_spin.setValue(int(s.value("Client/log_limit", 500)))

        self._show_unversioned_check.setChecked(
            s.value("Client/show_unversioned", True, type=bool)
        )

    def _on_accept(self) -> None:
        s = self._settings

        new_theme = self._THEME_VALUES[self._theme_combo.currentIndex()]
        old_theme = s.value("General/theme", "light")
        s.setValue("General/theme", new_theme)

        s.setValue("Client/default_wc_path", self._default_wc_edit.text().strip())

        diff_values = ["side_by_side", "unified"]
        s.setValue("Client/diff_mode", diff_values[self._diff_mode_combo.currentIndex()])

        s.setValue("Client/log_limit", self._log_limit_spin.value())
        s.setValue("Client/show_unversioned", self._show_unversioned_check.isChecked())

        self.accept()

        if new_theme != old_theme:
            self.theme_changed.emit(new_theme)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_wc(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Default Working Copy Directory",
            self._default_wc_edit.text() or os.path.expanduser("~"),
        )
        if path:
            self._default_wc_edit.setText(path)
