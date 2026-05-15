from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from core.history import HistoryCommand


@dataclass
class CanvasHistoryState:
    history: list[HistoryCommand] = field(default_factory=list)
    redo_stack: list[HistoryCommand] = field(default_factory=list)
    enabled: bool = True
    limit: int = 100
    change_callback: Callable[[], None] | None = None


__all__ = ["CanvasHistoryState"]
