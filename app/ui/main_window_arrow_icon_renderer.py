from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath

from ui.main_window_palette import PALETTE


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
            path.moveTo(4, 22)
            path.quadTo(15, 3, 26, 15)
            painter.drawPath(path)
            self.draw_arrow_head(painter, QPointF(15, 5), QPointF(26, 15))
            if kind == "curved_double":
                self.draw_arrow_head(painter, QPointF(15, 5), QPointF(4, 22))
        elif kind == "equilibrium":
            painter.drawLine(3, 10, 27, 10)
            self.draw_arrow_head(painter, QPointF(3, 10), QPointF(27, 10))
            painter.drawLine(27, 20, 3, 20)
            self.draw_arrow_head(painter, QPointF(27, 20), QPointF(3, 20))
        elif kind == "resonance":
            painter.drawLine(3, 15, 27, 15)
            self.draw_arrow_head(painter, QPointF(3, 15), QPointF(27, 15))
            self.draw_arrow_head(painter, QPointF(27, 15), QPointF(3, 15))
        elif kind == "inhibit":
            painter.drawLine(3, 15, 26, 15)
            painter.drawLine(26, 8, 26, 22)
        else:
            painter.drawLine(3, 15, 27, 15)
            self.draw_arrow_head(painter, QPointF(3, 15), QPointF(27, 15))

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

    def draw_arrow_preset(self, painter, label: str) -> None:
        width = {"Default": self._stroke_thin, "Bold": self._stroke_active + 0.9, "Fine": 1.0}.get(
            label,
            self._stroke_thin,
        )
        painter.setPen(self._icon_pen(width))
        painter.drawLine(5, 15, 24, 15)
        self.draw_arrow_head(painter, QPointF(5, 15), QPointF(24, 15))

    def draw_arrow_width_control(self, painter) -> None:
        painter.setPen(self._icon_pen(1.2, color=PALETTE["icon_muted"]))
        painter.drawLine(6, 10, 24, 10)
        painter.setPen(self._icon_pen(self._stroke_active))
        painter.drawLine(6, 19, 24, 19)

    def draw_arrow_head_control(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(5, 15, 24, 15)
        self.draw_arrow_head(painter, QPointF(5, 15), QPointF(24, 15))
        self.draw_arrow_head(painter, QPointF(9, 15), QPointF(24, 15))


__all__ = ["MainWindowArrowIconRenderer"]
