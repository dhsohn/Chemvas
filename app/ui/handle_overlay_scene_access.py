from __future__ import annotations

from ui.handle_interaction_logic import clear_handle_items as clear_handle_items_helper
from ui.scene_item_access import add_item_to_canvas_scene, canvas_scene_for


def clear_handle_items_for_canvas(canvas, handles):
    return clear_handle_items_helper(canvas_scene_for(canvas), handles)


def add_handle_to_canvas_scene(canvas, handle):
    return add_item_to_canvas_scene(canvas, handle)


__all__ = ["add_handle_to_canvas_scene", "clear_handle_items_for_canvas"]
