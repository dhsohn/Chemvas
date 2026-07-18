from __future__ import annotations

from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_service_access import canvas_services_for


def _optional_canvas_services(canvas) -> CanvasRuntimeServices | None:
    try:
        return canvas_services_for(canvas)
    except AttributeError:
        return None


def input_controller_for_view(canvas):
    services = _optional_canvas_services(canvas)
    return services.input.input_controller if services is not None else None


def pointer_controller_for_view(canvas):
    services = _optional_canvas_services(canvas)
    return services.input.pointer_controller if services is not None else None


def scene_pos_from_event_for_view(canvas, event):
    return canvas.mapToScene(event.position().toPoint())


__all__ = [
    "input_controller_for_view",
    "pointer_controller_for_view",
    "scene_pos_from_event_for_view",
]
