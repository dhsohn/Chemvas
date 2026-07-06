from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasSceneItemsState:
    selected_notes: list[Any] = field(default_factory=list)
    ring_items: list[Any] = field(default_factory=list)
    note_items: list[Any] = field(default_factory=list)
    mark_items: list[Any] = field(default_factory=list)
    arrow_items: list[Any] = field(default_factory=list)
    ts_bracket_items: list[Any] = field(default_factory=list)
    shape_items: list[Any] = field(default_factory=list)
    orbital_items: list[Any] = field(default_factory=list)


SCENE_ITEM_COLLECTION_ATTRS = (
    "selected_notes",
    "ring_items",
    "note_items",
    "mark_items",
    "arrow_items",
    "ts_bracket_items",
    "shape_items",
    "orbital_items",
)


def scene_items_state_for(canvas: Any) -> CanvasSceneItemsState:
    return ensure_canvas_state(canvas, "scene_items_state", CanvasSceneItemsState)


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


def selected_notes_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "selected_notes")


def note_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "note_items")


def ring_items_for(canvas: Any) -> list[Any]:
    return scene_item_collection_for(canvas, "ring_items")


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


def set_selected_notes_for(canvas: Any, notes: list[Any]) -> None:
    set_scene_item_collection_for(canvas, "selected_notes", notes)


def add_selected_note_for(canvas: Any, note: Any) -> None:
    append_scene_item_for(canvas, "selected_notes", note)


def remove_selected_note_for(canvas: Any, note: Any) -> bool:
    return remove_scene_item_from_collection_for(canvas, "selected_notes", note)


def clear_selected_notes_for(canvas: Any) -> None:
    set_selected_notes_for(canvas, [])


__all__ = [
    "SCENE_ITEM_COLLECTION_ATTRS",
    "CanvasSceneItemsState",
    "add_selected_note_for",
    "append_scene_item_for",
    "arrow_items_for",
    "clear_scene_item_collections_for",
    "clear_selected_notes_for",
    "mark_items_for",
    "note_items_for",
    "orbital_items_for",
    "remove_scene_item_from_collection_for",
    "remove_selected_note_for",
    "ring_items_for",
    "scene_item_collection_for",
    "scene_items_state_for",
    "selected_notes_for",
    "set_scene_item_collection_for",
    "set_selected_notes_for",
    "shape_items_for",
    "ts_bracket_items_for",
]
