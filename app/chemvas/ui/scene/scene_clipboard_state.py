from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SceneClipboardState:
    paste_source_json: str | None = None
    paste_count: int = 0


__all__ = ["SceneClipboardState"]
