from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont


@dataclass(slots=True, kw_only=True)
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


def text_style_state_for(canvas: Any) -> CanvasTextStyleState:
    return cast("CanvasTextStyleState", canvas.runtime_state.text_style_state)


def set_text_style_for(canvas: Any, name: str, value: Any) -> None:
    state = text_style_state_for(canvas)
    setattr(state, name, value)


__all__ = [
    "CanvasTextStyleState",
    "set_text_style_for",
    "text_style_state_for",
]
