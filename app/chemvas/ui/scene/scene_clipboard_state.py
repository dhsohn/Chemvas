from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SceneClipboardState:
    paste_source_json: str | None = None
    paste_count: int = 0

    def record_paste_source(self, source_json: str | None, count: int) -> None:
        """The payload the next paste offsets from, and how many pastes it has seen."""
        self.paste_source_json = source_json
        self.paste_count = int(count)


__all__ = ["SceneClipboardState"]
