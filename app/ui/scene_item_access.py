from __future__ import annotations


def scene_item_controller(canvas):
    return getattr(canvas, "_scene_item_controller", None)


def restore_ring_from_state(canvas, ring_state: dict):
    controller = scene_item_controller(canvas)
    if controller is not None:
        return controller._restore_ring_from_state(ring_state)
    return canvas._restore_ring_from_state(ring_state)


def restore_note_from_state(canvas, note_state: dict):
    controller = scene_item_controller(canvas)
    if controller is not None:
        return controller._restore_note_from_state(note_state)
    return canvas._restore_note_from_state(note_state)


def restore_mark_from_state(canvas, mark_state: dict) -> None:
    controller = scene_item_controller(canvas)
    if controller is not None:
        controller._restore_mark_from_state(mark_state)
        return
    canvas._restore_mark_from_state(mark_state)


def restore_arrow_from_state(canvas, arrow_state: dict):
    controller = scene_item_controller(canvas)
    if controller is not None:
        return controller._restore_arrow_from_state(arrow_state)
    return canvas._restore_arrow_from_state(arrow_state)


def restore_ts_bracket_from_state(canvas, ts_bracket_state: dict):
    controller = scene_item_controller(canvas)
    if controller is not None:
        return controller._restore_ts_bracket_from_state(ts_bracket_state)
    return canvas._restore_ts_bracket_from_state(ts_bracket_state)


def restore_orbital_from_state(canvas, orbital_state: dict):
    controller = scene_item_controller(canvas)
    if controller is not None:
        return controller._restore_orbital_from_state(orbital_state)
    return canvas._restore_orbital_from_state(orbital_state)


def apply_scene_item_state(canvas, item, state: dict) -> None:
    controller = scene_item_controller(canvas)
    if controller is not None:
        controller.apply_scene_item_state(item, state)
        return
    canvas.apply_scene_item_state(item, state)


def create_scene_item_from_state(canvas, state: dict):
    controller = scene_item_controller(canvas)
    if controller is not None:
        return controller.create_scene_item_from_state(state)
    return canvas.create_scene_item_from_state(state)


def restore_scene_item(canvas, item) -> None:
    controller = scene_item_controller(canvas)
    if controller is not None:
        controller.restore_scene_item(item)
        return
    canvas.restore_scene_item(item)


def remove_scene_item(canvas, item) -> None:
    controller = scene_item_controller(canvas)
    if controller is not None:
        controller.remove_scene_item(item)
        return
    canvas.remove_scene_item(item)


__all__ = [
    "apply_scene_item_state",
    "create_scene_item_from_state",
    "remove_scene_item",
    "restore_arrow_from_state",
    "restore_mark_from_state",
    "restore_note_from_state",
    "restore_orbital_from_state",
    "restore_ring_from_state",
    "restore_scene_item",
    "restore_ts_bracket_from_state",
    "scene_item_controller",
]
