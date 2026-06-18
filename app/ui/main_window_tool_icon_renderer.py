from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPolygonF


class MainWindowToolIconRenderer:
    def __init__(
        self,
        *,
        icon_pen,
        icon_brush,
        stroke_fine: float,
        stroke_thin: float,
        stroke_regular: float,
        stroke_molecule: float,
        stroke_active: float,
        icon_content_min: int,
        icon_content_max: int,
        icon_center: int,
        pale_fill_color: str,
        accent_fill_color: str,
    ) -> None:
        self._icon_pen = icon_pen
        self._icon_brush = icon_brush
        self._stroke_fine = stroke_fine
        self._stroke_thin = stroke_thin
        self._stroke_regular = stroke_regular
        self._stroke_molecule = stroke_molecule
        self._stroke_active = stroke_active
        self._icon_content_min = icon_content_min
        self._icon_content_max = icon_content_max
        self._icon_center = icon_center
        self._pale_fill_color = pale_fill_color
        self._accent_fill_color = accent_fill_color

    def draw_select(self, painter) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self._icon_pen(self._stroke_active))
        left, top, right, bottom = 4.5, 4.5, 25.5, 24.5
        corner = 5.5
        painter.drawLine(QPointF(left, top), QPointF(left + corner, top))
        painter.drawLine(QPointF(left, top), QPointF(left, top + corner))
        painter.drawLine(QPointF(right, top), QPointF(right - corner, top))
        painter.drawLine(QPointF(right, top), QPointF(right, top + corner))
        painter.drawLine(QPointF(left, bottom), QPointF(left + corner, bottom))
        painter.drawLine(QPointF(left, bottom), QPointF(left, bottom - corner))
        painter.drawLine(QPointF(right, bottom), QPointF(right - corner, bottom))
        painter.drawLine(QPointF(right, bottom), QPointF(right, bottom - corner))

        cursor = QPainterPath()
        cursor.moveTo(7.2, 6.7)
        cursor.lineTo(7.2, 26.7)
        cursor.lineTo(12.5, 21.4)
        cursor.lineTo(15.8, 26.8)
        cursor.lineTo(19.7, 24.4)
        cursor.lineTo(16.4, 19.2)
        cursor.lineTo(24.2, 19.2)
        cursor.closeSubpath()
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.setBrush(self._icon_brush())
        painter.drawPath(cursor)

    def draw_mark_plus(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_active))
        painter.drawLine(15, 7, 15, 23)
        painter.drawLine(7, 15, 23, 15)

    def draw_mark(self, painter) -> None:
        # Outlined bolt so it sits in the same line-art language as the rest
        # of the set instead of a flat filled glyph.
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bolt = QPolygonF(
            [
                QPointF(17.5, 4.5),
                QPointF(8.0, 16.0),
                QPointF(14.0, 16.0),
                QPointF(12.0, 25.5),
                QPointF(22.5, 12.8),
                QPointF(16.5, 12.8),
            ]
        )
        painter.drawPolygon(bolt)

    def draw_mark_minus(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_active))
        painter.drawLine(7, 15, 23, 15)

    def draw_mark_radical(self, painter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._icon_brush())
        painter.drawEllipse(12, 12, 6, 6)

    def draw_text(self, painter) -> None:
        # Stroked letterform so the text tool matches the line-art icon set
        # instead of reading as a heavy filled glyph.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self._icon_pen(self._stroke_active))
        legs = QPainterPath()
        legs.moveTo(7.5, 24.0)
        legs.lineTo(15.0, 6.0)
        legs.lineTo(22.5, 24.0)
        painter.drawPath(legs)
        painter.drawLine(QPointF(10.0, 18.0), QPointF(20.0, 18.0))

    def draw_ring_fill(self, painter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(float(self._icon_center), float(self._icon_center))
        radius = (self._icon_content_max - self._icon_content_min) / 2.0
        outer = QPolygonF()
        for index in range(5):
            angle = math.radians(360 / 5 * index - 90)
            outer.append(
                QPointF(
                    center.x() + radius * math.cos(angle),
                    center.y() + radius * math.sin(angle),
                )
            )
        painter.setPen(self._icon_pen(self._stroke_molecule))
        painter.setBrush(self._icon_brush(self._pale_fill_color))
        painter.drawPolygon(outer)

    def draw_orbital_preview(self, painter, kind: str) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        if kind == "s":
            painter.drawEllipse(9, 9, 12, 12)
        elif kind == "p":
            painter.drawEllipse(6, 11, 10, 10)
            painter.drawEllipse(14, 9, 10, 10)
        elif kind == "sp":
            painter.drawEllipse(6, 12, 10, 10)
            painter.drawEllipse(16, 8, 10, 10)
            painter.drawLine(5, 18, 25, 12)
        elif kind in {"sp2", "sp3"}:
            painter.drawEllipse(7, 7, 8, 8)
            painter.drawEllipse(15, 7, 8, 8)
            painter.drawEllipse(11, 15, 8, 8)
            if kind == "sp3":
                painter.drawEllipse(11, 2, 8, 8)
        elif kind == "d":
            painter.drawEllipse(6, 10, 8, 8)
            painter.drawEllipse(16, 10, 8, 8)
            painter.drawEllipse(11, 5, 8, 8)
            painter.drawEllipse(11, 15, 8, 8)
        else:
            painter.drawEllipse(9, 9, 12, 12)
            painter.drawLine(15, 9, 15, 21)

    def draw_flip_h(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(15, 5, 15, 25)
        painter.drawLine(7, 9, 13, 9)
        painter.drawLine(7, 21, 13, 21)
        painter.drawLine(17, 9, 23, 9)
        painter.drawLine(17, 21, 23, 21)

    def draw_flip_v(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(5, 15, 25, 15)
        painter.drawLine(9, 7, 9, 13)
        painter.drawLine(21, 7, 21, 13)
        painter.drawLine(9, 17, 9, 23)
        painter.drawLine(21, 17, 21, 23)

    def draw_ts_bracket(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_fine))
        painter.drawLine(8, 7, 5, 7)
        painter.drawLine(5, 7, 5, 23)
        painter.drawLine(5, 23, 8, 23)
        painter.drawLine(22, 7, 25, 7)
        painter.drawLine(25, 7, 25, 23)
        painter.drawLine(25, 23, 22, 23)
        font = painter.font()
        font.setPixelSize(8)
        painter.setFont(font)
        painter.drawText(QRectF(10.0, 8.0, 12.0, 8.0), Qt.AlignmentFlag.AlignCenter, "TS")

    def draw_orbital(self, painter) -> None:
        # Two lobes meeting at a central nucleus so it reads as a p-orbital
        # dumbbell rather than two detached circles.
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(3, 11, 12, 8)
        painter.drawEllipse(15, 11, 12, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._icon_brush())
        painter.drawEllipse(QPointF(15.0, 15.0), 1.4, 1.4)

    def draw_move(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(self._icon_center, self._icon_content_min, self._icon_center, self._icon_content_max)
        painter.drawLine(self._icon_content_min, self._icon_center, self._icon_content_max, self._icon_center)
        painter.drawLine(self._icon_center, self._icon_content_min, 12, 8)
        painter.drawLine(self._icon_center, self._icon_content_min, 18, 8)
        painter.drawLine(self._icon_center, self._icon_content_max, 12, 22)
        painter.drawLine(self._icon_center, self._icon_content_max, 18, 22)
        painter.drawLine(self._icon_content_min, self._icon_center, 8, 12)
        painter.drawLine(self._icon_content_min, self._icon_center, 8, 18)
        painter.drawLine(self._icon_content_max, self._icon_center, 22, 12)
        painter.drawLine(self._icon_content_max, self._icon_center, 22, 18)

    def draw_color(self, painter) -> None:
        # Line-art palette: an outlined body with a thumb hole and three small
        # solid paint wells, instead of a flat filled blob.
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(4, 7, 22, 18)
        painter.drawEllipse(QPointF(10.5, 19.0), 2.1, 2.1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._icon_brush())
        painter.drawEllipse(QPointF(13.5, 12.0), 1.5, 1.5)
        painter.drawEllipse(QPointF(18.5, 11.5), 1.5, 1.5)
        painter.drawEllipse(QPointF(21.5, 15.5), 1.5, 1.5)

    def draw_perspective(self, painter) -> None:
        # A clean isometric cube with a lightly shaded top face. Stays legible
        # at toolbar size, where the old wireframe-slab-plus-rotation-arc
        # collapsed into an unreadable blob.
        painter.setPen(self._icon_pen(self._stroke_thin))
        top = QPolygonF(
            [
                QPointF(15.0, 5.5),
                QPointF(24.5, 11.0),
                QPointF(15.0, 16.5),
                QPointF(5.5, 11.0),
            ]
        )
        painter.setBrush(self._icon_brush(self._pale_fill_color))
        painter.drawPolygon(top)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(5.5, 11.0), QPointF(5.5, 20.0))
        painter.drawLine(QPointF(24.5, 11.0), QPointF(24.5, 20.0))
        painter.drawLine(QPointF(15.0, 16.5), QPointF(15.0, 25.5))
        painter.drawLine(QPointF(5.5, 20.0), QPointF(15.0, 25.5))
        painter.drawLine(QPointF(24.5, 20.0), QPointF(15.0, 25.5))


__all__ = ["MainWindowToolIconRenderer"]
