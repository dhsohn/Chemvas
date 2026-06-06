from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def geometry_controller_for_access(canvas):
    return canvas_services_for(canvas).geometry_controller


__all__ = ["geometry_controller_for_access"]
