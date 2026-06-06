from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def ring_fill_scene_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_ring_fill_scene_service


__all__ = ["ring_fill_scene_service_for_access"]
