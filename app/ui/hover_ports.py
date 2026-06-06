from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def hover_scene_service_for_access(canvas):
    return canvas_services_for(canvas).hover_scene_service


def mark_hover_preview_service_for_access(canvas):
    return canvas_services_for(canvas).mark_hover_preview_service


def bond_hover_preview_service_for_access(canvas):
    return canvas_services_for(canvas).bond_hover_preview_service


def hover_interaction_service_for_access(canvas):
    return canvas_services_for(canvas).hover_interaction_service


__all__ = [
    "bond_hover_preview_service_for_access",
    "hover_interaction_service_for_access",
    "hover_scene_service_for_access",
    "mark_hover_preview_service_for_access",
]
