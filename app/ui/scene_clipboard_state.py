from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class SceneClipboardState:
    paste_source_json: str | None = None
    paste_count: int = 0


def scene_clipboard_state_for(canvas: Any) -> SceneClipboardState:
    state = canvas_state_object(canvas, "scene_clipboard_state")
    if state is not None:
        return state
    state = SceneClipboardState()
    canvas.scene_clipboard_state = state
    return state


__all__ = ["SceneClipboardState", "scene_clipboard_state_for"]
