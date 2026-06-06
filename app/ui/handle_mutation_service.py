from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.handle_interaction_logic import (
    orbital_rotation_angle as orbital_rotation_angle_helper,
)
from ui.handle_interaction_logic import (
    orbital_scale_factor as orbital_scale_factor_helper,
)
from ui.handle_mutation_access import (
    clamp_curved_midpoint_for,
    control_from_midpoint_for,
    default_curved_control_for,
    orbital_snap_enabled_for,
    orbital_snap_step_for,
)
from ui.renderer_style_access import bond_length_px_for
from ui.selection_service_access import refresh_selection_outline_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class HandleMutationService:
    def __init__(self, canvas: CanvasView, *, curved_arrow_path_service=None) -> None:
        self.canvas = canvas
        self.curved_arrow_path_service = curved_arrow_path_service

    def update_orbital_scale(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", bond_length_px_for(self.canvas) * 0.8)
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
            snap_enabled=orbital_snap_enabled_for(self.canvas),
            snap_step=orbital_snap_step_for(self.canvas),
        )
        item.setRotation(angle)

    def update_curved_control(self, item, pos: QPointF) -> None:
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        double = data.get("double", False)
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        mid = clamp_curved_midpoint_for(self.canvas, start, end, pos)
        control = control_from_midpoint_for(self.canvas, start, end, mid)
        if self.curved_arrow_path_service is not None:
            self.curved_arrow_path_service.set_curved_arrow_path(item, start, end, control, double)
        data["control"] = control
        item.setData(2, data)
        refresh_selection_outline_for(self.canvas)

    def update_curved_endpoint(self, item, pos: QPointF, endpoint: str) -> None:
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        control = data.get("control")
        double = data.get("double", False)
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        if endpoint == "start":
            start = QPointF(pos)
        elif endpoint == "end":
            end = QPointF(pos)
        else:
            return
        if not isinstance(control, QPointF):
            control = default_curved_control_for(self.canvas, start, end)
        if self.curved_arrow_path_service is not None:
            self.curved_arrow_path_service.set_curved_arrow_path(item, start, end, control, double)
        data["start"] = start
        data["end"] = end
        data["control"] = control
        item.setData(2, data)
        refresh_selection_outline_for(self.canvas)


__all__ = ["HandleMutationService"]
