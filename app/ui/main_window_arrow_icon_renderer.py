from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath


class MainWindowArrowIconRenderer:
    def __init__(
        self,
        *,
        icon_pen,
        stroke_thin: float,
        stroke_active: float,
        icon_content_min: int,
        icon_center: int,
    ) -> None:
        self._icon_pen = icon_pen
        self._stroke_thin = stroke_thin
        self._stroke_active = stroke_active
        self._icon_content_min = icon_content_min
        self._icon_center = icon_center

    def draw_arrow_preview(self, painter, kind: str) -> None:
        style = Qt.PenStyle.DashLine if kind == "dotted" else None
        painter.setPen(self._icon_pen(self._stroke_thin, style=style))
        if kind in {"curved_single", "curved_double"}:
            path = QPainterPath()
            path.moveTo(6, 19)
            path.quadTo(15, 6, 24, 15)
            painter.drawPath(path)
            self.draw_arrow_head(painter, QPointF(15, 8), QPointF(24, 15))
            if kind == "curved_double":
                self.draw_arrow_head(painter, QPointF(15, 8), QPointF(6, 19))
        elif kind == "equilibrium":
            painter.drawLine(5, 11, 23, 11)
            self.draw_arrow_head(painter, QPointF(5, 11), QPointF(23, 11))
            painter.drawLine(23, 19, 5, 19)
            self.draw_arrow_head(painter, QPointF(23, 19), QPointF(5, 19))
        elif kind == "resonance":
            painter.drawLine(5, 15, 23, 15)
            self.draw_arrow_head(painter, QPointF(5, 15), QPointF(23, 15))
            self.draw_arrow_head(painter, QPointF(23, 15), QPointF(5, 15))
        elif kind == "inhibit":
            painter.drawLine(5, 15, 23, 15)
            painter.drawLine(23, 10, 23, 20)
        else:
            painter.drawLine(5, 15, 23, 15)
            self.draw_arrow_head(painter, QPointF(5, 15), QPointF(23, 15))

    @staticmethod
    def draw_arrow_head(painter, start: QPointF, end: QPointF) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = 4.5
        head_angle = math.radians(25)
        left = QPointF(
            end.x() - head_len * math.cos(angle - head_angle),
            end.y() - head_len * math.sin(angle - head_angle),
        )
        right = QPointF(
            end.x() - head_len * math.cos(angle + head_angle),
            end.y() - head_len * math.sin(angle + head_angle),
        )
        painter.drawLine(left, end)
        painter.drawLine(right, end)

    def draw_arrow(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_active))
        painter.drawLine(self._icon_content_min, self._icon_center, 23, self._icon_center)
        painter.drawLine(23, self._icon_center, 18, 11)
        painter.drawLine(23, self._icon_center, 18, 19)


__all__ = ["MainWindowArrowIconRenderer"]
