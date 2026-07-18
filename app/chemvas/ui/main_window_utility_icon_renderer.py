from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath


class MainWindowUtilityIconRenderer:
    def __init__(
        self,
        *,
        icon_pen,
        icon_brush,
        stroke_thin: float,
        stroke_regular: float,
    ) -> None:
        self._icon_pen = icon_pen
        self._icon_brush = icon_brush
        self._stroke_thin = stroke_thin
        self._stroke_regular = stroke_regular

    def draw_undo(self, painter) -> None:
        # Back-pointing chevron, flat top bar, then a curl down the right side.
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(10.4, 6.1), QPointF(5.2, 11.3))
        painter.drawLine(QPointF(5.2, 11.3), QPointF(10.4, 16.4))
        body = QPainterPath()
        body.moveTo(5.2, 11.3)
        body.lineTo(18.4, 11.3)
        body.arcTo(12.1, 11.3, 12.6, 12.6, 90.0, -180.0)
        body.lineTo(16.1, 23.9)
        painter.drawPath(body)

    def draw_redo(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(19.6, 6.1), QPointF(24.8, 11.3))
        painter.drawLine(QPointF(24.8, 11.3), QPointF(19.6, 16.4))
        body = QPainterPath()
        body.moveTo(24.8, 11.3)
        body.lineTo(11.6, 11.3)
        body.arcTo(5.3, 11.3, 12.6, 12.6, 90.0, 180.0)
        body.lineTo(13.9, 23.9)
        painter.drawPath(body)

    def draw_save(self, painter) -> None:
        # Download arrow dropping into a tray with softly rounded corners.
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(15.0, 4.0), QPointF(15.0, 17.5))
        painter.drawLine(QPointF(10.3, 12.8), QPointF(15.0, 17.5))
        painter.drawLine(QPointF(19.7, 12.8), QPointF(15.0, 17.5))
        tray = QPainterPath()
        tray.moveTo(5.6, 19.5)
        tray.lineTo(5.6, 22.8)
        tray.quadTo(5.6, 24.8, 7.6, 24.8)
        tray.lineTo(22.4, 24.8)
        tray.quadTo(24.4, 24.8, 24.4, 22.8)
        tray.lineTo(24.4, 19.5)
        painter.drawPath(tray)

    def draw_open(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        path = QPainterPath()
        path.moveTo(5.0, 9.5)
        path.lineTo(11.0, 9.5)
        path.lineTo(13.5, 12.0)
        path.lineTo(25.0, 12.0)
        path.lineTo(25.0, 23.0)
        path.lineTo(5.0, 23.0)
        path.closeSubpath()
        painter.drawPath(path)

    def draw_preview_panel(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(6, 7, 18, 16)
        painter.drawLine(17, 7, 17, 23)
        painter.drawLine(QPointF(10.0, 18.0), QPointF(13.0, 13.0))
        painter.drawLine(QPointF(13.0, 13.0), QPointF(16.0, 18.0))
        painter.setBrush(self._icon_brush())
        painter.drawEllipse(QPointF(10.0, 18.0), 1.4, 1.4)
        painter.drawEllipse(QPointF(13.0, 13.0), 1.4, 1.4)
        painter.drawEllipse(QPointF(16.0, 18.0), 1.4, 1.4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(20, 11, 22, 11)
        painter.drawLine(20, 15, 22, 15)
        painter.drawLine(20, 19, 22, 19)

    def draw_add_canvas(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawRect(6, 7, 18, 16)
        painter.drawLine(15, 10, 15, 20)
        painter.drawLine(10, 15, 20, 15)
        painter.drawLine(9, 25, 21, 25)

    def draw_setup_sheet(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        path = QPainterPath()
        path.moveTo(8.0, 5.0)
        path.lineTo(19.0, 5.0)
        path.lineTo(24.0, 10.0)
        path.lineTo(24.0, 25.0)
        path.lineTo(8.0, 25.0)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(19.0, 5.0), QPointF(19.0, 10.0))
        painter.drawLine(QPointF(19.0, 10.0), QPointF(24.0, 10.0))

    def draw_info(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawEllipse(7, 7, 16, 16)
        painter.drawLine(15, 13, 15, 19)
        painter.drawPoint(15, 10)


__all__ = ["MainWindowUtilityIconRenderer"]
