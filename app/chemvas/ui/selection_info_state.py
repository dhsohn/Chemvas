from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

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
    return cast(SelectionInfoState, canvas.runtime_state.selection_info_state)


__all__ = [
    "SelectionInfoState",
    "SelectionSignature",
    "selection_info_state_for",
]
