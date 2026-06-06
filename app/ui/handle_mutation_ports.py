from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def handle_mutation_service_for_access(canvas):
    return canvas_services_for(canvas).handle_mutation_service


def curved_arrow_path_service_for_access(canvas):
    return canvas_services_for(canvas).curved_arrow_path_service


__all__ = [
    "curved_arrow_path_service_for_access",
    "handle_mutation_service_for_access",
]
