from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from PyQt6.QtWidgets import QColorDialog, QDialog, QMessageBox

from chemvas.ui.dialogs.note_appearance_dialog import NoteAppearanceDialog
from chemvas.ui.window.main_window_ports import (
    note_controller_for_window,
    style_controller_for_window,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class MainWindowTextStyleService:
    _TEXT_PRESET_APPLIERS: ClassVar[dict[str, Callable[[Any], None]]] = {
        "ACS": lambda controller: controller.apply_text_preset_acs(),
        "Paper Thin": lambda controller: controller.apply_text_preset_paper_thin(),
        "Paper Bold": lambda controller: controller.apply_text_preset_paper_bold(),
    }

    def _style_controller(self, window):
        return style_controller_for_window(window)

    def _apply_dialog_color(
        self, window, *, title: str, setter, get_color=QColorDialog.getColor
    ) -> None:
        color = get_color(parent=window, title=title)
        if not color.isValid():
            return
        setter(self._style_controller(window), color)

    def set_text_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(
            window,
            title="Text Color",
            setter=lambda controller, color: controller.set_text_color(color),
            get_color=get_color,
        )

    def set_note_box_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(
            window,
            title="Box Color",
            setter=lambda controller, color: controller.set_note_box_color(color),
            get_color=get_color,
        )

    def set_note_border_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(
            window,
            title="Border Color",
            setter=lambda controller, color: controller.set_note_border_color(color),
            get_color=get_color,
        )

    def set_text_preset(self, window, value: str) -> None:
        apply_preset = self._TEXT_PRESET_APPLIERS.get(value)
        if apply_preset is None:
            return
        apply_preset(self._style_controller(window))

    def edit_note_appearance(self, window) -> None:
        controller = self._style_controller(window)
        dialog = NoteAppearanceDialog(controller.note_appearance(), window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            controller.set_note_appearance(dialog.appearance_values())
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(window, "Note Appearance", str(error))

    def set_note_font_family(self, window, family: str) -> None:
        """Apply a font to the edited note, or make it the default for new notes."""
        controller = note_controller_for_window(window)
        if controller is None:
            return
        if controller.text_format_targets():
            controller.set_text_font_family(family)
        else:
            self.set_text_font_family_default(window, family)

    def set_text_font_family_default(self, window, family: str) -> None:
        try:
            self._style_controller(window).set_text_font_family_default(family)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(window, "Text Font", str(error))


__all__ = ["MainWindowTextStyleService"]
