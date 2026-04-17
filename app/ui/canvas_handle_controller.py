from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItemGroup

from ui.handle_interaction_logic import (
    clamp_curved_midpoint as clamp_curved_midpoint_helper,
    clear_handle_items as clear_handle_items_helper,
    control_from_midpoint as control_from_midpoint_helper,
    create_handle_item as create_handle_item_helper,
    curved_midpoint as curved_midpoint_helper,
    default_curved_control as default_curved_control_helper,
    orbital_handle_positions as orbital_handle_positions_helper,
    orbital_rotation_angle as orbital_rotation_angle_helper,
    orbital_scale_factor as orbital_scale_factor_helper,
)


class CanvasHandleController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def clear_handles(self) -> None:
        self.canvas._active_handles = clear_handle_items_helper(self.canvas.scene(), self.canvas._active_handles)
        self.canvas._handle_target = None
        self.canvas._clear_selection_highlight()

    def show_orbital_handles(self, item) -> None:
        self.clear_handles()
        self.canvas._set_selection_highlight([item])
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", self.canvas.renderer.style.bond_length_px * 0.8)
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        scale_pos, rotate_pos = orbital_handle_positions_helper(center, float(base_dist))
        self.canvas._active_handles = [
            self.canvas._create_handle(scale_pos, "orbital_scale", item),
            self.canvas._create_handle(rotate_pos, "orbital_rotate", item),
        ]
        self.canvas._handle_target = item

    def show_curved_handles(self, item) -> None:
        self.clear_handles()
        self.canvas._set_selection_highlight([item])
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        control = data.get("control")
        if isinstance(start, QPointF) and isinstance(end, QPointF):
            if not isinstance(control, QPointF):
                control = self.canvas._default_curved_control(start, end)
            mid = self.canvas._curved_midpoint(start, control, end)
            self.canvas._update_curved_control(item, mid)
            mid = self.canvas._curved_midpoint(start, item.data(2).get("control"), end)
        else:
            mid = item.boundingRect().center()
        self.canvas._active_handles = [self.canvas._create_handle(mid, "curved_control", item)]
        self.canvas._handle_target = item

    def create_handle(self, pos: QPointF, handle_type: str, target):
        handle = create_handle_item_helper(pos, handle_type, target)
        self.canvas.scene().addItem(handle)
        return handle

    def update_handle_drag(self, handle, scene_pos: QPointF) -> None:
        handle_type = handle.data(1)
        target = handle.data(2)
        if target is None:
            return
        if handle_type == "orbital_scale":
            self.canvas._update_orbital_scale(target, scene_pos)
            self.canvas.show_orbital_handles(target)
        elif handle_type == "orbital_rotate":
            self.canvas._update_orbital_rotate(target, scene_pos)
            self.canvas.show_orbital_handles(target)
        elif handle_type == "curved_control":
            self.canvas._update_curved_control(target, scene_pos)
            self.canvas.show_curved_handles(target)

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", self.canvas.renderer.style.bond_length_px * 0.8)
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        scale = orbital_scale_factor_helper(center, pos, float(base_dist))
        item.setScale(scale)

    def update_orbital_rotate(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        angle = orbital_rotation_angle_helper(
            center,
            pos,
            snap_enabled=self.canvas._orbital_snap_enabled,
            snap_step=self.canvas._orbital_snap_step,
        )
        item.setRotation(angle)

    def update_curved_control(self, item, pos: QPointF) -> None:
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        double = data.get("double", False)
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        mid = self.canvas._clamp_curved_midpoint(start, end, pos)
        control = self.canvas._control_from_midpoint(start, end, mid)
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self.canvas._add_arrow_head(path, control, end, double=False)
            self.canvas._add_arrow_head(path, control, start, double=False)
        else:
            self.canvas._add_arrow_head(path, control, end, double=False)
        item.setPath(path)
        data["control"] = control
        item.setData(2, data)
        self.canvas._update_selection_outline()

    def default_curved_control(self, start: QPointF, end: QPointF) -> QPointF:
        return default_curved_control_helper(start, end)

    def curved_midpoint(self, start: QPointF, control: QPointF, end: QPointF) -> QPointF:
        return curved_midpoint_helper(start, control, end)

    def control_from_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        return control_from_midpoint_helper(start, end, mid)

    def clamp_curved_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        snap_distance = None
        if self.canvas._curved_snap:
            snap_distance = self.canvas.renderer.style.bond_length_px * self.canvas._curved_snap_step
        return clamp_curved_midpoint_helper(
            start,
            end,
            mid,
            snap_enabled=self.canvas._curved_snap,
            snap_distance=snap_distance,
        )

    def set_selection_highlight(self, items: list) -> None:
        self.canvas._clear_selection_highlight()
        self.canvas._selected_items = items
        for item in items:
            self.canvas._apply_selection_style(item, True)

    def clear_selection_highlight(self) -> None:
        for item in self.canvas._selected_items:
            self.canvas._apply_selection_style(item, False)
        self.canvas._selected_items = []

    def apply_selection_style(self, item, selected: bool) -> None:
        if isinstance(item, QGraphicsItemGroup):
            for child in item.childItems():
                self.canvas._apply_selection_style(child, selected)
            return
        if hasattr(item, "pen"):
            pen = item.pen()
            if selected:
                item.setData(6, pen)
                pen.setColor(self.canvas._selection_color)
                pen.setWidthF(pen.widthF() + self.canvas._selection_stroke_delta)
                item.setPen(pen)
            else:
                original = item.data(6)
                if isinstance(original, QPen):
                    item.setPen(original)
