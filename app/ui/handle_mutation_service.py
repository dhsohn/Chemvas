from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.curved_arrow_path_service import curved_arrow_path_service_for
from ui.handle_interaction_logic import (
    orbital_rotation_angle as orbital_rotation_angle_helper,
)
from ui.handle_interaction_logic import (
    orbital_scale_factor as orbital_scale_factor_helper,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class HandleMutationService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

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
        curved_arrow_path_service_for(self.canvas).set_curved_arrow_path(item, start, end, control, double)
        data["control"] = control
        item.setData(2, data)
        self.canvas._update_selection_outline()

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
            control = self.canvas._default_curved_control(start, end)
        curved_arrow_path_service_for(self.canvas).set_curved_arrow_path(item, start, end, control, double)
        data["start"] = start
        data["end"] = end
        data["control"] = control
        item.setData(2, data)
        self.canvas._update_selection_outline()


def handle_mutation_service_for(canvas) -> HandleMutationService:
    return canvas._handle_mutation_service


__all__ = ["HandleMutationService", "handle_mutation_service_for"]
