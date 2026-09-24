from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from weakref import WeakValueDictionary


@dataclass(slots=True, kw_only=True)
class CanvasSceneItemsState:
    # A cache only: detached projections live while another UI owner uses them.
    projections: WeakValueDictionary[int, Any] = field(
        default_factory=WeakValueDictionary
    )
    ring_items: dict[int, Any] = field(default_factory=dict)
    note_items: dict[int, Any] = field(default_factory=dict)
    image_items: dict[int, Any] = field(default_factory=dict)
    mark_items: dict[int, Any] = field(default_factory=dict)
    arrow_items: dict[int, Any] = field(default_factory=dict)
    ts_bracket_items: dict[int, Any] = field(default_factory=dict)
    # Projections only. Document collections own membership and order.
    shape_items: dict[int, Any] = field(default_factory=dict)
    orbital_items: dict[int, Any] = field(default_factory=dict)


SCENE_ITEM_COLLECTION_ATTRS = (
    "ring_items",
    "note_items",
    "image_items",
    "mark_items",
    "arrow_items",
    "ts_bracket_items",
    "shape_items",
    "orbital_items",
)


DOCUMENT_COLLECTION_STATES = {
    "mark_items": "mark_state",
    "note_items": "note_state",
    "ring_items": "ring_state",
    "orbital_items": "orbital_state",
    "image_items": "image_state",
    "arrow_items": "arrow_state",
    "ts_bracket_items": "ts_bracket_state",
    "shape_items": "shape_state",
}


def require_scene_record_id(item: Any) -> int:
    record_id = item.data(3)
    if type(record_id) is not int:
        raise RuntimeError("annotation item attached without a record")
    return record_id


__all__ = [
    "DOCUMENT_COLLECTION_STATES",
    "SCENE_ITEM_COLLECTION_ATTRS",
    "CanvasSceneItemsState",
    "require_scene_record_id",
]
