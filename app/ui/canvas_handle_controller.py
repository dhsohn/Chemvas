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
from ui.handle_mutation_service import handle_mutation_service_for
from ui.handle_overlay_service import handle_overlay_service_for
from ui.selection_highlight_styler import selection_highlight_styler_for


class CanvasHandleController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def clear_handles(self) -> None:
        handle_overlay_service_for(self.canvas).clear_handles()

    def show_orbital_handles(self, item) -> None:
        handle_overlay_service_for(self.canvas).show_orbital_handles(item)

    def show_curved_handles(self, item) -> None:
        handle_overlay_service_for(self.canvas).show_curved_handles(item)

    def create_handle(self, pos: QPointF, handle_type: str, target):
        return handle_overlay_service_for(self.canvas).create_handle(pos, handle_type, target)

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
        elif handle_type == "curved_start":
            self.canvas._update_curved_endpoint(target, scene_pos, "start")
            self.canvas.show_curved_handles(target)
        elif handle_type == "curved_end":
            self.canvas._update_curved_endpoint(target, scene_pos, "end")
            self.canvas.show_curved_handles(target)

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        handle_mutation_service_for(self.canvas).update_orbital_scale(item, pos)

    def update_orbital_rotate(self, item, pos: QPointF) -> None:
        handle_mutation_service_for(self.canvas).update_orbital_rotate(item, pos)

    def update_curved_control(self, item, pos: QPointF) -> None:
        handle_mutation_service_for(self.canvas).update_curved_control(item, pos)

    def update_curved_endpoint(self, item, pos: QPointF, endpoint: str) -> None:
        handle_mutation_service_for(self.canvas).update_curved_endpoint(item, pos, endpoint)

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
        selection_highlight_styler_for(self.canvas).set_selection_highlight(items)

    def clear_selection_highlight(self) -> None:
        selection_highlight_styler_for(self.canvas).clear_selection_highlight()

    def apply_selection_style(self, item, selected: bool) -> None:
        selection_highlight_styler_for(self.canvas).apply_selection_style(item, selected)
