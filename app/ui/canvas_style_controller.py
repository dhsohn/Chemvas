from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from ui.renderer_style_access import atom_color_for, font_size_pt_for
from ui.selection_style_state import selection_style_state_for


class CanvasStyleController:
    def __init__(self, canvas: Any, *, note_controller=None) -> None:
        self.canvas = canvas
        self.note_controller = note_controller

    def _apply_text_style_to_selected(self) -> None:
        controller = self.note_controller
        apply_style = getattr(controller, "apply_text_style_to_selected", None)
        if callable(apply_style):
            apply_style()

    @property
    def text_style(self):
        return text_style_state_for(self.canvas)

    def _set_text_style(self, name: str, value: Any) -> None:
        set_text_style_for(self.canvas, name, value)

    def set_selection_color(self, color: QColor) -> None:
        if color.isValid():
            selection_style_state_for(self.canvas).color = color

    def set_selection_stroke_delta(self, delta: float) -> None:
        selection_style_state_for(self.canvas).stroke_delta = max(0.1, float(delta))

    def get_selection_stroke_delta(self) -> float:
        return float(selection_style_state_for(self.canvas).stroke_delta)

    def suspend_selection_outline(self, suspend: bool) -> None:
        selection_style_state_for(self.canvas).suspend_outline = bool(suspend)

    def set_text_font(self, font: QFont) -> None:
        self._set_text_style("text_font_family", font.family())
        self._apply_text_style_to_selected()

    def set_text_size(self, size: int) -> None:
        self._set_text_style("text_font_size", max(6, int(size)))
        self._apply_text_style_to_selected()

    def set_text_weight(self, weight: int) -> None:
        self._set_text_style("text_font_weight", max(1, min(1000, int(weight))))
        self._apply_text_style_to_selected()

    def get_text_weight(self) -> int:
        return int(self.text_style.text_font_weight)

    def set_text_italic(self, enabled: bool) -> None:
        self._set_text_style("text_italic", bool(enabled))
        self._apply_text_style_to_selected()

    def set_text_color(self, color: QColor) -> None:
        if color.isValid():
            self._set_text_style("text_color", color)
            self._apply_text_style_to_selected()

    def get_text_font(self) -> QFont:
        style = self.text_style
        return QFont(style.text_font_family, style.text_font_size)

    def get_text_size(self) -> int:
        return self.text_style.text_font_size

    def apply_text_preset_acs(self) -> None:
        self._set_text_style("text_font_family", "Arial")
        self._set_text_style("text_font_size", font_size_pt_for(self.canvas))
        self._set_text_style("text_font_weight", QFont.Weight.Normal)
        self._set_text_style("text_italic", False)
        self._set_text_style("text_color", QColor(atom_color_for(self.canvas)))
        self._set_text_style("text_alignment", Qt.AlignmentFlag.AlignLeft)
        self._set_text_style("text_line_spacing", 1.0)
        self._set_text_style("note_box_enabled", False)
        self._set_text_style("note_border_enabled", False)
        self._apply_text_style_to_selected()

    def apply_text_preset_paper_thin(self) -> None:
        self._set_text_style("text_font_family", "Arial")
        self._set_text_style("text_font_size", max(9, font_size_pt_for(self.canvas) - 1))
        self._set_text_style("text_font_weight", QFont.Weight.Normal)
        self._set_text_style("text_italic", False)
        self._set_text_style("text_color", QColor("#222222"))
        self._set_text_style("text_alignment", Qt.AlignmentFlag.AlignLeft)
        self._set_text_style("text_line_spacing", 1.05)
        self._set_text_style("note_box_enabled", False)
        self._set_text_style("note_border_enabled", False)
        self._apply_text_style_to_selected()

    def apply_text_preset_paper_bold(self) -> None:
        self._set_text_style("text_font_family", "Arial")
        self._set_text_style("text_font_size", font_size_pt_for(self.canvas) + 2)
        self._set_text_style("text_font_weight", QFont.Weight.DemiBold)
        self._set_text_style("text_italic", False)
        self._set_text_style("text_color", QColor("#111111"))
        self._set_text_style("text_alignment", Qt.AlignmentFlag.AlignLeft)
        self._set_text_style("text_line_spacing", 1.1)
        self._set_text_style("note_box_enabled", True)
        self._set_text_style("note_box_color", QColor("#ffffff"))
        self._set_text_style("note_box_alpha", 1.0)
        self._set_text_style("note_border_enabled", True)
        self._set_text_style("note_border_color", QColor("#111111"))
        self._set_text_style("note_border_width", 1.2)
        self._set_text_style("note_padding", 8.0)
        self._apply_text_style_to_selected()

    def set_text_alignment(self, alignment: str) -> None:
        mapping = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }
        if alignment in mapping:
            self._set_text_style("text_alignment", mapping[alignment])
            self._apply_text_style_to_selected()

    def set_text_line_spacing(self, spacing: float) -> None:
        self._set_text_style("text_line_spacing", max(0.8, float(spacing)))
        self._apply_text_style_to_selected()

    def set_note_box_enabled(self, enabled: bool) -> None:
        self._set_text_style("note_box_enabled", bool(enabled))
        self._apply_text_style_to_selected()

    def set_note_box_color(self, color: QColor) -> None:
        if color.isValid():
            self._set_text_style("note_box_color", color)
            self._apply_text_style_to_selected()

    def set_note_box_alpha(self, alpha: float) -> None:
        self._set_text_style("note_box_alpha", max(0.0, min(1.0, float(alpha))))
        self._apply_text_style_to_selected()

    def get_note_box_alpha(self) -> float:
        return self.text_style.note_box_alpha

    def set_note_border_enabled(self, enabled: bool) -> None:
        self._set_text_style("note_border_enabled", bool(enabled))
        self._apply_text_style_to_selected()

    def set_note_border_color(self, color: QColor) -> None:
        if color.isValid():
            self._set_text_style("note_border_color", color)
            self._apply_text_style_to_selected()

    def set_note_border_width(self, width: float) -> None:
        self._set_text_style("note_border_width", max(0.5, float(width)))
        self._apply_text_style_to_selected()

    def set_note_padding(self, padding: float) -> None:
        self._set_text_style("note_padding", max(2.0, float(padding)))
        self._apply_text_style_to_selected()


__all__ = ["CanvasStyleController"]
