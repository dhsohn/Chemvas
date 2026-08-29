from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast


@dataclass(slots=True)
class SceneClipboardState:
    paste_source_json: str | None = None
    paste_count: int = 0


def scene_clipboard_state_for(canvas: Any) -> SceneClipboardState:
    return cast("SceneClipboardState", canvas.runtime_state.scene_clipboard_state)


__all__ = ["SceneClipboardState", "scene_clipboard_state_for"]
