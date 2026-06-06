from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def insert_controller_for_access(canvas):
    return canvas_services_for(canvas).insert_controller


__all__ = ["insert_controller_for_access"]
