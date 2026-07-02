from __future__ import annotations

from ui.canvas_scene_state import canvas_scene_for, optional_canvas_scene_for
from ui.scene_item_ports import scene_item_controller_for_access


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


def remove_scene_items(scene, items) -> None:
    for item in items:
        scene.removeItem(item)


def add_item_to_canvas_scene(canvas, item):
    canvas_scene_for(canvas).addItem(item)
    return item


def item_can_be_added_to_canvas_scene(canvas, item) -> bool:
    if item is None:
        return False
    scene = optional_canvas_scene_for(canvas)
    if scene is None:
        return False
    scene_method = getattr(item, "scene", None)
    if not callable(scene_method):
        return True
    try:
        return scene_method() is not scene
    except RuntimeError:
        return False


def clear_canvas_scene(canvas) -> None:
    canvas_scene_for(canvas).clear()


def item_is_in_canvas_scene(canvas, item) -> bool:
    if item is None:
        return False
    scene = optional_canvas_scene_for(canvas)
    if scene is None:
        return False
    try:
        return item.scene() is scene
    except RuntimeError:
        return False


def remove_item_from_canvas_scene(canvas, item) -> bool:
    if item is None:
        return False
    scene = optional_canvas_scene_for(canvas)
    if scene is None:
        return False
    item_scene = None
    scene_method = getattr(item, "scene", None)
    if callable(scene_method):
        try:
            item_scene = scene_method()
        except RuntimeError:
            return False
        if item_scene is not scene:
            return False
    scene.removeItem(item)
    return True


def remove_attached_item_from_canvas_scene(canvas, item) -> bool | None:
    if item is None:
        return False
    scene = optional_canvas_scene_for(canvas)
    if scene is None:
        return None
    scene_method = getattr(item, "scene", None)
    if callable(scene_method):
        try:
            if scene_method() is not scene:
                return False
        except RuntimeError:
            return None
    scene.removeItem(item)
    return True


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


def create_scene_item_group(canvas, items):
    return canvas_scene_for(canvas).createItemGroup(items)


def destroy_scene_item_group(canvas, group) -> None:
    canvas_scene_for(canvas).destroyItemGroup(group)


def clear_scene_item_map(scene, item_map: dict) -> dict:
    remove_scene_items(scene, item_map.values())
    return {}


def clear_scene_item_list_map(scene, item_map: dict) -> dict:
    for items in item_map.values():
        remove_scene_items(scene, items)
    return {}


def clear_canvas_scene_item_map(canvas, item_map: dict) -> dict:
    return clear_scene_item_map(canvas_scene_for(canvas), item_map)


def clear_canvas_scene_item_list_map(canvas, item_map: dict) -> dict:
    return clear_scene_item_list_map(canvas_scene_for(canvas), item_map)


__all__ = [
    "add_item_to_canvas_scene",
    "apply_scene_item_state",
    "attach_scene_item",
    "attached_canvas_scene_items",
    "bond_ids_for_ring_item",
    "canvas_scene_for",
    "clear_canvas_scene",
    "clear_canvas_scene_item_list_map",
    "clear_canvas_scene_item_map",
    "clear_scene_item_list_map",
    "clear_scene_item_map",
    "create_scene_item_from_state",
    "create_scene_item_group",
    "destroy_scene_item_group",
    "item_can_be_added_to_canvas_scene",
    "item_is_in_canvas_scene",
    "refresh_bond_geometry_for_ring_item",
    "remove_attached_item_from_canvas_scene",
    "remove_item_from_canvas_scene",
    "remove_items_from_canvas_scene",
    "remove_scene_item",
    "remove_scene_items",
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
