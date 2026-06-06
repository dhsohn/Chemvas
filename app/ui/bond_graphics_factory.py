from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF

from ui.graphics_items import NoSelectLineItem, NoSelectPathItem, NoSelectPolygonItem


class BondGraphicsFactory:
    def __init__(self, renderer) -> None:
        self.renderer = renderer

    @property
    def _bond_color(self) -> str:
        return self.renderer.style.bond_color

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        dotted: bool = False,
    ) -> NoSelectLineItem:
        item = NoSelectLineItem(x1, y1, x2, y2)
        pen = self.renderer.dotted_bond_pen() if dotted else self.renderer.bond_pen()
        item.setPen(pen)
        return item

    def filled_polygon(
        self,
        polygon: QPolygonF,
        *,
        pen: QPen | None = None,
        color: QColor | str | None = None,
    ) -> NoSelectPolygonItem:
        item = NoSelectPolygonItem(polygon)
        item.setPen(pen if pen is not None else QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(color or self._bond_color)))
        return item

    def path_fill(
        self,
        path: QPainterPath,
        *,
        color: QColor | str | None = None,
    ) -> NoSelectPathItem:
        item = NoSelectPathItem(path)
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(color or self._bond_color)))
        return item


__all__ = ["BondGraphicsFactory"]
