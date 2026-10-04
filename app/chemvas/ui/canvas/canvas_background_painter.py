from __future__ import annotations

from PyQt6.QtCore import QLineF, Qt
from PyQt6.QtGui import QColor, QPen

from chemvas.features.rendering import grid_lines
from chemvas.ui.canvas.canvas_tool_settings_state import (
    GRID_COLOR,
    MIN_GRID_SPACING_PX,
    grid_step_for,
)
from chemvas.ui.canvas.sheet_setup_access import sheet_rect_for


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
    if not canvas.runtime_state.tool_settings_state.grid_snap_enabled:
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
    settings = canvas.runtime_state.tool_settings_state
    color = QColor(GRID_COLOR)
    color.setAlphaF(settings.grid_opacity)
    pen = QPen(color)
    pen.setWidthF(0.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setClipRect(area, Qt.ClipOperation.IntersectClip)
    lines = [
        QLineF(*line)
        for line in grid_lines(
            (area.left(), area.top(), area.right(), area.bottom()),
            step=step,
            style=settings.grid_style,
        )
    ]
    if lines:
        painter.drawLines(lines)


__all__ = ["draw_canvas_background_for"]
