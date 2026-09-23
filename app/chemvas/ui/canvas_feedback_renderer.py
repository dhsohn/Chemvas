"""View-only drawing feedback; no scene item can leak into a figure export."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainterPath, QPen

from chemvas.shell.palette import PALETTE
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.canvas_service_ports import tool_controller_for_access
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for


def draw_canvas_feedback_for(canvas, painter, rect) -> None:
    transform = painter.worldTransform()
    painter.save()
    try:
        painter.resetTransform()
        if tool_settings_state_for(canvas).valence_checking:
            model = model_for(canvas)
            painter.setPen(QPen(QColor(PALETTE["danger_text"]), 1.0))
            for atom_id in canvas.runtime_state.valence_warnings.warnings_for(model):
                atom = model.atoms[atom_id]
                item = visible_atom_item_for(canvas, atom_id)
                bounds = (
                    item.sceneBoundingRect()
                    if item is not None
                    else QRectF(atom.x - 3, atom.y - 3, 6, 6)
                )
                if not rect.intersects(bounds):
                    continue
                bounds = transform.mapRect(bounds).adjusted(-3, -2, 3, 3)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                wave = QPainterPath(QPointF(bounds.left(), bounds.bottom()))
                for x in range(2, max(4, round(bounds.width())) + 1, 2):
                    wave.lineTo(
                        bounds.left() + x, bounds.bottom() + (2 if x % 4 else 0)
                    )
                painter.drawPath(wave)
        tool = tool_controller_for_access(canvas).active
        segment = tool.angle_guide if tool is not None else None
        if segment is None:
            return
        start, end = (QPointF(*point) for point in segment)
        angle = (
            round(math.degrees(math.atan2(start.y() - end.y(), end.x() - start.x())))
            % 360
        )
        start, end = transform.map(start), transform.map(end)
        delta = end - start
        length = math.hypot(delta.x(), delta.y())
        if length == 0:
            return
        extension = delta * (18.0 / length)
        pen = QPen(QColor(13, 148, 136, 120), 0.75, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(start - extension, end + extension)
        font = QFont(painter.font())
        font.setPixelSize(10)
        painter.setFont(font)
        badge = QRectF(end.x() + 12, end.y() - 24, 38, 18)
        painter.setPen(QPen(QColor(PALETTE["checked_border"]), 0.75))
        painter.setBrush(QColor(PALETTE["checked_bg"]))
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(QColor(PALETTE["checked_text"]))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"{angle}°")
    finally:
        painter.restore()
