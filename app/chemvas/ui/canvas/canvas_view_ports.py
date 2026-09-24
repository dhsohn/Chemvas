from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_input_controller import CanvasInputController
    from chemvas.ui.canvas.canvas_pointer_controller import CanvasPointerController
    from chemvas.ui.canvas.canvas_runtime_services import CanvasRuntimeServices


def _optional_canvas_services(canvas) -> CanvasRuntimeServices | None:
    try:
        return canvas.services
    except AttributeError:
        return None


def input_controller_for_view(canvas) -> CanvasInputController | None:
    services = _optional_canvas_services(canvas)
    return services.input_controller if services is not None else None


def pointer_controller_for_view(canvas) -> CanvasPointerController | None:
    services = _optional_canvas_services(canvas)
    return services.pointer_controller if services is not None else None


def scene_pos_from_event_for_view(canvas, event):
    return canvas.mapToScene(event.position().toPoint())


__all__ = [
    "input_controller_for_view",
    "pointer_controller_for_view",
    "scene_pos_from_event_for_view",
]
