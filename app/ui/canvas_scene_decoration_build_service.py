from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsTextItem

from ui.canvas_arrow_build_service import CanvasArrowBuildService
from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.graphics_items import (
    AtomDotItem,
    AtomLabelItem,
    NoSelectLineItem,
    NoSelectPathItem,
)
from ui.mark_item_access import mark_selection_radius_for
from ui.renderer_style_access import (
    atom_color_for,
    atom_font_for,
    bond_color_for,
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
    font_family_for,
    orbital_alpha_for,
    orbital_negative_color_for,
    orbital_positive_color_for,
)
from ui.scene_item_access import add_item_to_canvas_scene


class CanvasSceneDecorationBuildService:
    def __init__(self, canvas, *, arrow_build_service=None) -> None:
        self.canvas = canvas
        self.arrow_build_service = arrow_build_service or CanvasArrowBuildService(canvas)

    def build_mark_item(self, kind: str):
        selection_radius = mark_selection_radius_for(self.canvas)
        if kind == "radical":
            radius = max(1.2, bond_line_width_for(self.canvas) * 0.7)
            hit_padding = max(0.0, selection_radius - radius)
            item = AtomDotItem(-radius, -radius, radius * 2.0, radius * 2.0, hit_padding=hit_padding)
            item.setBrush(QColor(atom_color_for(self.canvas)))
            item.setPen(QPen(Qt.PenStyle.NoPen))
            return item
        if kind in {"plus", "minus"}:
            text_item = AtomLabelItem(hit_radius=selection_radius)
            text_item.setFont(atom_font_for(self.canvas))
            text_item.setDefaultTextColor(QColor(atom_color_for(self.canvas)))
            text_item.setPlainText("+" if kind == "plus" else "-")
            return text_item
        return None

    def mark_center(self, item) -> QPointF:
        if isinstance(item, QGraphicsTextItem):
            rect = item.boundingRect()
            return QPointF(item.pos().x() + rect.center().x(), item.pos().y() + rect.center().y())
        return item.pos()

    def set_mark_center(self, item, center: QPointF) -> None:
        if isinstance(item, QGraphicsTextItem):
            rect = item.boundingRect()
            item.setPos(center.x() - rect.center().x(), center.y() - rect.center().y())
            return
        item.setPos(center)

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        return self.arrow_build_service.preview_arrow(start, end, kind)

    def build_arrow_item(self, start: QPointF, end: QPointF, kind: str) -> QGraphicsPathItem:
        return self.arrow_build_service.build_arrow_item(start, end, kind)

    def build_single_head_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_single_head_arrow(start, end)

    def build_double_head_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_double_head_arrow(start, end)

    def build_dotted_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_dotted_arrow(start, end)

    def build_curved_arrow(self, start: QPointF, end: QPointF, double: bool) -> QGraphicsPathItem:
        return self.arrow_build_service.build_curved_arrow(start, end, double)

    def build_inhibition_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_inhibition_arrow(start, end)

    def build_equilibrium_item(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_equilibrium_item(start, end)

    def add_arrow_head(self, path: QPainterPath, start: QPointF, end: QPointF, double: bool) -> None:
        self.arrow_build_service.add_arrow_head(path, start, end, double)

    def ts_bracket_rect_from_points(self, start: QPointF, end: QPointF) -> QRectF:
        rect = QRectF(start, end).normalized()
        min_width = bond_length_px_for(self.canvas) * 1.8
        min_height = bond_length_px_for(self.canvas) * 2.4
        if rect.width() < 4.0 and rect.height() < 4.0:
            return QRectF(
                start.x() - min_width / 2.0,
                start.y() - min_height / 2.0,
                min_width,
                min_height,
            )
        center = rect.center()
        width = max(rect.width(), min_width)
        height = max(rect.height(), min_height)
        return QRectF(center.x() - width / 2.0, center.y() - height / 2.0, width, height)

    def ts_bracket_stroke_width(self) -> float:
        return max(0.8, bond_line_width_for(self.canvas) * 0.58)

    def ts_bracket_path(self, rect: QRectF) -> QPainterPath:
        rect = QRectF(rect).normalized()
        hook = min(rect.width() * 0.18, bond_length_px_for(self.canvas) * 0.55)
        hook = max(hook, bond_length_px_for(self.canvas) * 0.28)
        bracket_lines = QPainterPath()
        bracket_lines.moveTo(rect.left() + hook, rect.top())
        bracket_lines.lineTo(rect.left(), rect.top())
        bracket_lines.lineTo(rect.left(), rect.bottom())
        bracket_lines.lineTo(rect.left() + hook, rect.bottom())
        bracket_lines.moveTo(rect.right() - hook, rect.top())
        bracket_lines.lineTo(rect.right(), rect.top())
        bracket_lines.lineTo(rect.right(), rect.bottom())
        bracket_lines.lineTo(rect.right() - hook, rect.bottom())

        stroker = QPainterPathStroker()
        stroker.setWidth(self.ts_bracket_stroke_width())
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        path = stroker.createStroke(bracket_lines)

        font = QFont(font_family_for(self.canvas))
        font.setPixelSize(
            max(
                10,
                round(min(rect.height() * 0.22, bond_length_px_for(self.canvas) * 0.95)),
            )
        )
        path.addText(
            rect.right() + hook * 0.18,
            rect.top() + font.pixelSize() * 0.18,
            font,
            "\u2021",
        )
        return path

    def build_ts_bracket_item(self, rect: QRectF) -> QGraphicsPathItem:
        normalized = QRectF(rect).normalized()
        item = NoSelectPathItem(self.ts_bracket_path(normalized))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(bond_color_for(self.canvas))))
        item.setData(0, "ts_bracket")
        item.setData(1, {"rect": normalized})
        return item

    def preview_ts_bracket(self, start: QPointF, end: QPointF):
        item = self.build_ts_bracket_item(self.ts_bracket_rect_from_points(start, end))
        preview_color = QColor(120, 120, 120, 140)
        item.setBrush(QBrush(preview_color))
        return add_item_to_canvas_scene(self.canvas, item)

    def build_orbital_items(self, center: QPointF, kind: str):
        radius = bond_length_px_for(self.canvas) * 0.35
        pen = bond_pen_for(self.canvas)
        pos_color = QColor(orbital_positive_color_for(self.canvas))
        neg_color = QColor(orbital_negative_color_for(self.canvas))
        pos_color.setAlphaF(orbital_alpha_for(self.canvas))
        neg_color.setAlphaF(orbital_alpha_for(self.canvas))
        phase_enabled = tool_settings_state_for(self.canvas).orbital_phase_enabled

        def _ellipse_item(cx, cy, rx, ry, fill=None):
            item = QGraphicsEllipseItem(cx - rx, cy - ry, rx * 2, ry * 2)
            item.setPen(pen)
            if fill is not None:
                item.setBrush(fill)
            return item

        items = []
        if kind == "s":
            fill = pos_color if phase_enabled else None
            items.append(_ellipse_item(center.x(), center.y(), radius, radius, fill))
            return items
        if kind == "p":
            fill1 = pos_color if phase_enabled else None
            fill2 = neg_color if phase_enabled else None
            items.append(_ellipse_item(center.x() - radius, center.y(), radius, radius * 0.7, fill1))
            items.append(_ellipse_item(center.x() + radius, center.y(), radius, radius * 0.7, fill2))
            return items
        if kind == "sp":
            fill1 = pos_color if phase_enabled else None
            fill2 = neg_color if phase_enabled else None
            items.append(_ellipse_item(center.x() - radius * 1.2, center.y(), radius * 1.2, radius * 0.7, fill1))
            items.append(_ellipse_item(center.x() + radius * 0.6, center.y(), radius * 0.6, radius * 0.4, fill2))
            return items
        if kind == "sp2":
            fill = pos_color if phase_enabled else None
            for angle in [0, 120, 240]:
                rad = math.radians(angle)
                cx = center.x() + math.cos(rad) * radius * 1.1
                cy = center.y() + math.sin(rad) * radius * 1.1
                items.append(_ellipse_item(cx, cy, radius * 0.75, radius * 0.5, fill))
            return items
        if kind == "sp3":
            fill = pos_color if phase_enabled else None
            for angle in [45, 135, 225, 315]:
                rad = math.radians(angle)
                cx = center.x() + math.cos(rad) * radius * 1.1
                cy = center.y() + math.sin(rad) * radius * 1.1
                items.append(_ellipse_item(cx, cy, radius * 0.7, radius * 0.45, fill))
            return items
        if kind == "d":
            fill1 = pos_color if phase_enabled else None
            fill2 = neg_color if phase_enabled else None
            for angle, fill in [(45, fill1), (135, fill2), (225, fill1), (315, fill2)]:
                rad = math.radians(angle)
                cx = center.x() + math.cos(rad) * radius * 1.1
                cy = center.y() + math.sin(rad) * radius * 1.1
                items.append(_ellipse_item(cx, cy, radius * 0.7, radius * 0.45, fill))
            return items
        if kind == "mo_bonding":
            fill = pos_color if phase_enabled else None
            items.append(_ellipse_item(center.x() - radius, center.y(), radius, radius * 0.7, fill))
            items.append(_ellipse_item(center.x() + radius, center.y(), radius, radius * 0.7, fill))
            return items
        if kind == "mo_antibonding":
            fill1 = pos_color if phase_enabled else None
            fill2 = neg_color if phase_enabled else None
            items.append(_ellipse_item(center.x() - radius, center.y(), radius, radius * 0.7, fill1))
            items.append(_ellipse_item(center.x() + radius, center.y(), radius, radius * 0.7, fill2))
            node = NoSelectLineItem(center.x(), center.y() - radius * 0.8, center.x(), center.y() + radius * 0.8)
            node.setPen(pen)
            items.append(node)
            return items
        return items

    def arrow_pen(self, dotted: bool = False):
        return self.arrow_build_service.arrow_pen(dotted=dotted)


__all__ = ["CanvasSceneDecorationBuildService"]
