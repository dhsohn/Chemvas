from __future__ import annotations

from PyQt6.QtCore import QPointF

from chemvas.ui.main_window_icon_geometry import (
    chair_icon_points,
    chair_icon_rect,
    template_preview_ring_polygon,
    template_preview_ring_sides,
)


class MainWindowTemplateIconRenderer:
    def __init__(
        self,
        *,
        icon_pen,
        stroke_regular: float,
        stroke_thin: float,
    ) -> None:
        self._icon_pen = icon_pen
        self._stroke_regular = stroke_regular
        self._stroke_thin = stroke_thin

    def draw_templates(self, painter) -> None:
        painter.setPen(self._icon_pen(self._stroke_regular))
        chair = chair_icon_points(chair_icon_rect())
        if not chair.isEmpty():
            painter.drawPolygon(chair)

    def draw_template_preview(self, painter, label: str) -> None:
        def draw_ring(sides: int) -> None:
            painter.drawPolygon(template_preview_ring_polygon(sides))

        def draw_benzene() -> None:
            center = QPointF(15.0, 15.0)
            polygon = template_preview_ring_polygon(6)
            painter.drawPolygon(polygon)
            for index in range(0, polygon.count(), 2):
                start = polygon[index]
                end = polygon[(index + 1) % polygon.count()]
                painter.drawLine(
                    _toward_center(start, center), _toward_center(end, center)
                )

        painter.setPen(self._icon_pen(self._stroke_thin))
        lower = label.lower()
        if "benzene" in lower:
            draw_benzene()
            return
        ring_sides = template_preview_ring_sides(label)
        if ring_sides is not None:
            draw_ring(ring_sides)
        elif "naphthalene" in lower or "anthracene" in lower or "phenanthrene" in lower:
            draw_ring(6)
            draw_ring(6)
            painter.drawLine(12, 7, 18, 7)
        elif "chair" in lower:
            chair = chair_icon_points(chair_icon_rect())
            if not chair.isEmpty():
                painter.drawPolygon(chair)
        elif label in {"Me", "Et", "t-Bu", "i-Pr"}:
            painter.drawLine(5, 15, 15, 15)
            painter.drawText(16, 18, label)
        elif label in {"Vinyl", "Allyl"}:
            painter.drawLine(5, 18, 14, 12)
            painter.drawLine(14, 12, 23, 18)
        elif label in {"Carboxyl", "Carbonyl"}:
            painter.drawLine(5, 15, 15, 15)
            painter.drawLine(15, 15, 23, 10)
            painter.drawText(23, 12, "O")
        elif label in {"Nitro", "Sulfonyl"}:
            painter.drawLine(5, 15, 15, 15)
            painter.drawText(16, 18, "NO2" if label == "Nitro" else "SO2")
        else:
            draw_ring(6)


def _toward_center(point: QPointF, center: QPointF, amount: float = 0.22) -> QPointF:
    return QPointF(
        point.x() + (center.x() - point.x()) * amount,
        point.y() + (center.y() - point.y()) * amount,
    )


__all__ = ["MainWindowTemplateIconRenderer"]
