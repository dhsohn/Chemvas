from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

# Selected ids plus the content the formula readout actually consumes
# (elements, bond orders, mark-derived annotations): editing a selected
# atom's marks or labels must miss this cache even though the id sets are
# unchanged.
SelectionSignature = tuple[
    frozenset[int],
    frozenset[int],
    tuple[tuple[int, str], ...],
    tuple[tuple[int, int, int], ...],
    tuple[tuple[int, tuple[tuple[str, int], ...]], ...],
]
PendingSelectionSignature = tuple[frozenset[int], frozenset[int]]


@dataclass(slots=True)
class SelectionInfoState:
    callback: Callable[[str, str], None] | None = None
    signature: SelectionSignature | None = None
    pending_signature: PendingSelectionSignature | None = None
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
    "PendingSelectionSignature",
    "SelectionInfoState",
    "SelectionSignature",
    "selection_info_state_for",
]
