from __future__ import annotations

from chemvas.ui.canvas_service_ports import geometry_controller_for_access


def mark_target_distance_for_atom_for(
    canvas,
    atom_id: int,
    direction_x: float,
    direction_y: float,
    kind: str,
) -> float:
    return geometry_controller_for_access(canvas).mark_target_distance_for_atom(
        atom_id, direction_x, direction_y, kind
    )


__all__ = [
    "mark_target_distance_for_atom_for",
]
