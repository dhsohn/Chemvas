from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemvas.domain.document.perspective import (
    current_atom_coords_3d,
    stored_coords_match_projection,
)

AtomCoords3D = tuple[float, float, float]


@dataclass(slots=True)
class CanvasAtomCoords3DState:
    atom_coords_3d: dict[int, AtomCoords3D] = field(default_factory=dict)


def set_atom_coords_3d_for(canvas: Any, coords: dict[int, AtomCoords3D]) -> None:
    state = canvas.runtime_state.atom_coords_3d_state
    state.atom_coords_3d = coords


def set_atom_coords_3d_for_id(canvas: Any, atom_id: int, coords: AtomCoords3D) -> None:
    atom_coords = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
    atom_coords[atom_id] = coords


def pop_atom_coords_3d_for(canvas: Any, atom_id: int) -> AtomCoords3D | None:
    atom_coords = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
    coords = atom_coords.pop(atom_id, None)
    return coords


def clear_atom_coords_3d_for(canvas: Any) -> None:
    set_atom_coords_3d_for(canvas, {})


def stored_atom_coords_3d_matches_projection_for(
    canvas: Any, atom_id: int, coords: AtomCoords3D
) -> bool:
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return False
    rotation = canvas.runtime_state.rotation_state
    return stored_coords_match_projection(
        coords,
        (atom.x, atom.y),
        bond_length_px=canvas.renderer.style.bond_length_px,
        center_3d=rotation.projection_center_3d,
        anchor_2d=rotation.projection_anchor_2d,
    )


def current_atom_coords_3d_for(
    canvas, atom_id: int
) -> tuple[float, float, float] | None:
    atom = canvas.model.atoms.get(atom_id)
    if atom is None:
        return None
    rotation = canvas.runtime_state.rotation_state
    return current_atom_coords_3d(
        (atom.x, atom.y),
        canvas.runtime_state.atom_coords_3d_state.atom_coords_3d.get(atom_id),
        bond_length_px=canvas.renderer.style.bond_length_px,
        center_3d=rotation.projection_center_3d,
        anchor_2d=rotation.projection_anchor_2d,
    )


__all__ = [
    "AtomCoords3D",
    "CanvasAtomCoords3DState",
    "clear_atom_coords_3d_for",
    "current_atom_coords_3d_for",
    "pop_atom_coords_3d_for",
    "set_atom_coords_3d_for",
    "set_atom_coords_3d_for_id",
    "stored_atom_coords_3d_matches_projection_for",
]
