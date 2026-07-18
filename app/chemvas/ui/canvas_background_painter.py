from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen

from chemvas.ui.sheet_setup_access import sheet_rect_for


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
    painter.restore()


__all__ = ["draw_canvas_background_for"]
