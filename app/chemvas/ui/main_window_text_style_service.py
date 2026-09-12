from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from PyQt6.QtWidgets import QColorDialog, QDialog, QMessageBox

from chemvas.ui.note_appearance_dialog import NoteAppearanceDialog

if TYPE_CHECKING:
    from collections.abc import Callable


class MainWindowTextStyleService:
    _TEXT_PRESET_APPLIERS: ClassVar[dict[str, Callable[[Any], None]]] = {
        "ACS": lambda controller: controller.apply_text_preset_acs(),
        "Paper Thin": lambda controller: controller.apply_text_preset_paper_thin(),
        "Paper Bold": lambda controller: controller.apply_text_preset_paper_bold(),
    }

    def __init__(self, *, style_controller_for_window) -> None:
        self._style_controller_for_window = style_controller_for_window

    def _style_controller(self, window):
        return self._style_controller_for_window(window)

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

    def set_text_font_family_default(self, window, family: str) -> None:
        try:
            self._style_controller(window).set_text_font_family_default(family)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(window, "Text Font", str(error))


__all__ = ["MainWindowTextStyleService"]
