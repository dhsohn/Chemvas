from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class CanvasCallbackState:
    tool_change: Callable[[], None] | None = None
    error: Callable[[str], None] | None = None
    zoom: Callable[..., None] | None = None


def callback_state_for(canvas: Any) -> CanvasCallbackState:
    state = canvas_state_object(canvas, "callback_state")
    if state is not None:
        return state
    state = CanvasCallbackState()
    canvas.callback_state = state
    return state


__all__ = ["CanvasCallbackState", "callback_state_for"]
