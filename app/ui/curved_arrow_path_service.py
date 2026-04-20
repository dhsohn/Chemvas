from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsPathItem

    from ui.canvas_view import CanvasView


class CurvedArrowPathService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def set_curved_arrow_path(
        self,
        item: QGraphicsPathItem,
        start: QPointF,
        end: QPointF,
        control: QPointF,
        double: bool,
    ) -> None:
        # Curved-arrow geometry is tracked in scene coordinates.
        # Reset per-item translation before rebuilding the local path so
        # the rendered arrow stays aligned with endpoint/control handles.
        item.setPos(0.0, 0.0)
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self.canvas._add_arrow_head(path, control, end, double=False)
            self.canvas._add_arrow_head(path, control, start, double=False)
        else:
            self.canvas._add_arrow_head(path, control, end, double=False)
        item.setPath(path)


def curved_arrow_path_service_for(canvas) -> CurvedArrowPathService:
    service = getattr(canvas, "_curved_arrow_path_service", None)
    if isinstance(service, CurvedArrowPathService) and service.canvas is canvas:
        return service
    if service is not None and hasattr(service, "set_curved_arrow_path"):
        return service
    return CurvedArrowPathService(canvas)


__all__ = ["CurvedArrowPathService", "curved_arrow_path_service_for"]
