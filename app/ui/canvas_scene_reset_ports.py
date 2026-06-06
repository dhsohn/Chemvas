from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def scene_reset_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_scene_reset_service


__all__ = ["scene_reset_service_for_access"]
