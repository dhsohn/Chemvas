from __future__ import annotations

from PyQt6.QtCore import QPointF

from ui.handle_interaction_logic import (
    clamp_curved_midpoint as clamp_curved_midpoint_helper,
)
from ui.handle_interaction_logic import (
    control_from_midpoint as control_from_midpoint_helper,
)
from ui.handle_interaction_logic import (
    curved_midpoint as curved_midpoint_helper,
)
from ui.handle_interaction_logic import (
    default_curved_control as default_curved_control_helper,
)
from ui.handle_mutation_access import curved_snap_distance_for, curved_snap_enabled_for
from ui.selection_highlight_styler import selection_highlight_styler_for


class CanvasHandleController:
    def __init__(self, canvas, *, handle_overlay_service=None, handle_mutation_service=None) -> None:
        self.canvas = canvas
        self.handle_overlay_service = handle_overlay_service
        self.handle_mutation_service = handle_mutation_service

    def clear_handles(self) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.clear_handles()

    def show_orbital_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_orbital_handles(item)

    def show_curved_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_curved_handles(item)

    def show_shape_handles(self, item) -> None:
        if self.handle_overlay_service is not None:
            self.handle_overlay_service.show_shape_handles(item)

    def create_handle(self, pos: QPointF, handle_type: str, target):
        if self.handle_overlay_service is None:
            return None
        return self.handle_overlay_service.create_handle(pos, handle_type, target)

    def update_handle_drag(self, handle, scene_pos: QPointF) -> None:
        handle_type = handle.data(1)
        target = handle.data(2)
        if target is None:
            return
        if handle_type == "orbital_scale":
            self.update_orbital_scale(target, scene_pos)
            self.show_orbital_handles(target)
        elif handle_type == "orbital_rotate":
            self.update_orbital_rotate(target, scene_pos)
            self.show_orbital_handles(target)
        elif handle_type == "curved_control":
            self.update_curved_control(target, scene_pos)
            self.show_curved_handles(target)
        elif handle_type == "curved_start":
            self.update_curved_endpoint(target, scene_pos, "start")
            self.show_curved_handles(target)
        elif handle_type == "curved_end":
            self.update_curved_endpoint(target, scene_pos, "end")
            self.show_curved_handles(target)
        elif handle_type.startswith("shape_"):
            self.update_shape_resize(target, handle_type, scene_pos)
            self.show_shape_handles(target)

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_orbital_scale(item, pos)

    def update_orbital_rotate(self, item, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_orbital_rotate(item, pos)

    def update_curved_control(self, item, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_curved_control(item, pos)

    def update_shape_resize(self, item, anchor: str, pos: QPointF) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_shape_resize(item, anchor, pos)

    def update_curved_endpoint(self, item, pos: QPointF, endpoint: str) -> None:
        if self.handle_mutation_service is not None:
            self.handle_mutation_service.update_curved_endpoint(item, pos, endpoint)

    def default_curved_control(self, start: QPointF, end: QPointF) -> QPointF:
        return default_curved_control_helper(start, end)

    def curved_midpoint(self, start: QPointF, control: QPointF, end: QPointF) -> QPointF:
        return curved_midpoint_helper(start, control, end)

    def control_from_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        return control_from_midpoint_helper(start, end, mid)

    def clamp_curved_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        snap_enabled = curved_snap_enabled_for(self.canvas)
        snap_distance = None
        if snap_enabled:
            snap_distance = curved_snap_distance_for(self.canvas)
        return clamp_curved_midpoint_helper(
            start,
            end,
            mid,
            snap_enabled=snap_enabled,
            snap_distance=snap_distance,
        )

    def set_selection_highlight(self, items: list) -> None:
        selection_highlight_styler_for(self.canvas).set_selection_highlight(items)

    def clear_selection_highlight(self) -> None:
        selection_highlight_styler_for(self.canvas).clear_selection_highlight()

    def apply_selection_style(self, item, selected: bool) -> None:
        selection_highlight_styler_for(self.canvas).apply_selection_style(item, selected)


__all__ = ["CanvasHandleController"]
