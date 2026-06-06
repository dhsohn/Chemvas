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
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.drawArc(5, 8, 18, 18, 90 * 16, 270 * 16)
        painter.drawLine(8, 10, 5, 15)
        painter.drawLine(8, 10, 11, 10)

    def draw_redo(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.drawArc(8, 8, 18, 18, 180 * 16, 270 * 16)
        painter.drawLine(23, 10, 25, 15)
        painter.drawLine(23, 10, 19, 10)

    def draw_save(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(QPointF(15.0, 5.0), QPointF(15.0, 17.5))
        painter.drawLine(QPointF(10.0, 12.5), QPointF(15.0, 17.5))
        painter.drawLine(QPointF(20.0, 12.5), QPointF(15.0, 17.5))
        painter.drawLine(QPointF(6.0, 19.0), QPointF(6.0, 24.0))
        painter.drawLine(QPointF(6.0, 24.0), QPointF(24.0, 24.0))
        painter.drawLine(QPointF(24.0, 24.0), QPointF(24.0, 19.0))

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

    def draw_export_xyz(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawRect(7, 8, 10, 12)
        painter.drawLine(17, 8, 23, 12)
        painter.drawLine(17, 20, 23, 24)
        painter.drawLine(23, 12, 23, 24)
        painter.drawLine(7, 8, 13, 12)
        painter.drawLine(13, 12, 23, 12)
        painter.drawLine(7, 20, 13, 24)
        painter.drawLine(13, 24, 23, 24)

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

    def draw_add_sheet(self, painter) -> None:
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
