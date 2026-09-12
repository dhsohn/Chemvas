"""Edit the existing document-wide note box and line-spacing settings."""

from __future__ import annotations

from functools import partial
from typing import cast

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
)


class NoteAppearanceDialog(QDialog):
    def __init__(self, values: dict[str, object], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Note Appearance")
        self._values = dict(values)
        self._initial_numbers: dict[str, float] = {}
        self.checks: dict[str, QCheckBox] = {}
        self.numbers: dict[str, QDoubleSpinBox] = {}
        self.colors: dict[str, QPushButton] = {}
        layout = QFormLayout(self)
        notice = QLabel(
            "Applies to every note in this document, including new notes.\n"
            "Character formatting is unchanged.",
            self,
        )
        notice.setWordWrap(True)
        layout.addRow(notice)
        for name, label in (
            ("note_box_enabled", "Background fill"),
            ("note_border_enabled", "Border"),
        ):
            check = QCheckBox(label, self)
            check.setChecked(cast("bool", values[name]))
            self.checks[name] = check
            layout.addRow(check)
        for name, label in (
            ("note_box_color", "Fill color"),
            ("note_border_color", "Border color"),
        ):
            button = QPushButton(str(values[name]), self)
            button.clicked.connect(partial(self._choose_color, name, label))
            self.colors[name] = button
            layout.addRow(label, button)
        for name, label, minimum, maximum in (
            ("note_box_alpha", "Fill opacity", 0.0, 1.0),
            ("note_border_width", "Border width (canvas units)", 0.5, 1_000_000.0),
            ("note_padding", "Padding (canvas units)", 2.0, 1_000_000.0),
            ("text_line_spacing", "Line spacing multiplier", 0.8, 1_000_000.0),
        ):
            spin = QDoubleSpinBox(self)
            spin.setDecimals(4)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(
                0.1 if name in {"note_box_alpha", "text_line_spacing"} else 0.5
            )
            spin.setValue(float(cast("float", values[name])))
            self.numbers[name] = spin
            self._initial_numbers[name] = spin.value()
            layout.addRow(label, spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _choose_color(self, name: str, title: str) -> None:
        color = QColorDialog.getColor(QColor(str(self._values[name])), self, title)
        if color.isValid():
            self._values[name] = color.name()
            self.colors[name].setText(color.name())

    def appearance_values(self) -> dict[str, object]:
        values = dict(self._values)
        for name, check in self.checks.items():
            values[name] = check.isChecked()
        for name, spin in self.numbers.items():
            # Accepting displayed rounding or a clipped imported value is a no-op.
            if spin.value() != self._initial_numbers[name]:
                values[name] = spin.value()
        return values


__all__ = ["NoteAppearanceDialog"]
