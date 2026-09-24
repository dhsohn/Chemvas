from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class CanvasCallbackState:
    tool_change: Callable[[], None] | None = None
    error: Callable[[str], None] | None = None
    zoom: Callable[..., None] | None = None
    document_change: Callable[..., None] | None = None
    scene_selection_group: Callable[[], None] | None = None
    scene_selection_outline: Callable[[], None] | None = None


def run_scene_selection_group_callback_for(canvas) -> None:
    callback = canvas.runtime_state.callback_state.scene_selection_group
    if callback is not None:
        callback()


def run_scene_selection_outline_callback_for(canvas) -> None:
    callback = canvas.runtime_state.callback_state.scene_selection_outline
    if callback is not None:
        callback()


__all__ = [
    "CanvasCallbackState",
    "run_scene_selection_group_callback_for",
    "run_scene_selection_outline_callback_for",
]
