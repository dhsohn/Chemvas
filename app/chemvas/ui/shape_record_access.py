"""Keep the shape store in step with the graphics items that still own shapes.

Until reads move to the store, the item is the source of truth and the record is
derived from it. Every site that changes what a shape is calls
``sync_shape_record_for`` afterwards, so the store never lags an edit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6 import sip

from chemvas.domain.document import normalized_shape, shape_from_state
from chemvas.ui.canvas_shape_state import shape_state_for
from chemvas.ui.scene_item_state_serialization import shape_state_dict

if TYPE_CHECKING:
    from chemvas.domain.document import Shape

# Roles 0-2 carry an item's kind and payloads; the shape id has its own.
SHAPE_ID_ROLE = 3


def _is_deleted(item: Any) -> bool:
    try:
        return sip.isdeleted(item)
    except TypeError:
        # Not a Qt wrapper at all; nothing Qt could have destroyed.
        return False


def shape_id_for_item(item: Any) -> int | None:
    shape_id = item.data(SHAPE_ID_ROLE)
    return shape_id if type(shape_id) is int else None


def shape_record_for(canvas: Any, item: Any) -> Shape | None:
    shape_id = shape_id_for_item(item)
    if shape_id is None:
        return None
    return shape_state_for(canvas).records.get(shape_id)


def sync_shape_record_for(canvas: Any, item: Any) -> None:
    if item is None or _is_deleted(item) or item.data(0) != "shape":
        return
    state = shape_state_for(canvas)
    shape_id = shape_id_for_item(item)
    if shape_id is None:
        shape_id = state.next_shape_id
        state.next_shape_id += 1
        item.setData(SHAPE_ID_ROLE, shape_id)
    try:
        record = normalized_shape(shape_from_state(shape_state_dict(item)))
    except ValueError:
        # An item whose geometry no document would accept has no record; the
        # edit itself must not fail because the mirror could not follow it.
        state.records.pop(shape_id, None)
        return
    state.records[shape_id] = record


def clear_shape_records_for(canvas: Any) -> None:
    state = shape_state_for(canvas)
    state.records = {}
    state.next_shape_id = 1


__all__ = [
    "SHAPE_ID_ROLE",
    "clear_shape_records_for",
    "shape_id_for_item",
    "shape_record_for",
    "sync_shape_record_for",
]
