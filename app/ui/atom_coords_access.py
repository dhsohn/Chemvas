from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ui.bond_graphics_access import project_point_3d_for
from ui.canvas_model_access import atom_for_id
from ui.canvas_state_lookup import ensure_canvas_state
from ui.renderer_style_access import bond_length_px_for

AtomCoords3D = tuple[float, float, float]


@dataclass(slots=True)
class CanvasAtomCoords3DState:
    atom_coords_3d: dict[int, AtomCoords3D] = field(default_factory=dict)


ATOM_COORDS_3D_ATTRS = ("atom_coords_3d",)


def atom_coords_3d_state_for(canvas: Any) -> CanvasAtomCoords3DState:
    return ensure_canvas_state(canvas, "atom_coords_3d_state", CanvasAtomCoords3DState)


def atom_coords_3d_for(canvas: Any) -> dict[int, AtomCoords3D]:
    return atom_coords_3d_state_for(canvas).atom_coords_3d


def set_atom_coords_3d_for(canvas: Any, coords: dict[int, AtomCoords3D]) -> None:
    state = atom_coords_3d_state_for(canvas)
    state.atom_coords_3d = coords


def atom_coords_3d_for_id(canvas: Any, atom_id: int) -> AtomCoords3D | None:
    return atom_coords_3d_for(canvas).get(atom_id)


def set_atom_coords_3d_for_id(canvas: Any, atom_id: int, coords: AtomCoords3D) -> None:
    atom_coords = atom_coords_3d_for(canvas)
    atom_coords[atom_id] = coords


def pop_atom_coords_3d_for(canvas: Any, atom_id: int) -> AtomCoords3D | None:
    atom_coords = atom_coords_3d_for(canvas)
    coords = atom_coords.pop(atom_id, None)
    return coords


def clear_atom_coords_3d_for(canvas: Any) -> None:
    set_atom_coords_3d_for(canvas, {})


def current_atom_coords_3d_for(canvas, atom_id: int) -> tuple[float, float, float] | None:
    atom = atom_for_id(canvas, atom_id)
    if atom is None:
        return None
    coords = atom_coords_3d_for_id(canvas, atom_id)
    if coords is None:
        return (atom.x, atom.y, 0.0)
    proj_x, proj_y = project_point_3d_for(canvas, coords)
    tolerance = max(1.0, bond_length_px_for(canvas) * 0.15)
    if math.hypot(proj_x - atom.x, proj_y - atom.y) > tolerance:
        return (atom.x, atom.y, 0.0)
    return coords


__all__ = [
    "ATOM_COORDS_3D_ATTRS",
    "AtomCoords3D",
    "CanvasAtomCoords3DState",
    "atom_coords_3d_for",
    "atom_coords_3d_for_id",
    "atom_coords_3d_state_for",
    "clear_atom_coords_3d_for",
    "current_atom_coords_3d_for",
    "pop_atom_coords_3d_for",
    "set_atom_coords_3d_for",
    "set_atom_coords_3d_for_id",
]
