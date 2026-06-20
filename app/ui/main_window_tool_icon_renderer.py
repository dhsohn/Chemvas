from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPolygonF,
    QRadialGradient,
)


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
        # A single clean pointer; the old selection-marquee corner brackets are
        # dropped to match the cursor in the design mock-up.
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
        self._draw_atomic_mark_icon(painter)

    def draw_mark_minus(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_active))
        painter.drawLine(7, 15, 23, 15)

    def draw_mark_radical(self, painter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._icon_brush())
        painter.drawEllipse(12, 12, 6, 6)

    def _alpha_color(self, color: str | None, alpha: float) -> QColor:
        base = self._icon_pen(self._stroke_thin).color() if color is None else QColor(color)
        base.setAlphaF(max(0.0, min(1.0, alpha)))
        return base

    def _alpha_pen(self, width: float, *, color: str | None = None, alpha: float = 1.0):
        pen = self._icon_pen(width, color=color)
        pen.setColor(self._alpha_color(color, alpha))
        return pen

    def _draw_glow_dot(self, painter, center: QPointF, radius: float, *, alpha: float = 0.82) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._alpha_color(self._pale_fill_color, min(1.0, alpha * 0.62))))
        painter.drawEllipse(center, radius + 1.6, radius + 1.6)
        painter.setBrush(QBrush(self._alpha_color(None, alpha)))
        painter.drawEllipse(center, radius, radius)

    def _draw_atomic_mark_icon(self, painter) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(15.0, 15.0)

        glow = QRadialGradient(center, 10.5)
        glow.setColorAt(0.0, self._alpha_color(self._pale_fill_color, 0.9))
        glow.setColorAt(0.42, self._alpha_color(self._accent_fill_color, 0.36))
        glow.setColorAt(1.0, self._alpha_color(self._accent_fill_color, 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, 10.5, 10.5)

        painter.setPen(self._alpha_pen(self._stroke_fine, alpha=0.16))
        painter.drawLine(QPointF(4.8, 15.0), QPointF(25.2, 15.0))
        painter.drawLine(QPointF(7.2, 7.2), QPointF(22.8, 22.8))

        for angle, alpha, width in ((-27.0, 0.42, 1.05), (32.0, 0.5, 1.15), (82.0, 0.34, 1.0)):
            painter.save()
            painter.translate(center)
            painter.rotate(angle)
            painter.setPen(self._alpha_pen(width, alpha=alpha))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-10.9, -3.45, 21.8, 6.9))
            painter.restore()

        core = QRadialGradient(center, 4.6)
        core.setColorAt(0.0, self._alpha_color("#ffffff", 0.95))
        core.setColorAt(0.48, self._alpha_color(self._pale_fill_color, 0.84))
        core.setColorAt(1.0, self._alpha_color(None, 0.34))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core))
        painter.drawEllipse(center, 4.6, 4.6)
        painter.setBrush(QBrush(self._alpha_color(None, 0.58)))
        painter.drawEllipse(center, 1.15, 1.15)

        self._draw_glow_dot(painter, QPointF(6.8, 22.0), 1.6, alpha=0.8)
        self._draw_glow_dot(painter, QPointF(9.7, 9.2), 0.9, alpha=0.45)
        self._draw_glow_dot(painter, QPointF(22.4, 17.8), 0.85, alpha=0.42)

        painter.restore()

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
        # Dashed vertical mirror axis with a chevron pointing out each side.
        painter.setPen(self._icon_pen(self._stroke_thin, style=Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(15.0, 4.5), QPointF(15.0, 25.5))
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.drawLine(QPointF(10.6, 10.0), QPointF(5.6, 15.0))
        painter.drawLine(QPointF(5.6, 15.0), QPointF(10.6, 20.0))
        painter.drawLine(QPointF(19.4, 10.0), QPointF(24.4, 15.0))
        painter.drawLine(QPointF(24.4, 15.0), QPointF(19.4, 20.0))

    def draw_flip_v(self, painter) -> None:
        # Dashed horizontal mirror axis with a chevron above and below.
        painter.setPen(self._icon_pen(self._stroke_thin, style=Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(4.5, 15.0), QPointF(25.5, 15.0))
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.drawLine(QPointF(10.0, 10.6), QPointF(15.0, 5.6))
        painter.drawLine(QPointF(15.0, 5.6), QPointF(20.0, 10.6))
        painter.drawLine(QPointF(10.0, 19.4), QPointF(15.0, 24.4))
        painter.drawLine(QPointF(15.0, 24.4), QPointF(20.0, 19.4))

    def draw_ts_bracket(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_fine))
        self._draw_square_bracket_icon(painter, QRectF(4.0, 6.0, 8.0, 18.0), left=True)
        self._draw_square_bracket_icon(painter, QRectF(18.0, 6.0, 8.0, 18.0), left=False)
        self._draw_parenthesis_icon(painter, QRectF(9.0, 8.0, 5.0, 14.0), left=True)
        self._draw_parenthesis_icon(painter, QRectF(16.0, 8.0, 5.0, 14.0), left=False)

    def _draw_square_bracket_icon(self, painter, rect: QRectF, *, left: bool) -> None:
        hook = rect.width() * 0.55
        if left:
            x = rect.left()
            painter.drawLine(QPointF(x + hook, rect.top()), QPointF(x, rect.top()))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(x, rect.bottom()), QPointF(x + hook, rect.bottom()))
            return
        x = rect.right()
        painter.drawLine(QPointF(x - hook, rect.top()), QPointF(x, rect.top()))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.drawLine(QPointF(x, rect.bottom()), QPointF(x - hook, rect.bottom()))

    def _draw_parenthesis_icon(self, painter, rect: QRectF, *, left: bool) -> None:
        path = QPainterPath()
        top = rect.top()
        bottom = rect.bottom()
        middle = rect.center().y()
        control = rect.height() * 0.22
        if left:
            outer_x = rect.left()
            inner_x = rect.right()
            path.moveTo(inner_x, top)
            path.cubicTo(outer_x, top + control, outer_x, middle - control, outer_x, middle)
            path.cubicTo(outer_x, middle + control, outer_x, bottom - control, inner_x, bottom)
        else:
            outer_x = rect.right()
            inner_x = rect.left()
            path.moveTo(inner_x, top)
            path.cubicTo(outer_x, top + control, outer_x, middle - control, outer_x, middle)
            path.cubicTo(outer_x, middle + control, outer_x, bottom - control, inner_x, bottom)
        painter.drawPath(path)

    def _draw_brace_icon(self, painter, rect: QRectF, *, left: bool) -> None:
        path = QPainterPath()
        top = rect.top()
        bottom = rect.bottom()
        middle = rect.center().y()
        quarter = rect.height() / 4.0
        sign = 1.0 if left else -1.0
        outer_x = rect.left() if left else rect.right()
        inner_x = outer_x + sign * rect.width()
        waist_x = outer_x + sign * rect.width() * 0.18
        shoulder_x = outer_x + sign * rect.width() * 0.62
        path.moveTo(inner_x, top)
        path.cubicTo(outer_x, top, outer_x, top + quarter * 0.55, waist_x, top + quarter)
        path.cubicTo(shoulder_x, top + quarter * 1.32, shoulder_x, middle - quarter * 0.35, outer_x, middle)
        path.cubicTo(shoulder_x, middle + quarter * 0.35, shoulder_x, bottom - quarter * 1.32, waist_x, bottom - quarter)
        path.cubicTo(outer_x, bottom - quarter * 0.55, outer_x, bottom, inner_x, bottom)
        painter.drawPath(path)

    def _draw_dagger_icon(self, painter, symbol: str) -> None:
        font = painter.font()
        font.setPixelSize(22)
        painter.setFont(font)
        painter.drawText(QRectF(6.0, 4.5, 18.0, 21.0), Qt.AlignmentFlag.AlignCenter, symbol)

    def draw_bracket_preview(self, painter, kind: str) -> None:
        painter.setPen(self._icon_pen(self._stroke_fine))
        top = 5.5
        height = 19.0
        left_pair = QRectF(4.8, top, 7.2, height)
        right_pair = QRectF(18.0, top, 7.2, height)
        single_left = QRectF(8.2, top, 8.2, height)
        if kind == "square_left":
            self._draw_square_bracket_icon(painter, single_left, left=True)
        elif kind == "parenthesis_left":
            self._draw_parenthesis_icon(painter, single_left, left=True)
        elif kind == "brace_left":
            self._draw_brace_icon(painter, single_left, left=True)
        elif kind == "parentheses_pair":
            self._draw_parenthesis_icon(painter, left_pair, left=True)
            self._draw_parenthesis_icon(painter, right_pair, left=False)
        elif kind == "braces_pair":
            self._draw_brace_icon(painter, left_pair, left=True)
            self._draw_brace_icon(painter, right_pair, left=False)
        elif kind == "dagger":
            self._draw_dagger_icon(painter, "\u2020")
        elif kind == "double_dagger":
            self._draw_dagger_icon(painter, "\u2021")
        else:
            self._draw_square_bracket_icon(painter, left_pair, left=True)
            self._draw_square_bracket_icon(painter, right_pair, left=False)

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
        # Cross with a symmetric chevron arrowhead on each of the four ends.
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(QPointF(15.0, 5.0), QPointF(15.0, 25.0))
        painter.drawLine(QPointF(5.0, 15.0), QPointF(25.0, 15.0))
        painter.drawLine(QPointF(11.9, 8.1), QPointF(15.0, 5.0))
        painter.drawLine(QPointF(15.0, 5.0), QPointF(18.1, 8.1))
        painter.drawLine(QPointF(11.9, 21.9), QPointF(15.0, 25.0))
        painter.drawLine(QPointF(15.0, 25.0), QPointF(18.1, 21.9))
        painter.drawLine(QPointF(8.1, 11.9), QPointF(5.0, 15.0))
        painter.drawLine(QPointF(5.0, 15.0), QPointF(8.1, 18.1))
        painter.drawLine(QPointF(21.9, 11.9), QPointF(25.0, 15.0))
        painter.drawLine(QPointF(25.0, 15.0), QPointF(21.9, 18.1))

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
