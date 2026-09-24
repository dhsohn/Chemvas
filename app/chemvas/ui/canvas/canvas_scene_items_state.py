from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakValueDictionary

from PyQt6 import sip

if TYPE_CHECKING:
    from chemvas.domain.document import AnnotationCollection
    from chemvas.ui.scene.scene_render_context import SceneRenderState


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


def scene_items_state_for(canvas: Any) -> CanvasSceneItemsState:
    return cast("CanvasSceneItemsState", canvas.runtime_state.scene_items_state)


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


def document_collection_for(
    state: SceneRenderState, name: str
) -> AnnotationCollection[Any]:
    return cast(
        "AnnotationCollection[Any]", getattr(state, DOCUMENT_COLLECTION_STATES[name])
    )


def items_in_document_order(state: SceneRenderState, name: str) -> list[Any]:
    """Missing-view slots preserve indices in saved arrays and group references."""
    views = getattr(state.scene_items_state, name)
    return [
        views.get(record_id) for record_id in document_collection_for(state, name).order
    ]


def scene_item_collection_for(canvas: Any, name: str) -> list[Any]:
    return items_in_document_order(canvas.runtime_state, name)


def require_scene_record_id(item: Any) -> int:
    record_id = item.data(3)
    if type(record_id) is not int:
        raise RuntimeError("annotation item attached without a record")
    return record_id


def append_scene_item_for(canvas: Any, name: str, item: Any) -> None:
    record_id = require_scene_record_id(item)
    document_collection_for(canvas.runtime_state, name).add(record_id)
    getattr(scene_items_state_for(canvas), name)[record_id] = item
    scene_items_state_for(canvas).projections[record_id] = item


def remove_scene_item_from_collection_for(canvas: Any, name: str, item: Any) -> bool:
    record_id = item.data(3)
    if type(record_id) is not int:
        return False
    removed = document_collection_for(canvas.runtime_state, name).remove(record_id)
    getattr(scene_items_state_for(canvas), name).pop(record_id, None)
    return removed


def clear_scene_item_collections_for(canvas: Any) -> None:
    state = scene_items_state_for(canvas)
    for name in SCENE_ITEM_COLLECTION_ATTRS:
        document_collection_for(canvas.runtime_state, name).clear()
        setattr(state, name, {})


def restore_scene_item_order_for(
    canvas: Any, name: str, entries: list[tuple[int, Any]]
) -> None:
    document = document_collection_for(canvas.runtime_state, name)
    order = list(document.order)
    ids = [(index, require_scene_record_id(item)) for index, item in entries]
    for _, record_id in ids:
        order.remove(record_id)
    for index, record_id in ids:
        order.insert(index, record_id)
    document.reorder(order)


def note_items_for(canvas: Any) -> list[Any]:
    return [
        item
        for item in scene_item_collection_for(canvas, "note_items")
        if item is not None
    ]


def image_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "image_items")


def ring_items_for(canvas: Any) -> list[Any]:
    return [
        item
        for item in scene_item_collection_for(canvas, "ring_items")
        if item is not None and not _ring_item_is_deleted(item)
    ]


def _ring_item_is_deleted(item: Any) -> bool:
    try:
        return sip.isdeleted(item)
    except TypeError:
        return False


def ring_items_for_atoms(canvas: Any, atom_ids: set[int]) -> list[Any]:
    """Ring items whose atom-id payload intersects ``atom_ids``.

    Skips sip-deleted wrappers so gesture-scoped discovery survives Qt
    teardown of individual rings.
    """

    affected: list[Any] = []
    for ring in ring_items_for(canvas):
        if _ring_item_is_deleted(ring):
            continue
        ring_atom_ids = ring.data(2)
        if isinstance(ring_atom_ids, list) and not atom_ids.isdisjoint(ring_atom_ids):
            affected.append(ring)
    return affected


def mark_items_for(canvas: Any) -> list[Any]:
    return [
        item
        for item in scene_item_collection_for(canvas, "mark_items")
        if item is not None
    ]


def arrow_items_for(canvas: Any) -> list[Any]:
    return [
        item
        for item in scene_item_collection_for(canvas, "arrow_items")
        if item is not None
    ]


def ts_bracket_items_for(canvas: Any) -> list[Any]:
    return [
        item
        for item in scene_item_collection_for(canvas, "ts_bracket_items")
        if item is not None
    ]


def shape_items_for(canvas: Any) -> list[Any]:
    return [
        item
        for item in scene_item_collection_for(canvas, "shape_items")
        if item is not None
    ]


def orbital_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "orbital_items")


__all__ = [
    "DOCUMENT_COLLECTION_STATES",
    "SCENE_ITEM_COLLECTION_ATTRS",
    "CanvasSceneItemsState",
    "append_scene_item_for",
    "arrow_items_for",
    "clear_scene_item_collections_for",
    "document_collection_for",
    "image_items_for",
    "items_in_document_order",
    "mark_items_for",
    "note_items_for",
    "orbital_items_for",
    "remove_scene_item_from_collection_for",
    "require_scene_record_id",
    "restore_scene_item_order_for",
    "ring_items_for",
    "scene_item_collection_for",
    "scene_items_state_for",
    "shape_items_for",
    "ts_bracket_items_for",
]
