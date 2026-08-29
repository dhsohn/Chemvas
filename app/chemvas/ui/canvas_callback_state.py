from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class CanvasCallbackState:
    tool_change: Callable[[], None] | None = None
    error: Callable[[str], None] | None = None
    zoom: Callable[..., None] | None = None
    scene_selection_group: Callable[[], None] | None = None
    scene_selection_outline: Callable[[], None] | None = None


def callback_state_for(canvas) -> CanvasCallbackState:
    return cast("CanvasCallbackState", canvas.runtime_state.callback_state)


__all__ = ["CanvasCallbackState", "callback_state_for"]
