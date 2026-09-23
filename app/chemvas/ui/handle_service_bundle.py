from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas_handle_controller import CanvasHandleController
from chemvas.ui.handle_mutation_service import HandleMutationService
from chemvas.ui.handle_overlay_service import HandleOverlayService

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class HandleServiceBundle:
    handle_controller: CanvasHandleController
    handle_overlay_service: HandleOverlayService
    handle_mutation_service: HandleMutationService


def build_handle_services(canvas: CanvasView | Any) -> HandleServiceBundle:
    handle_overlay_service = HandleOverlayService(canvas)
    handle_mutation_service = HandleMutationService(
        canvas,
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
    )


__all__ = ["HandleServiceBundle", "build_handle_services"]
