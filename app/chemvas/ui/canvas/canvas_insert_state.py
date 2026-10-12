from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, kw_only=True)
class CanvasInsertState:
    template_active: bool = False
    template_ring_size: int | None = None
    template_ring_style: str | None = None
    template_preview_items: list[Any] = field(default_factory=list)
    template_preview_lines: list[Any] = field(default_factory=list)
    template_preview_dots: list[Any] = field(default_factory=list)


__all__ = ["CanvasInsertState"]
