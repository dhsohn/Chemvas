from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def scene_item_controller_for_access(canvas):
    return canvas_services_for(canvas).scene_item_controller


__all__ = ["scene_item_controller_for_access"]
