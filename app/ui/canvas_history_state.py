from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.history import HistoryCommand

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass
class CanvasHistoryState:
    history: list[HistoryCommand] = field(default_factory=list)
    redo_stack: list[HistoryCommand] = field(default_factory=list)
    enabled: bool = True
    limit: int = 100
    change_callback: Callable[[], None] | None = None


def history_state_for(canvas: Any) -> CanvasHistoryState:
    return ensure_canvas_state(canvas, "history_state", CanvasHistoryState)


__all__ = ["CanvasHistoryState", "history_state_for"]
