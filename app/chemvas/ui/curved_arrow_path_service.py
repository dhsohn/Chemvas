from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.canvas_service_ports import arrow_build_service_for_access

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QGraphicsPathItem

    from chemvas.ui.canvas_view import CanvasView


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
        arrow_build_service_for_access(self.canvas).set_curved_arrow_path(
            item, start, end, control, double
        )


__all__ = ["CurvedArrowPathService"]
