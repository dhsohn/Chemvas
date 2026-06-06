from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class CanvasTextStyleState:
    text_font_family: str = "Arial"
    text_font_size: int = 12
    text_font_weight: int | QFont.Weight = QFont.Weight.Normal
    text_italic: bool = False
    text_color: QColor = field(default_factory=lambda: QColor("#222222"))
    text_alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft
    text_line_spacing: float = 1.0
    note_box_enabled: bool = False
    note_box_color: QColor = field(default_factory=lambda: QColor("#ffffff"))
    note_box_alpha: float = 1.0
    note_border_enabled: bool = False
    note_border_color: QColor = field(default_factory=lambda: QColor("#333333"))
    note_border_width: float = 1.0
    note_padding: float = 6.0


TEXT_STYLE_ATTRS = (
    "text_font_family",
    "text_font_size",
    "text_font_weight",
    "text_italic",
    "text_color",
    "text_alignment",
    "text_line_spacing",
    "note_box_enabled",
    "note_box_color",
    "note_box_alpha",
    "note_border_enabled",
    "note_border_color",
    "note_border_width",
    "note_padding",
)


def text_style_state_for(canvas: Any) -> CanvasTextStyleState:
    state = canvas_state_object(canvas, "text_style_state")
    if state is not None:
        return state
    state = CanvasTextStyleState()
    canvas.text_style_state = state
    return state


def set_text_style_for(canvas: Any, name: str, value: Any) -> None:
    state = text_style_state_for(canvas)
    setattr(state, name, value)


__all__ = [
    "CanvasTextStyleState",
    "set_text_style_for",
    "text_style_state_for",
]
