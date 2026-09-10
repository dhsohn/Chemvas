from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen

from chemvas.ui.endpoint_snap_access import grid_snap_enabled_for, grid_step_for
from chemvas.ui.sheet_setup_access import sheet_rect_for

# Below this on-screen spacing the grid reads as a grey wash rather than as a
# guide, so it is left unpainted while the snapping itself keeps working.
MIN_GRID_SPACING_PX = 6.0


def draw_canvas_background_for(canvas, painter, rect) -> None:
    painter.save()
    painter.fillRect(rect, QColor("#e7e7e4"))
    sheet_rect = sheet_rect_for(canvas)
    # Layered soft drop shadow (light from top-left) so the page clearly reads
    # as paper floating above the workspace rather than blending into it. The
    # tight, darker inner layer gives a crisp contact edge; the wider, fainter
    # outer layers fall off into a soft ambient halo.
    for offset, alpha in ((11.0, 6), (6.5, 11), (3.0, 17), (1.4, 26)):
        painter.fillRect(
            sheet_rect.adjusted(-offset * 0.4, offset * 0.3, offset, offset + 1.0),
            QColor(0, 0, 0, alpha),
        )
    painter.fillRect(sheet_rect, QColor("#ffffff"))
    pen = QPen(QColor("#dededa"))
    pen.setWidthF(1.0)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(sheet_rect)
    _draw_grid(canvas, painter, rect, sheet_rect)
    painter.restore()


def _draw_grid(canvas, painter, rect, sheet_rect) -> None:
    if not grid_snap_enabled_for(canvas):
        return
    step = grid_step_for(canvas)
    if step <= 0.0:
        return
    # The exposed rect can be far larger than the page; only the part of the
    # sheet actually on screen needs points.
    area = sheet_rect.intersected(rect)
    if area.isEmpty():
        return
    # Perspective squashes the vertical scale independently, so the denser
    # of the two axes decides whether the grid is still readable.
    transform = painter.transform()
    scale = min(abs(transform.m11()), abs(transform.m22())) or 1.0
    if step * scale < MIN_GRID_SPACING_PX:
        return
    pen = QPen(QColor("#c9c9c4"))
    pen.setWidthF(0.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    first_x = math.ceil(area.left() / step) * step
    first_y = math.ceil(area.top() / step) * step
    points = [
        QPointF(x, y)
        for x in _grid_coordinates(first_x, area.right(), step)
        for y in _grid_coordinates(first_y, area.bottom(), step)
    ]
    if points:
        painter.drawPoints(*points)


def _grid_coordinates(first: float, limit: float, step: float) -> list[float]:
    count = int((limit - first) / step) + 1 if limit >= first else 0
    return [first + index * step for index in range(max(0, count))]


__all__ = ["draw_canvas_background_for"]
