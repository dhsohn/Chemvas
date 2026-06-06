from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.canvas_handle_controller import CanvasHandleController
from ui.curved_arrow_path_service import CurvedArrowPathService
from ui.handle_mutation_service import HandleMutationService
from ui.handle_overlay_service import HandleOverlayService

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class HandleServiceBundle:
    handle_controller: CanvasHandleController
    handle_overlay_service: HandleOverlayService
    handle_mutation_service: HandleMutationService
    curved_arrow_path_service: CurvedArrowPathService


def build_handle_services(canvas: CanvasView | Any) -> HandleServiceBundle:
    handle_overlay_service = HandleOverlayService(canvas)
    curved_arrow_path_service = CurvedArrowPathService(canvas)
    handle_mutation_service = HandleMutationService(
        canvas,
        curved_arrow_path_service=curved_arrow_path_service,
    )
    handle_controller = CanvasHandleController(
        canvas,
        handle_overlay_service=handle_overlay_service,
        handle_mutation_service=handle_mutation_service,
    )
    return HandleServiceBundle(
        handle_controller=handle_controller,
        handle_overlay_service=handle_overlay_service,
        handle_mutation_service=handle_mutation_service,
        curved_arrow_path_service=curved_arrow_path_service,
    )


__all__ = ["HandleServiceBundle", "build_handle_services"]
