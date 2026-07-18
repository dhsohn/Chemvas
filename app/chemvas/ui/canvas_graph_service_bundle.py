from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas_graph_service import CanvasGraphService

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasGraphServiceBundle:
    canvas_graph_service: CanvasGraphService


def build_canvas_graph_services(
    canvas: CanvasView | Any, *, graph_state: Any
) -> CanvasGraphServiceBundle:
    canvas_graph_service = CanvasGraphService(canvas, graph_state)
    return CanvasGraphServiceBundle(canvas_graph_service=canvas_graph_service)


__all__ = ["CanvasGraphServiceBundle", "build_canvas_graph_services"]
