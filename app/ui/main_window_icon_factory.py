from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from core.model import Atom


class MainWindowIconFactory:
    def __init__(self, window) -> None:
        self.window = window

    def make_icon(self, painter_fn, size: int = 30) -> QIcon:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_fn(painter)
        painter.end()
        return QIcon(pixmap)

    def icon_select(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#8b7355"))
            pen.setWidthF(2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(5, 6, 20, 18)
        return self.make_icon(draw)

    def icon_bond(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(7, 23, 23, 7)
        return self.make_icon(draw)

    def icon_bond_bold(self) -> QIcon:
        def draw(p):
            start = QPointF(6, 23)
            end = QPointF(24, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            start = QPointF(start.x() + dx * 0.025, start.y() + dy * 0.025)
            end = QPointF(end.x() - dx * 0.025, end.y() - dy * 0.025)
            p.setPen(self.window.canvas.renderer.bold_bond_pen())
            p.drawLine(start, end)
        return self.make_icon(draw)

    def icon_mark_plus(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(15, 7, 15, 23)
            p.drawLine(7, 15, 23, 15)
        return self.make_icon(draw)

    def icon_mark_minus(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(7, 15, 23, 15)
        return self.make_icon(draw)

    def icon_mark_radical(self) -> QIcon:
        def draw(p):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3d3229"))
            p.drawEllipse(12, 12, 6, 6)
        return self.make_icon(draw)

    def icon_text(self) -> QIcon:
        def draw(p):
            font = QFont("Arial")
            font.setBold(True)
            font.setPointSize(22)
            p.setFont(font)
            p.setPen(QPen(QColor("#3d3229")))
            p.drawText(7, 21, "A")
        return self.make_icon(draw)

    def benzene_icon_polygon(self, center: QPointF, radius: float) -> QPolygonF:
        polygon = QPolygonF()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            polygon.append(
                QPointF(
                    center.x() + radius * math.cos(angle),
                    center.y() + radius * math.sin(angle),
                )
            )
        return polygon

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
        canvas_bond_length = max(1.0, float(self.window.canvas.renderer.style.bond_length_px))
        scale = canvas_bond_length / icon_bond_length
        scaled_center = QPointF(center.x() * scale, center.y() * scale)
        segments: list[tuple[QPointF, QPointF]] = []
        for index in range(0, polygon.count(), 2):
            start = polygon[index]
            end = polygon[(index + 1) % polygon.count()]
            _, inner_seg, _ = self.window.canvas._ring_double_segments(
                Atom("C", start.x() * scale, start.y() * scale),
                Atom("C", end.x() * scale, end.y() * scale),
                scaled_center,
            )
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

    def icon_ring(self) -> QIcon:
        icon_size = 26
        center = QPointF(icon_size / 2.0, icon_size / 2.0)
        radius = 11.2

        def draw(p):
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.8)
            p.setPen(pen)
            outer = self.benzene_icon_polygon(center, radius)
            p.drawPolygon(outer)
            inner_pen = QPen(QColor("#3d3229"))
            inner_pen.setWidthF(1.8)
            p.setPen(inner_pen)
            for start, end in self.benzene_icon_inner_segments(outer, center, spacing_scale=0.92):
                p.drawLine(start, end)
        return self.make_icon(draw, size=icon_size)

    def icon_ring_fill(self) -> QIcon:
        def draw(p):
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.8)
            center = QPointF(15.0, 15.0)
            radius = 10.0
            outer = QPolygonF()
            for i in range(5):
                angle = math.radians(360 / 5 * i - 90)
                outer.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.setPen(pen)
            p.setBrush(QBrush(QColor("#f3ead7")))
            p.drawPolygon(outer)
        return self.make_icon(draw)

    def icon_undo(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawArc(5, 8, 18, 18, 90 * 16, 270 * 16)
            p.drawLine(8, 10, 5, 15)
            p.drawLine(8, 10, 11, 10)
        return self.make_icon(draw)

    def icon_redo(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawArc(8, 8, 18, 18, 180 * 16, 270 * 16)
            p.drawLine(23, 10, 25, 15)
            p.drawLine(23, 10, 19, 10)
        return self.make_icon(draw)

    def icon_save(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 5, 18, 20)
            p.drawLine(6, 11, 24, 11)
            p.drawRect(10, 15, 10, 8)
        return self.make_icon(draw)

    def icon_open(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 13, 18, 10)
            p.drawLine(15, 6, 15, 16)
            p.drawLine(11, 10, 15, 6)
            p.drawLine(19, 10, 15, 6)
        return self.make_icon(draw)

    def icon_export_xyz(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.3)
            p.setPen(pen)
            p.drawRect(7, 8, 10, 12)
            p.drawLine(17, 8, 23, 12)
            p.drawLine(17, 20, 23, 24)
            p.drawLine(23, 12, 23, 24)
            p.drawLine(7, 8, 13, 12)
            p.drawLine(13, 12, 23, 12)
            p.drawLine(7, 20, 13, 24)
            p.drawLine(13, 24, 23, 24)
        return self.make_icon(draw)

    def icon_add_sheet(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 7, 18, 16)
            p.drawLine(15, 10, 15, 20)
            p.drawLine(10, 15, 20, 15)
            p.drawLine(9, 25, 21, 25)
        return self.make_icon(draw)

    def icon_templates(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            chair = self.chair_icon_points(self.chair_icon_rect())
            if not chair.isEmpty():
                p.drawPolygon(chair)
        return self.make_icon(draw)

    def icon_info(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawEllipse(7, 7, 16, 16)
            p.drawLine(15, 13, 15, 19)
            p.drawPoint(15, 10)
        return self.make_icon(draw)

    def icon_bond_double(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawLine(5, 11, 25, 11)
            p.drawLine(5, 19, 25, 19)
        return self.make_icon(draw)

    def icon_bond_triple(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 10, 25, 10)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(5, 20, 25, 20)
        return self.make_icon(draw)

    def icon_bond_wedge(self) -> QIcon:
        def draw(p):
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
            half_width = self.window.canvas.renderer.bold_bond_pen().widthF() * 0.5 * 0.95
            p1 = start
            p2 = QPointF(end.x() + nx * half_width, end.y() + ny * half_width)
            p3 = QPointF(end.x() - nx * half_width, end.y() - ny * half_width)
            polygon = QPolygonF([p1, p2, p3])
            p.setPen(self.window.canvas.renderer.bond_pen())
            p.setBrush(QBrush(QColor(self.window.canvas.renderer.style.bond_color)))
            p.drawPolygon(polygon)
        return self.make_icon(draw)

    def icon_bond_hash(self) -> QIcon:
        def draw(p):
            start = QPointF(7, 23)
            end = QPointF(23, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = math.hypot(dx, dy) or 1.0
            nx = -dy / length
            ny = dx / length
            count = max(3, int(length / self.window.canvas.renderer.style.hash_spacing_px))
            max_size = self.window.canvas.renderer.bold_bond_pen().widthF()
            t_positions = [i / (count - 1) for i in range(count)]
            t_sizes = [(i + 1) / (count + 1) for i in range(count)]
            max_t = max(t_sizes) if t_sizes else 1.0
            p.setPen(self.window.canvas.renderer.bond_pen())
            for t_pos, t_size in zip(t_positions, t_sizes):
                cx = start.x() + dx * t_pos
                cy = start.y() + dy * t_pos
                size = max_size * (t_size / max_t) if max_t > 0 else max_size
                hx = nx * size / 2.0
                hy = ny * size / 2.0
                p.drawLine(QPointF(cx - hx, cy - hy), QPointF(cx + hx, cy + hy))
        return self.make_icon(draw)

    def icon_bond_dotted(self) -> QIcon:
        def draw(p):
            pen = self.window.canvas.renderer.dotted_bond_pen()
            pen.setColor(QColor("#3d3229"))
            p.setPen(pen)
            p.drawLine(5, 15, 25, 15)
        return self.make_icon(draw)

    def icon_bond_length(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(6, 15, 24, 15)
            p.drawLine(6, 11, 6, 19)
            p.drawLine(24, 11, 24, 19)
        return self.make_icon(draw)

    def icon_arrow_preview(self, kind: str) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            if kind == "dotted":
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            if kind in {"curved_single", "curved_double"}:
                path = QPainterPath()
                path.moveTo(6, 19)
                path.quadTo(15, 6, 24, 15)
                p.drawPath(path)
                self.draw_arrow_head(p, QPointF(15, 8), QPointF(24, 15))
                if kind == "curved_double":
                    self.draw_arrow_head(p, QPointF(15, 8), QPointF(6, 19))
            elif kind == "equilibrium":
                p.drawLine(5, 11, 23, 11)
                self.draw_arrow_head(p, QPointF(5, 11), QPointF(23, 11))
                p.drawLine(23, 19, 5, 19)
                self.draw_arrow_head(p, QPointF(23, 19), QPointF(5, 19))
            elif kind == "resonance":
                p.drawLine(5, 15, 23, 15)
                self.draw_arrow_head(p, QPointF(5, 15), QPointF(23, 15))
                self.draw_arrow_head(p, QPointF(23, 15), QPointF(5, 15))
            elif kind == "inhibit":
                p.drawLine(5, 15, 23, 15)
                p.drawLine(23, 10, 23, 20)
            else:
                p.drawLine(5, 15, 23, 15)
                self.draw_arrow_head(p, QPointF(5, 15), QPointF(23, 15))
        return self.make_icon(draw)

    def draw_arrow_head(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
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

    def icon_orbital_preview(self, kind: str) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            if kind == "s":
                p.drawEllipse(9, 9, 12, 12)
            elif kind == "p":
                p.drawEllipse(6, 11, 10, 10)
                p.drawEllipse(14, 9, 10, 10)
            elif kind == "sp":
                p.drawEllipse(6, 12, 10, 10)
                p.drawEllipse(16, 8, 10, 10)
                p.drawLine(5, 18, 25, 12)
            elif kind in {"sp2", "sp3"}:
                p.drawEllipse(7, 7, 8, 8)
                p.drawEllipse(15, 7, 8, 8)
                p.drawEllipse(11, 15, 8, 8)
                if kind == "sp3":
                    p.drawEllipse(11, 2, 8, 8)
            elif kind == "d":
                p.drawEllipse(6, 10, 8, 8)
                p.drawEllipse(16, 10, 8, 8)
                p.drawEllipse(11, 5, 8, 8)
                p.drawEllipse(11, 15, 8, 8)
            else:
                p.drawEllipse(9, 9, 12, 12)
                p.drawLine(15, 9, 15, 21)
        return self.make_icon(draw)

    def icon_template_preview(self, label: str) -> QIcon:
        def draw_ring(p, sides: int):
            center = QPointF(15.0, 15.0)
            radius = 10.0
            poly = QPolygonF()
            for i in range(sides):
                angle = math.radians(360 / sides * i - 90)
                poly.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.drawPolygon(poly)

        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            lower = label.lower()
            if "cyclopropane" in lower:
                draw_ring(p, 3)
            elif "cyclobutane" in lower:
                draw_ring(p, 4)
            elif "cyclopentane" in lower or "furan" in lower or "thiophene" in lower:
                draw_ring(p, 5)
            elif "benzene" in lower or "pyridine" in lower or "pyrimidine" in lower:
                draw_ring(p, 6)
            elif "naphthalene" in lower or "anthracene" in lower or "phenanthrene" in lower:
                draw_ring(p, 6)
                draw_ring(p, 6)
                p.drawLine(12, 7, 18, 7)
            elif "crown" in lower:
                draw_ring(p, 10)
            elif "chair" in lower:
                chair = self.chair_icon_points(self.chair_icon_rect())
                if not chair.isEmpty():
                    p.drawPolygon(chair)
            elif label in {"Me", "Et", "t-Bu", "i-Pr"}:
                p.drawLine(5, 15, 15, 15)
                p.drawText(16, 18, label)
            elif label in {"Vinyl", "Allyl"}:
                p.drawLine(5, 18, 14, 12)
                p.drawLine(14, 12, 23, 18)
            elif label in {"Carboxyl", "Carbonyl"}:
                p.drawLine(5, 15, 15, 15)
                p.drawLine(15, 15, 23, 10)
                p.drawText(23, 12, "O")
            elif label in {"Nitro", "Sulfonyl"}:
                p.drawLine(5, 15, 15, 15)
                p.drawText(16, 18, "NO2" if label == "Nitro" else "SO2")
            else:
                draw_ring(p, 6)
        return self.make_icon(draw)

    @staticmethod
    def chair_icon_rect() -> QRectF:
        return QRectF(2.0, 5.5, 26.0, 19.0)

    def chair_icon_points(self, rect: QRectF) -> QPolygonF:
        angle_steep = math.radians(-68.0)
        angle_shallow = math.radians(-25.0)
        v1 = QPointF(math.cos(angle_steep), math.sin(angle_steep))
        v2 = QPointF(math.cos(angle_shallow), math.sin(angle_shallow))

        points = [
            QPointF(0.0, 0.0),
            QPointF(v1.x(), v1.y()),
            QPointF(v1.x() + 1.0, v1.y()),
            QPointF(v1.x() + 1.0 + v2.x(), v1.y() + v2.y()),
            QPointF(1.0 + v2.x(), v2.y()),
            QPointF(v2.x(), v2.y()),
        ]
        min_x = min(point.x() for point in points)
        max_x = max(point.x() for point in points)
        min_y = min(point.y() for point in points)
        max_y = max(point.y() for point in points)
        width = max_x - min_x
        height = max_y - min_y
        scale = min(rect.width() / width, rect.height() / height) * 0.92
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        center = rect.center()
        poly = QPolygonF()
        for point in points:
            poly.append(
                QPointF(
                    center.x() + (point.x() - cx) * scale,
                    center.y() + (point.y() - cy) * scale,
                )
            )
        return poly

    def icon_flip_h(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(15, 5, 15, 25)
            p.drawLine(7, 9, 13, 9)
            p.drawLine(7, 21, 13, 21)
            p.drawLine(17, 9, 23, 9)
            p.drawLine(17, 21, 23, 21)
        return self.make_icon(draw)

    def icon_flip_v(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(9, 7, 9, 13)
            p.drawLine(21, 7, 21, 13)
            p.drawLine(9, 17, 9, 23)
            p.drawLine(21, 17, 21, 23)
        return self.make_icon(draw)

    def icon_arrow(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(5, 15, 23, 15)
            p.drawLine(23, 15, 18, 11)
            p.drawLine(23, 15, 18, 19)
        return self.make_icon(draw)

    def icon_ts_bracket(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.drawLine(8, 7, 5, 7)
            p.drawLine(5, 7, 5, 23)
            p.drawLine(5, 23, 8, 23)
            p.drawLine(22, 7, 25, 7)
            p.drawLine(25, 7, 25, 23)
            p.drawLine(25, 23, 22, 23)
            font = p.font()
            font.setPixelSize(8)
            p.setFont(font)
            p.drawText(QRectF(10.0, 8.0, 12.0, 8.0), Qt.AlignmentFlag.AlignCenter, "TS")
        return self.make_icon(draw)

    def icon_orbital(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawEllipse(6, 10, 8, 10)
            p.drawEllipse(16, 10, 8, 10)
        return self.make_icon(draw)

    def icon_move(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(15, 5, 15, 25)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(15, 5, 12, 8)
            p.drawLine(15, 5, 18, 8)
            p.drawLine(15, 25, 12, 22)
            p.drawLine(15, 25, 18, 22)
            p.drawLine(5, 15, 8, 12)
            p.drawLine(5, 15, 8, 18)
            p.drawLine(25, 15, 22, 12)
            p.drawLine(25, 15, 22, 18)
        return self.make_icon(draw)

    def icon_color(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(QBrush(QColor("#d8c8a6")))
            palette = QPainterPath()
            palette.moveTo(4, 18)
            palette.cubicTo(4, 8, 15, 6, 25, 9)
            palette.cubicTo(29, 10, 29, 20, 23, 24)
            palette.cubicTo(18, 26, 11, 25, 9, 21)
            palette.cubicTo(14, 23, 15, 20, 14, 18)
            palette.cubicTo(11, 20, 6, 20, 4, 18)
            p.drawPath(palette)
            p.setBrush(QBrush(Qt.GlobalColor.white))
            p.drawEllipse(9, 13, 4, 4)
            p.drawEllipse(14, 11, 4, 4)
            p.drawEllipse(19, 15, 4, 4)
        return self.make_icon(draw)

    def icon_perspective(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            cx, cy, r = 15.0, 15.0, 10.0
            start_deg = 40.0
            span_deg = 280.0
            end_deg = (start_deg + span_deg) % 360.0
            p.drawArc(5, 5, 20, 20, int(start_deg * 16), int(span_deg * 16))
            rad = math.radians(end_deg)
            end = QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))
            tangent = rad + math.pi / 2.0
            head_len = 3.0
            head_angle = math.radians(25.0)
            left = QPointF(
                end.x() + head_len * math.cos(tangent + math.pi + head_angle),
                end.y() - head_len * math.sin(tangent + math.pi + head_angle),
            )
            right = QPointF(
                end.x() + head_len * math.cos(tangent + math.pi - head_angle),
                end.y() - head_len * math.sin(tangent + math.pi - head_angle),
            )
            p.drawLine(end, left)
            p.drawLine(end, right)
        return self.make_icon(draw)


__all__ = ["MainWindowIconFactory"]
