from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene

    from .plan import ExportPlan

METERS_PER_INCH = 0.0254


def paint_scene_region(
    painter: QPainter,
    scene: QGraphicsScene,
    plan: ExportPlan,
    target_w: float,
    target_h: float,
    background: str,
) -> None:
    target = QRectF(0.0, 0.0, float(target_w), float(target_h))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if background == "white":
        painter.fillRect(target, Qt.GlobalColor.white)
    source = QRectF(plan.source_x, plan.source_y, plan.source_w, plan.source_h)
    scene.render(painter, target, source)


__all__ = ["METERS_PER_INCH", "paint_scene_region"]
