from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from ui.canvas_state_lookup import canvas_state_object

SelectionSignature = tuple[frozenset[int], frozenset[int]]


@dataclass(slots=True)
class SelectionInfoState:
    callback: Callable[[str, str], None] | None = None
    signature: SelectionSignature | None = None
    pending_signature: SelectionSignature | None = None
    cache: tuple[str, str] = ("", "")
    rdkit_warmup_pending: bool = False
    rdkit_idle_threshold: float = 0.4
    last_interaction_time: float = 0.0

    @classmethod
    def create(cls) -> SelectionInfoState:
        return cls(last_interaction_time=time.monotonic())


def selection_info_state_for(canvas: Any) -> SelectionInfoState:
    state = canvas_state_object(canvas, "selection_info_state")
    if state is not None:
        return state
    state = SelectionInfoState.create()
    canvas.selection_info_state = state
    return state


__all__ = [
    "SelectionInfoState",
    "SelectionSignature",
    "selection_info_state_for",
]
