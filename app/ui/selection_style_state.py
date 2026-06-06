from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtGui import QColor

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class SelectionStyleState:
    selected_items: list = field(default_factory=list)
    color: QColor = field(default_factory=lambda: QColor("#0d9488"))
    stroke_delta: float = 0.6
    suspend_outline: bool = False


def selection_style_state_for(canvas: Any) -> SelectionStyleState:
    state = canvas_state_object(canvas, "selection_style_state")
    if state is not None:
        return state
    state = SelectionStyleState()
    canvas.selection_style_state = state
    return state


__all__ = [
    "SelectionStyleState",
    "selection_style_state_for",
]
