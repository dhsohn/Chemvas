from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def move_controller_for_access(canvas):
    return canvas_services_for(canvas).move_controller


__all__ = ["move_controller_for_access"]
