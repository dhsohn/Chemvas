from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

from ui.scene_decoration_build_access import add_arrow_head_for

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
            add_arrow_head_for(self.canvas, path, control, end, double=False)
            add_arrow_head_for(self.canvas, path, control, start, double=False)
        else:
            add_arrow_head_for(self.canvas, path, control, end, double=False)
        item.setPath(path)


__all__ = ["CurvedArrowPathService"]
