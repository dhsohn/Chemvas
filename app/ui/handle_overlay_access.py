from __future__ import annotations

from ui.canvas_service_ports import handle_overlay_service_for_access


def clear_handles_for(canvas) -> None:
    handle_overlay_service_for_access(canvas).clear_handles()


def show_orbital_handles_for(canvas, item) -> None:
    handle_overlay_service_for_access(canvas).show_orbital_handles(item)


def show_curved_handles_for(canvas, item) -> None:
    handle_overlay_service_for_access(canvas).show_curved_handles(item)


def show_shape_handles_for(canvas, item) -> None:
    handle_overlay_service_for_access(canvas).show_shape_handles(item)


__all__ = [
    "clear_handles_for",
    "show_curved_handles_for",
    "show_orbital_handles_for",
    "show_shape_handles_for",
]
