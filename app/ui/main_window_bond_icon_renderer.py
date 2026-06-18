from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from ui.main_window_icon_geometry import benzene_icon_polygon


class MainWindowBondIconRenderer:
    def __init__(
        self,
        *,
        canvas_style,
        icon_pen,
        renderer_icon_pen,
        icon_brush,
        stroke_active: float,
        stroke_thin: float,
        stroke_regular: float,
        stroke_molecule: float,
        icon_size: int,
    ) -> None:
        self._canvas_style = canvas_style
        self._icon_pen = icon_pen
        self._renderer_icon_pen = renderer_icon_pen
        self._icon_brush = icon_brush
        self._stroke_active = stroke_active
        self._stroke_thin = stroke_thin
        self._stroke_regular = stroke_regular
        self._stroke_molecule = stroke_molecule
        self._icon_size = icon_size

    def draw_bond(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_active))
        painter.drawLine(7, 23, 23, 7)

    def draw_bold_bond(self, painter) -> None:
        start = QPointF(6, 23)
        end = QPointF(24, 7)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        start = QPointF(start.x() + dx * 0.025, start.y() + dy * 0.025)
        end = QPointF(end.x() - dx * 0.025, end.y() - dy * 0.025)
        painter.setPen(self._renderer_icon_pen(self._canvas_style.bold_bond_pen()))
        painter.drawLine(start, end)

    def benzene_icon_inner_segments(
        self,
        polygon: QPolygonF,
        center: QPointF,
        *,
        spacing_scale: float = 1.0,
    ) -> list[tuple[QPointF, QPointF]]:
        if polygon.count() < 2:
            return []
        first = polygon[0]
        second = polygon[1]
        icon_bond_length = math.hypot(second.x() - first.x(), second.y() - first.y())
        if icon_bond_length <= 1e-6:
            return []
        canvas_bond_length = max(1.0, float(self._canvas_style.bond_length_px()))
        scale = canvas_bond_length / icon_bond_length
        scaled_center = QPointF(center.x() * scale, center.y() * scale)
        segments: list[tuple[QPointF, QPointF]] = []
        for index in range(0, polygon.count(), 2):
            start = polygon[index]
            end = polygon[(index + 1) % polygon.count()]
            inner_seg = self._canvas_style.ring_double_inner_segment(
                QPointF(start.x() * scale, start.y() * scale),
                QPointF(end.x() * scale, end.y() * scale),
                scaled_center,
            )
            if inner_seg is None:
                continue
            start_point = QPointF(inner_seg[0] / scale, inner_seg[1] / scale)
            end_point = QPointF(inner_seg[2] / scale, inner_seg[3] / scale)
            if abs(spacing_scale - 1.0) > 1e-6:
                midpoint = QPointF(
                    (start_point.x() + end_point.x()) / 2.0,
                    (start_point.y() + end_point.y()) / 2.0,
                )
                center_dx = midpoint.x() - center.x()
                center_dy = midpoint.y() - center.y()
                adjusted_midpoint = QPointF(
                    center.x() + center_dx * spacing_scale,
                    center.y() + center_dy * spacing_scale,
                )
                start_point = QPointF(
                    adjusted_midpoint.x() + (start_point.x() - midpoint.x()),
                    adjusted_midpoint.y() + (start_point.y() - midpoint.y()),
                )
                end_point = QPointF(
                    adjusted_midpoint.x() + (end_point.x() - midpoint.x()),
                    adjusted_midpoint.y() + (end_point.y() - midpoint.y()),
                )
            segments.append((start_point, end_point))
        return segments

    def draw_ring(self, painter) -> None:
        icon_size = self._icon_size
        center = QPointF(icon_size / 2.0, icon_size / 2.0)
        radius = 13.4

        painter.setPen(self._icon_pen(self._stroke_molecule))
        outer = benzene_icon_polygon(center, radius)
        painter.drawPolygon(outer)
        # Aromatic ring: a delocalised inner circle rather than Kekule bonds.
        painter.drawEllipse(center, 8.0, 8.0)

    def draw_double_bond(self, painter) -> None:
        # Parallel diagonals so double/triple share the single bond's slope.
        painter.setPen(self._icon_pen(self._stroke_regular))
        painter.drawLine(QPointF(6.2, 20.2), QPointF(20.2, 6.2))
        painter.drawLine(QPointF(9.8, 23.8), QPointF(23.8, 9.8))

    def draw_triple_bond(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(QPointF(5.7, 19.7), QPointF(19.7, 5.7))
        painter.drawLine(QPointF(8.0, 22.0), QPointF(22.0, 8.0))
        painter.drawLine(QPointF(10.3, 24.3), QPointF(24.3, 10.3))

    def draw_wedge_bond(self, painter) -> None:
        start = QPointF(7, 23)
        end = QPointF(23, 7)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        start = QPointF(start.x() + dx * 0.1, start.y() + dy * 0.1)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        half_width = self._canvas_style.bold_bond_pen().widthF() * 0.5 * 0.95
        p1 = start
        p2 = QPointF(end.x() + nx * half_width, end.y() + ny * half_width)
        p3 = QPointF(end.x() - nx * half_width, end.y() - ny * half_width)
        polygon = QPolygonF([p1, p2, p3])
        painter.setPen(self._renderer_icon_pen(self._canvas_style.bond_pen()))
        painter.setBrush(self._icon_brush())
        painter.drawPolygon(polygon)

    def draw_hash_bond(self, painter) -> None:
        start = QPointF(7, 23)
        end = QPointF(23, 7)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        count = max(3, int(length / self._canvas_style.hash_spacing_px()))
        max_size = self._canvas_style.bold_bond_pen().widthF()
        t_positions = [index / (count - 1) for index in range(count)]
        t_sizes = [(index + 1) / (count + 1) for index in range(count)]
        max_t = max(t_sizes) if t_sizes else 1.0
        painter.setPen(self._renderer_icon_pen(self._canvas_style.bond_pen()))
        for t_pos, t_size in zip(t_positions, t_sizes, strict=False):
            cx = start.x() + dx * t_pos
            cy = start.y() + dy * t_pos
            size = max_size * (t_size / max_t) if max_t > 0 else max_size
            hx = nx * size / 2.0
            hy = ny * size / 2.0
            painter.drawLine(QPointF(cx - hx, cy - hy), QPointF(cx + hx, cy + hy))

    def draw_dotted_bond(self, painter) -> None:
        painter.setPen(self._renderer_icon_pen(self._canvas_style.dotted_bond_pen()))
        painter.drawLine(QPointF(7.0, 23.0), QPointF(23.0, 7.0))

    def draw_bond_length(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_thin))
        painter.drawLine(6, 15, 24, 15)
        painter.drawLine(6, 11, 6, 19)
        painter.drawLine(24, 11, 24, 19)


__all__ = ["MainWindowBondIconRenderer"]
