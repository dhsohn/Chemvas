from __future__ import annotations

from chemvas.ui.canvas_service_access import optional_canvas_service_method
from chemvas.ui.canvas_service_ports import hover_scene_service_for_access


def _hover_scene_method(canvas, name: str):
    return optional_canvas_service_method(canvas, hover_scene_service_for_access, name)


def clear_hover_highlight_for(canvas) -> None:
    method = _hover_scene_method(canvas, "clear_hover_highlight")
    if method is not None:
        method()


def add_hover_preview_items_for(canvas, items) -> None:
    method = _hover_scene_method(canvas, "add_hover_preview_items")
    if method is not None:
        method(items)


__all__ = ["add_hover_preview_items_for", "clear_hover_highlight_for"]
