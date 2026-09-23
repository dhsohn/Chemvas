from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from PyQt6 import sip

if TYPE_CHECKING:
    from chemvas.domain.document import Arrow


@dataclass(slots=True, kw_only=True)
class CanvasArrowState:
    # Detached items retained by history keep their records until finalization.
    records: dict[int, Arrow] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class CanvasSceneItemsState:
    ring_items: list[Any] = field(default_factory=list)
    note_items: list[Any] = field(default_factory=list)
    image_items: list[Any] = field(default_factory=list)
    mark_items: list[Any] = field(default_factory=list)
    arrow_items: list[Any] = field(default_factory=list)
    ts_bracket_items: list[Any] = field(default_factory=list)
    shape_items: list[Any] = field(default_factory=list)
    orbital_items: list[Any] = field(default_factory=list)


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


def scene_item_collection_for(canvas: Any, name: str) -> list[Any]:
    return getattr(scene_items_state_for(canvas), name)


def set_scene_item_collection_for(canvas: Any, name: str, items: list[Any]) -> None:
    state = scene_items_state_for(canvas)
    setattr(state, name, items)


def append_scene_item_for(canvas: Any, name: str, item: Any) -> None:
    items = scene_item_collection_for(canvas, name)
    if item not in items:
        items.append(item)


def remove_scene_item_from_collection_for(canvas: Any, name: str, item: Any) -> bool:
    items = scene_item_collection_for(canvas, name)
    if item not in items:
        return False
    items.remove(item)
    return True


def clear_scene_item_collections_for(canvas: Any) -> None:
    state = scene_items_state_for(canvas)
    for name in SCENE_ITEM_COLLECTION_ATTRS:
        setattr(state, name, [])


def note_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "note_items")


def image_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "image_items")


def ring_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "ring_items")


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
    return scene_item_collection_for(canvas, "mark_items")


def arrow_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "arrow_items")


def ts_bracket_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "ts_bracket_items")


def shape_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "shape_items")


def orbital_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "orbital_items")


__all__ = [
    "SCENE_ITEM_COLLECTION_ATTRS",
    "CanvasSceneItemsState",
    "append_scene_item_for",
    "arrow_items_for",
    "clear_scene_item_collections_for",
    "image_items_for",
    "mark_items_for",
    "note_items_for",
    "orbital_items_for",
    "remove_scene_item_from_collection_for",
    "ring_items_for",
    "scene_item_collection_for",
    "scene_items_state_for",
    "set_scene_item_collection_for",
    "shape_items_for",
    "ts_bracket_items_for",
]
