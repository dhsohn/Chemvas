from __future__ import annotations

from PyQt6.QtWidgets import QColorDialog


class MainWindowTextStyleService:
    def set_text_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        color = get_color(parent=window, title="Text Color")
        if color.isValid():
            window.canvas.set_text_color(color)

    def set_text_align(self, window, value: str) -> None:
        mapping = {"Left": "left", "Center": "center", "Right": "right"}
        window.canvas.set_text_alignment(mapping.get(value, "left"))

    def set_note_box_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        color = get_color(parent=window, title="Box Color")
        if color.isValid():
            window.canvas.set_note_box_color(color)

    def set_note_border_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        color = get_color(parent=window, title="Border Color")
        if color.isValid():
            window.canvas.set_note_border_color(color)

    def set_text_preset(self, window, value: str) -> None:
        if value == "ACS":
            window.canvas.apply_text_preset_acs()
        elif value == "Paper Thin":
            window.canvas.apply_text_preset_paper_thin()
        elif value == "Paper Bold":
            window.canvas.apply_text_preset_paper_bold()


__all__ = ["MainWindowTextStyleService"]
