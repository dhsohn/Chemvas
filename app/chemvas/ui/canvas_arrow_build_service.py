from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QPainterPath

from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.graphics_items import NoSelectPathItem
from chemvas.ui.renderer_style_access import (
    bond_length_px_for,
    bond_pen_for,
    bond_spacing_px_for,
)
from chemvas.ui.scene_item_access import add_item_to_canvas_scene


class CanvasArrowBuildService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    @property
    def settings(self):
        return tool_settings_state_for(self.canvas)

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        item = self.build_arrow_item(start, end, kind)
        return add_item_to_canvas_scene(self.canvas, item)

    def build_arrow_item(self, start: QPointF, end: QPointF, kind: str):
        if kind == "equilibrium":
            return self.build_equilibrium_item(start, end)
        if kind == "resonance":
            return self.build_double_head_arrow(start, end)
        if kind == "curved_single":
            return self.build_curved_arrow(start, end, double=False)
        if kind == "curved_double":
            return self.build_curved_arrow(start, end, double=True)
        if kind == "inhibit":
            return self.build_inhibition_arrow(start, end)
        if kind == "dotted":
            return self.build_dotted_arrow(start, end)
        return self.build_single_head_arrow(start, end)

    def build_single_head_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_double_head_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        self.add_arrow_head(path, end, start, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_dotted_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen(dotted=True))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_curved_arrow(self, start: QPointF, end: QPointF, double: bool):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        control = QPointF(
            start.x() + dx * 0.5 + nx * length * 0.3,
            start.y() + dy * 0.5 + ny * length * 0.3,
        )
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self.add_arrow_head(path, control, end, double=False)
            self.add_arrow_head(path, control, start, double=False)
        else:
            self.add_arrow_head(path, control, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(
            2, {"start": start, "end": end, "control": control, "double": double}
        )
        return item

    def build_inhibition_arrow(self, start: QPointF, end: QPointF):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        bar = bond_length_px_for(self.canvas) * 0.2

        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        bar_start = QPointF(end.x() - nx * bar, end.y() - ny * bar)
        bar_end = QPointF(end.x() + nx * bar, end.y() + ny * bar)
        path.moveTo(bar_start)
        path.lineTo(bar_end)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_equilibrium_item(self, start: QPointF, end: QPointF):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        offset = bond_spacing_px_for(self.canvas) * 1.5
        start_up = QPointF(start.x() + nx * offset, start.y() + ny * offset)
        end_up = QPointF(end.x() + nx * offset, end.y() + ny * offset)
        start_down = QPointF(start.x() - nx * offset, start.y() - ny * offset)
        end_down = QPointF(end.x() - nx * offset, end.y() - ny * offset)

        path = QPainterPath()
        path.addPath(self.build_single_head_arrow(start_up, end_up).path())
        path.addPath(self.build_single_head_arrow(end_down, start_down).path())

        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def add_arrow_head(
        self, path: QPainterPath, start: QPointF, end: QPointF, double: bool
    ) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = bond_length_px_for(self.canvas) * self.settings.arrow_head_scale
        head_angle = math.radians(25)
        offsets = [0.0]
        if double:
            offset_mag = max(1.4, self.settings.arrow_line_width * 1.2)
            offsets = [-offset_mag, offset_mag]
        for offset in offsets:
            dx = math.cos(angle + math.pi / 2) * offset
            dy = math.sin(angle + math.pi / 2) * offset
            tip = QPointF(end.x() + dx, end.y() + dy) if double else end
            left = QPointF(
                tip.x() - head_len * math.cos(angle - head_angle),
                tip.y() - head_len * math.sin(angle - head_angle),
            )
            right = QPointF(
                tip.x() - head_len * math.cos(angle + head_angle),
                tip.y() - head_len * math.sin(angle + head_angle),
            )
            path.moveTo(left)
            path.lineTo(tip)
            path.lineTo(right)

    def arrow_pen(self, dotted: bool = False):
        pen = bond_pen_for(self.canvas)
        pen.setWidthF(self.settings.arrow_line_width)
        if dotted:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen


__all__ = ["CanvasArrowBuildService"]
