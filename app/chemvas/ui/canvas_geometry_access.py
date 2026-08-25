from __future__ import annotations

from chemvas.ui.canvas_service_access import optional_canvas_service_method
from chemvas.ui.canvas_service_ports import geometry_controller_for_access


def _geometry_method(canvas, name: str):
    return optional_canvas_service_method(canvas, geometry_controller_for_access, name)


def mark_target_distance_for_atom_for(
    canvas,
    atom_id: int,
    direction_x: float,
    direction_y: float,
    kind: str,
) -> float:
    method = _geometry_method(canvas, "mark_target_distance_for_atom")
    if method is not None:
        return method(atom_id, direction_x, direction_y, kind)
    return 0.0


__all__ = [
    "mark_target_distance_for_atom_for",
]
