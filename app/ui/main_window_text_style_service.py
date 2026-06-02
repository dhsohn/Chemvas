from __future__ import annotations

from PyQt6.QtWidgets import QColorDialog


class MainWindowTextStyleService:
    _TEXT_ALIGNMENTS = {"Left": "left", "Center": "center", "Right": "right"}
    _TEXT_PRESET_APPLIERS = {
        "ACS": lambda canvas: canvas.apply_text_preset_acs(),
        "Paper Thin": lambda canvas: canvas.apply_text_preset_paper_thin(),
        "Paper Bold": lambda canvas: canvas.apply_text_preset_paper_bold(),
    }

    def _apply_dialog_color(self, window, *, title: str, setter, get_color=QColorDialog.getColor) -> None:
        color = get_color(parent=window, title=title)
        if not color.isValid():
            return
        setter(window.canvas, color)

    def set_text_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(
            window,
            title="Text Color",
            setter=lambda canvas, color: canvas.set_text_color(color),
            get_color=get_color,
        )

    def set_text_align(self, window, value: str) -> None:
        window.canvas.set_text_alignment(self._TEXT_ALIGNMENTS.get(value, "left"))

    def set_note_box_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(
            window,
            title="Box Color",
            setter=lambda canvas, color: canvas.set_note_box_color(color),
            get_color=get_color,
        )

    def set_note_border_color(self, window, *, get_color=QColorDialog.getColor) -> None:
        self._apply_dialog_color(
            window,
            title="Border Color",
            setter=lambda canvas, color: canvas.set_note_border_color(color),
            get_color=get_color,
        )

    def set_text_preset(self, window, value: str) -> None:
        apply_preset = self._TEXT_PRESET_APPLIERS.get(value)
        if apply_preset is None:
            return
        apply_preset(window.canvas)


__all__ = ["MainWindowTextStyleService"]
