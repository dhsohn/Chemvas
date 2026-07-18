from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class SceneClipboardState:
    paste_source_json: str | None = None
    paste_count: int = 0


def scene_clipboard_state_for(canvas: Any) -> SceneClipboardState:
    return ensure_canvas_state(canvas, "scene_clipboard_state", SceneClipboardState)


__all__ = ["SceneClipboardState", "scene_clipboard_state_for"]
