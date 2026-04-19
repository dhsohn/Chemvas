from __future__ import annotations

from PyQt6.QtWidgets import QColorDialog


class MainWindowTextStyleService:
    _TEXT_ALIGNMENTS = {"Left": "left", "Center": "center", "Right": "right"}
    _TEXT_PRESET_METHODS = {
        "ACS": "apply_text_preset_acs",
        "Paper Thin": "apply_text_preset_paper_thin",
        "Paper Bold": "apply_text_preset_paper_bold",
    }

    def _apply_dialog_color(self, window, *, title: str, setter_name: str, get_color=QColorDialog.getColor) -> None:
        color = get_color(parent=window, title=title)
        if not color.isValid():
            return
        getattr(window.canvas, setter_name)(color)

    def set_text_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(window, title="Text Color", setter_name="set_text_color", get_color=get_color)

    def set_text_align(self, window, value: str) -> None:
        window.canvas.set_text_alignment(self._TEXT_ALIGNMENTS.get(value, "left"))

    def set_note_box_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(window, title="Box Color", setter_name="set_note_box_color", get_color=get_color)

    def set_note_border_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(window, title="Border Color", setter_name="set_note_border_color", get_color=get_color)

    def set_text_preset(self, window, value: str) -> None:
        method_name = self._TEXT_PRESET_METHODS.get(value)
        if method_name is None:
            return
        getattr(window.canvas, method_name)()


__all__ = ["MainWindowTextStyleService"]
