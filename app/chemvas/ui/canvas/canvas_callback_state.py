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

    def set_window_callbacks(
        self,
        *,
        error: Callable[[str], None] | None,
        tool_change: Callable[[], None] | None,
        zoom: Callable[..., None] | None,
    ) -> None:
        """The three callbacks a window binds to its active canvas, as one step."""
        self.error = error
        self.tool_change = tool_change
        self.zoom = zoom


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
