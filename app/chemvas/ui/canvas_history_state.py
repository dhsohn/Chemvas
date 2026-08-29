from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.core.history import HistoryCommand


@dataclass
class CanvasHistoryState:
    history: list[HistoryCommand] = field(default_factory=list)
    redo_stack: list[HistoryCommand] = field(default_factory=list)
    enabled: bool = True
    limit: int = 100
    change_callback: Callable[[], None] | None = None


def history_state_for(canvas: Any) -> CanvasHistoryState:
    return cast("CanvasHistoryState", canvas.runtime_state.history_state)


__all__ = ["CanvasHistoryState", "history_state_for"]
