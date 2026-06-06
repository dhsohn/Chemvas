from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def handle_overlay_service_for_access(canvas):
    return canvas_services_for(canvas).handle_overlay_service


__all__ = ["handle_overlay_service_for_access"]
