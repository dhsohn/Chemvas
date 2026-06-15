from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ui.export_dialog_logic import (
    DEFAULT_DPI,
    DPI_OPTIONS,
    EXPORT_BACKGROUNDS,
    EXPORT_FORMATS,
    EXPORT_SCOPES,
    EXPORT_SIZES,
    is_dpi_relevant,
)
from ui.main_window_toolbar_buttons import ArrowButton
from ui.sheet_setup_logic import SHEET_ORIENTATION_OPTIONS, supported_sheet_sizes


@dataclass(frozen=True)
class FigureExportOptions:
    fmt: str
    sizing: str
    scope: str
    dpi: int
    background: str


@dataclass(frozen=True)
class SheetSetupSelection:
    size: str
    orientation: str


def _add_action_row(layout: QVBoxLayout, *, accept_label: str) -> tuple[QPushButton, QPushButton]:
    action_row = QHBoxLayout()
    action_row.addStretch(1)
    accept_btn = QPushButton(accept_label)
    cancel_btn = QPushButton("Cancel")
    action_row.addWidget(accept_btn)
    action_row.addWidget(cancel_btn)
    layout.addLayout(action_row)
    return accept_btn, cancel_btn


def prompt_export_options(window) -> FigureExportOptions | None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Export Figure")
    dialog.setStyleSheet(window.styleSheet())
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Format:"))
    format_combo = QComboBox()
    format_combo.setObjectName("exportFormatCombo")
    for label, fmt, _suffix in EXPORT_FORMATS:
        format_combo.addItem(label, fmt)
    layout.addWidget(format_combo)

    layout.addWidget(QLabel("Size:"))
    size_combo = QComboBox()
    size_combo.setObjectName("exportSizeCombo")
    for label, value in EXPORT_SIZES:
        size_combo.addItem(label, value)
    layout.addWidget(size_combo)

    layout.addWidget(QLabel("Scope:"))
    scope_combo = QComboBox()
    scope_combo.setObjectName("exportScopeCombo")
    for label, value in EXPORT_SCOPES:
        scope_combo.addItem(label, value)
    layout.addWidget(scope_combo)

    layout.addWidget(QLabel("Background:"))
    background_combo = QComboBox()
    background_combo.setObjectName("exportBackgroundCombo")
    for label, value in EXPORT_BACKGROUNDS:
        background_combo.addItem(label, value)
    layout.addWidget(background_combo)

    dpi_label = QLabel("Resolution (DPI):")
    layout.addWidget(dpi_label)
    dpi_combo = QComboBox()
    dpi_combo.setObjectName("exportDpiCombo")
    for dpi_value in DPI_OPTIONS:
        dpi_combo.addItem(str(dpi_value), dpi_value)
    dpi_combo.setCurrentIndex(DPI_OPTIONS.index(DEFAULT_DPI))
    layout.addWidget(dpi_combo)

    def sync_dpi_enabled() -> None:
        enabled = is_dpi_relevant(format_combo.currentData())
        dpi_label.setEnabled(enabled)
        dpi_combo.setEnabled(enabled)

    format_combo.currentIndexChanged.connect(sync_dpi_enabled)
    sync_dpi_enabled()

    export_btn, cancel_btn = _add_action_row(layout, accept_label="Export")
    export_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return FigureExportOptions(
        fmt=format_combo.currentData(),
        sizing=size_combo.currentData(),
        scope=scope_combo.currentData(),
        dpi=int(dpi_combo.currentData()),
        background=background_combo.currentData(),
    )


def prompt_bond_length(window, current: float) -> float | None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Bond Length")
    dialog.setStyleSheet(window.styleSheet())
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Set bond length (px):"))

    frame = QFrame()
    frame.setObjectName("spinFrame")
    frame_layout = QHBoxLayout(frame)
    frame_layout.setContentsMargins(2, 2, 2, 2)
    frame_layout.setSpacing(0)

    spin = QDoubleSpinBox()
    spin.setDecimals(1)
    spin.setRange(10.0, 200.0)
    spin.setValue(current)
    spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    spin.setMinimumWidth(90)
    spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    frame_layout.addWidget(spin)

    buttons_col = QVBoxLayout()
    buttons_col.setContentsMargins(0, 0, 0, 0)
    buttons_col.setSpacing(0)
    up_btn = ArrowButton("up")
    up_btn.setObjectName("spinUpButton")
    up_btn.setFixedSize(18, 14)
    down_btn = ArrowButton("down")
    down_btn.setObjectName("spinDownButton")
    down_btn.setFixedSize(18, 14)
    buttons_col.addWidget(up_btn)
    buttons_col.addWidget(down_btn)
    frame_layout.addLayout(buttons_col)

    layout.addWidget(frame)

    ok_btn, cancel_btn = _add_action_row(layout, accept_label="OK")

    up_btn.clicked.connect(lambda: spin.setValue(min(200.0, spin.value() + 1.0)))
    down_btn.clicked.connect(lambda: spin.setValue(max(10.0, spin.value() - 1.0)))
    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return spin.value()


def prompt_sheet_setup(window, *, current_size: str, current_orientation: str) -> SheetSetupSelection | None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Setup Sheet")
    dialog.setStyleSheet(window.styleSheet())
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Sheet size:"))

    size_combo = QComboBox()
    size_combo.setObjectName("sheetSizeCombo")
    size_combo.addItems(supported_sheet_sizes())
    size_index = size_combo.findText(current_size)
    if size_index >= 0:
        size_combo.setCurrentIndex(size_index)
    layout.addWidget(size_combo)

    layout.addWidget(QLabel("Orientation:"))

    orientation_combo = QComboBox()
    orientation_combo.setObjectName("sheetOrientationCombo")
    for value, label in SHEET_ORIENTATION_OPTIONS:
        orientation_combo.addItem(label, value)
        if value == current_orientation:
            orientation_combo.setCurrentIndex(orientation_combo.count() - 1)
    layout.addWidget(orientation_combo)

    ok_btn, cancel_btn = _add_action_row(layout, accept_label="OK")
    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return SheetSetupSelection(size=size_combo.currentText(), orientation=orientation_combo.currentData())


__all__ = [
    "FigureExportOptions",
    "SheetSetupSelection",
    "prompt_bond_length",
    "prompt_export_options",
    "prompt_sheet_setup",
]
