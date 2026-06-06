from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def scene_decoration_service_for_access(canvas):
    return canvas_services_for(canvas).scene_decoration_service


def scene_decoration_build_service_for_access(canvas):
    return canvas_services_for(canvas).scene_decoration_build_service


def mark_scene_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_mark_scene_service


__all__ = [
    "mark_scene_service_for_access",
    "scene_decoration_build_service_for_access",
    "scene_decoration_service_for_access",
]
