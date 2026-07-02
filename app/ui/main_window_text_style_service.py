from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from PyQt6.QtWidgets import QColorDialog


class MainWindowTextStyleService:
    _TEXT_ALIGNMENTS: ClassVar[dict[str, str]] = {"Left": "left", "Center": "center", "Right": "right"}
    _TEXT_PRESET_APPLIERS: ClassVar[dict[str, Callable[[Any], None]]] = {
        "ACS": lambda controller: controller.apply_text_preset_acs(),
        "Paper Thin": lambda controller: controller.apply_text_preset_paper_thin(),
        "Paper Bold": lambda controller: controller.apply_text_preset_paper_bold(),
    }

    def __init__(self, *, style_controller_for_window) -> None:
        self._style_controller_for_window = style_controller_for_window

    def _style_controller(self, window):
        return self._style_controller_for_window(window)

    def _apply_dialog_color(self, window, *, title: str, setter, get_color=QColorDialog.getColor) -> None:
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

    def set_text_align(self, window, value: str) -> None:
        self._style_controller(window).set_text_alignment(self._TEXT_ALIGNMENTS.get(value, "left"))

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


__all__ = ["MainWindowTextStyleService"]
