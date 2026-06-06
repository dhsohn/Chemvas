from __future__ import annotations

from ui.hover_ports import hover_scene_service_for_access


def _hover_scene_method(canvas, name: str):
    try:
        service = hover_scene_service_for_access(canvas)
    except AttributeError:
        service = None
    method = getattr(service, name, None)
    return method if callable(method) else None


def clear_hover_highlight_for(canvas) -> None:
    method = _hover_scene_method(canvas, "clear_hover_highlight")
    if method is not None:
        method()


def add_hover_preview_items_for(canvas, items) -> None:
    method = _hover_scene_method(canvas, "add_hover_preview_items")
    if method is not None:
        method(items)


__all__ = ["add_hover_preview_items_for", "clear_hover_highlight_for"]
