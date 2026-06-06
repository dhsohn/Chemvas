from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen

from ui.sheet_setup_access import sheet_rect_for


def draw_canvas_background_for(canvas, painter, rect) -> None:
    painter.save()
    painter.fillRect(rect, QColor("#e7e7e4"))
    sheet_rect = sheet_rect_for(canvas)
    # Layered soft drop shadow so the page reads as paper floating above
    # the workspace rather than blending into it.
    for offset, alpha in ((6.0, 5), (4.0, 9), (2.0, 16)):
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
    painter.restore()


__all__ = ["draw_canvas_background_for"]
