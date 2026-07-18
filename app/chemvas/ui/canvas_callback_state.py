from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasCallbackState:
    tool_change: Callable[[], None] | None = None
    error: Callable[[str], None] | None = None
    zoom: Callable[..., None] | None = None
    scene_selection_group: Callable[[], None] | None = None
    scene_selection_outline: Callable[[], None] | None = None


def callback_state_for(canvas: Any) -> CanvasCallbackState:
    return ensure_canvas_state(canvas, "callback_state", CanvasCallbackState)


__all__ = ["CanvasCallbackState", "callback_state_for"]
