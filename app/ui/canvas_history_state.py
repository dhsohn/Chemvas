from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.history import HistoryCommand


@dataclass
class CanvasHistoryState:
    history: list[HistoryCommand] = field(default_factory=list)
    redo_stack: list[HistoryCommand] = field(default_factory=list)
    enabled: bool = True
    limit: int = 100
    change_callback: Callable[[], None] | None = None


class CanvasHistoryStateAdapter:
    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas

    def _ensure(self, name: str, default):
        if not hasattr(self._canvas, name):
            setattr(self._canvas, name, default() if callable(default) else default)
        return getattr(self._canvas, name)

    @property
    def history(self) -> list[HistoryCommand]:
        return self._ensure("_history", list)

    @history.setter
    def history(self, value: list[HistoryCommand]) -> None:
        self._canvas._history = value

    @property
    def redo_stack(self) -> list[HistoryCommand]:
        return self._ensure("_redo_stack", list)

    @redo_stack.setter
    def redo_stack(self, value: list[HistoryCommand]) -> None:
        self._canvas._redo_stack = value

    @property
    def enabled(self) -> bool:
        return self._ensure("_history_enabled", True)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._canvas._history_enabled = value

    @property
    def limit(self) -> int:
        return self._ensure("_history_limit", 100)

    @limit.setter
    def limit(self, value: int) -> None:
        self._canvas._history_limit = value

    @property
    def change_callback(self) -> Callable[[], None] | None:
        return self._ensure("_history_change_callback", None)

    @change_callback.setter
    def change_callback(self, value: Callable[[], None] | None) -> None:
        self._canvas._history_change_callback = value


def history_state_for(canvas: Any) -> CanvasHistoryState | CanvasHistoryStateAdapter:
    state = getattr(canvas, "_history_state", None)
    if state is not None:
        return state
    return CanvasHistoryStateAdapter(canvas)


__all__ = ["CanvasHistoryState", "CanvasHistoryStateAdapter", "history_state_for"]
