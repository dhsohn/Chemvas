from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from chemvas.domain.document import TSBracket


@dataclass(slots=True, kw_only=True)
class CanvasTSBracketState:
    """Every TS bracket of the open document as Qt-free data, keyed by a runtime id.

    A bracket's graphics item carries the id; the record says what the bracket
    is. A record stays while the scene, history or an active savepoint retains
    its item; finalization removes it when the item is released. Opening another
    document clears the store. Ids come from ``new_scene_record_id`` and are
    never reused; the counter lives outside this rolled-back state. The store
    is therefore a lookup, never a list of the document's brackets: which
    brackets the document has, and in what order, is the attached bracket items.
    """

    records: dict[int, TSBracket] = field(default_factory=dict)


def ts_bracket_state_for(canvas: Any) -> CanvasTSBracketState:
    return cast("CanvasTSBracketState", canvas.runtime_state.ts_bracket_state)


__all__ = ["CanvasTSBracketState", "ts_bracket_state_for"]
