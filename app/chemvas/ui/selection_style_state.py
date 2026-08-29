from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from PyQt6.QtGui import QColor


@dataclass(slots=True)
class SelectionStyleState:
    selected_items: list = field(default_factory=list)
    color: QColor = field(default_factory=lambda: QColor("#0d9488"))
    stroke_delta: float = 0.6
    suspend_outline: bool = False


def selection_style_state_for(canvas: Any) -> SelectionStyleState:
    return cast("SelectionStyleState", canvas.runtime_state.selection_style_state)


__all__ = [
    "SelectionStyleState",
    "selection_style_state_for",
]
