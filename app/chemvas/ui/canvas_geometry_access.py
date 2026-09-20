from __future__ import annotations

from chemvas.ui.scene_render_access import scene_render_context_for


def mark_target_distance_for_atom_for(
    canvas,
    atom_id: int,
    direction_x: float,
    direction_y: float,
    kind: str,
) -> float:
    return scene_render_context_for(canvas).geometry.mark_target_distance_for_atom(
        atom_id, direction_x, direction_y, kind
    )


__all__ = [
    "mark_target_distance_for_atom_for",
]
