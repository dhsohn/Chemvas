from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from chemvas.domain.document import Shape


@dataclass(slots=True, kw_only=True)
class CanvasShapeState:
    """Every shape of the open document as Qt-free data, keyed by a runtime id.

    A shape's graphics item carries the id; the record says what the shape is.
    A record stays while the scene, history or an active savepoint retains its
    item; finalization removes it when the item is released. Opening another
    document clears the store. Ids come from ``new_scene_record_id`` and are
    never reused; the counter lives outside this rolled-back state. The store
    is therefore a lookup, never a list of the document's shapes: which shapes
    the document has, and in what order, is the attached shape items.
    """

    records: dict[int, Shape] = field(default_factory=dict)


def shape_state_for(canvas: Any) -> CanvasShapeState:
    return cast("CanvasShapeState", canvas.runtime_state.shape_state)


__all__ = ["CanvasShapeState", "shape_state_for"]
