from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.history import HistoryCommand

from ui.canvas_state_lookup import canvas_state_object


@dataclass
class CanvasHistoryState:
    history: list[HistoryCommand] = field(default_factory=list)
    redo_stack: list[HistoryCommand] = field(default_factory=list)
    enabled: bool = True
    limit: int = 100
    change_callback: Callable[[], None] | None = None


def history_state_for(canvas: Any) -> CanvasHistoryState:
    state = canvas_state_object(canvas, "history_state")
    if state is not None:
        return state
    state = CanvasHistoryState()
    canvas.history_state = state
    return state


__all__ = ["CanvasHistoryState", "history_state_for"]
