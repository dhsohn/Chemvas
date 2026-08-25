from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.ui.canvas_scene_state import canvas_scene_for, optional_canvas_scene_for
from chemvas.ui.canvas_service_ports import scene_item_controller_for_access


def scene_item_controller(canvas):
    return scene_item_controller_for_access(canvas)


def restore_ring_from_state(canvas, ring_state: dict):
    return scene_item_controller(canvas).restore_ring_from_state(ring_state)


def restore_note_from_state(canvas, note_state: dict):
    return scene_item_controller(canvas).restore_note_from_state(note_state)


def restore_mark_from_state(canvas, mark_state: dict):
    return scene_item_controller(canvas).restore_mark_from_state(mark_state)


def restore_arrow_from_state(canvas, arrow_state: dict):
    return scene_item_controller(canvas).restore_arrow_from_state(arrow_state)


def restore_ts_bracket_from_state(canvas, ts_bracket_state: dict):
    return scene_item_controller(canvas).restore_ts_bracket_from_state(ts_bracket_state)


def restore_shape_from_state(canvas, shape_state: dict):
    return scene_item_controller(canvas).restore_shape_from_state(shape_state)


def restore_orbital_from_state(canvas, orbital_state: dict):
    return scene_item_controller(canvas).restore_orbital_from_state(orbital_state)


def bond_ids_for_ring_item(canvas, item) -> set[int]:
    return scene_item_controller(canvas).bond_ids_for_ring_item(item)


def refresh_bond_geometry_for_ring_item(canvas, item) -> None:
    scene_item_controller(canvas).refresh_bond_geometry_for_ring_item(item)


def apply_scene_item_state(canvas, item, state: dict) -> None:
    scene_item_controller(canvas).apply_scene_item_state(item, state)


def create_scene_item_from_state(canvas, state: dict):
    return scene_item_controller(canvas).create_scene_item_from_state(state)


def attach_scene_item(canvas, item) -> None:
    scene_item_controller(canvas).attach_scene_item(item)


def restore_scene_item(canvas, item) -> None:
    scene_item_controller(canvas).restore_scene_item(item)


def remove_scene_item(canvas, item) -> None:
    scene_item_controller(canvas).remove_scene_item(item)


def add_item_to_canvas_scene(canvas, item):
    canvas_scene_for(canvas).addItem(item)
    return item


def canvas_scene_for_item_operation(canvas):
    if isinstance(canvas, QObject) and sip.isdeleted(canvas):
        return None
    try:
        return canvas_scene_for(canvas)
    except RuntimeError:
        if isinstance(canvas, QObject) and sip.isdeleted(canvas):
            return None
        raise


def item_is_unavailable_for_scene_operation(item) -> bool:
    return item is None or (isinstance(item, QGraphicsItem) and sip.isdeleted(item))


def item_is_in_scene(scene, item) -> bool:
    if item_is_unavailable_for_scene_operation(item):
        return False
    if scene is None:
        return False
    scene_method = getattr(item, "scene", None)
    if not callable(scene_method):
        return False
    try:
        return scene_method() is scene
    except RuntimeError:
        if isinstance(item, QGraphicsItem) and sip.isdeleted(item):
            return False
        raise


def item_is_in_canvas_scene(canvas, item) -> bool:
    if item_is_unavailable_for_scene_operation(item):
        return False
    return item_is_in_scene(
        canvas_scene_for_item_operation(canvas),
        item,
    )


def _detach_item_from_canvas_scene(
    canvas, item, *, unresolved: bool | None
) -> bool | None:
    """Detach ``item`` from the canvas scene, tolerating a deleted C++ object.

    ``unresolved`` is the answer for "cannot tell": either the canvas has no
    scene to detach from, or the item's own C++ object is already gone, so
    whether it was ever attached here is unknowable. The two wrappers below
    differ in nothing else.
    """

    if item is None:
        return False
    scene = optional_canvas_scene_for(canvas)
    if scene is None:
        return unresolved
    scene_method = getattr(item, "scene", None)
    if callable(scene_method):
        try:
            if scene_method() is not scene:
                return False
        except RuntimeError:
            return unresolved
    scene.removeItem(item)
    return True


def remove_item_from_canvas_scene(canvas, item) -> bool:
    """Detach if attached here. "Cannot tell" is reported as not detached."""

    return _detach_item_from_canvas_scene(canvas, item, unresolved=False) is True


def remove_attached_item_from_canvas_scene(canvas, item) -> bool | None:
    """Detach if attached here, answering ``None`` when that is unknowable.

    The third answer is load-bearing at exactly one caller:
    ``SceneItemLifecycleService.remove_scene_item`` treats ``None`` as "stop"
    and ``False`` as "carry on". A ``False`` item was provably never in this
    scene, so the ring-fill bond geometry can safely be refreshed against it; a
    ``None`` item may have been, and reading it would raise. Do not collapse
    this to ``bool``.
    """

    return _detach_item_from_canvas_scene(canvas, item, unresolved=None)


def remove_items_from_canvas_scene(canvas, items) -> None:
    for item in list(items):
        remove_item_from_canvas_scene(canvas, item)


def attached_canvas_scene_items(canvas, items) -> list:
    scene = optional_canvas_scene_for(canvas)
    if scene is None:
        return []
    attached_items = []
    for item in items:
        try:
            if item.scene() is not scene:
                continue
        except RuntimeError:
            continue
        attached_items.append(item)
    return attached_items


__all__ = [
    "add_item_to_canvas_scene",
    "apply_scene_item_state",
    "attach_scene_item",
    "attached_canvas_scene_items",
    "bond_ids_for_ring_item",
    "canvas_scene_for",
    "canvas_scene_for_item_operation",
    "create_scene_item_from_state",
    "item_is_in_canvas_scene",
    "item_is_in_scene",
    "item_is_unavailable_for_scene_operation",
    "refresh_bond_geometry_for_ring_item",
    "remove_attached_item_from_canvas_scene",
    "remove_item_from_canvas_scene",
    "remove_items_from_canvas_scene",
    "remove_scene_item",
    "restore_arrow_from_state",
    "restore_mark_from_state",
    "restore_note_from_state",
    "restore_orbital_from_state",
    "restore_ring_from_state",
    "restore_scene_item",
    "restore_shape_from_state",
    "restore_ts_bracket_from_state",
    "scene_item_controller",
]
