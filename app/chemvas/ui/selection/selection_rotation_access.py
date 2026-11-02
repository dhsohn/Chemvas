from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.features.selection import (
    center_for_coords_3d,
    fragment_plane_normal_for,
    normalize_3d,
    rotate_point_around_axis,
    unproject_point_3d,
)
from chemvas.ui.canvas.canvas_ring_fill_scene_access import (
    update_ring_fills_for_atoms_for,
)
from chemvas.ui.molecule.bond_graphics_access import project_point_3d_for
from chemvas.ui.selection.selection_rotation_planarity import (
    atom_in_planar_system_for,
    bond_in_cycle_for,
    bond_is_planar_fragment_edge_for,
    flatten_planar_fragments_for,
    planar_fragment_components_for,
)

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF


def bond_ids_for_atom_ids_for(canvas, atom_ids: set[int]) -> set[int]:
    graph = canvas.runtime_state.graph_state
    bond_ids: set[int] = set()
    for atom_id in atom_ids:
        bond_ids.update(graph.atom_bond_ids.get(atom_id, ()))
    return bond_ids


def unproject_scene_point_3d_for(
    canvas,
    point: QPointF,
    z: float,
    *,
    center_3d: tuple[float, float, float] | None = None,
    anchor_2d: tuple[float, float] | None = None,
) -> tuple[float, float, float]:
    rotation = canvas.runtime_state.rotation_state
    if center_3d is None:
        center_3d = rotation.projection_center_3d
    if center_3d is None:
        return point.x(), point.y(), z
    if anchor_2d is None:
        anchor_2d = rotation.projection_anchor_2d or (center_3d[0], center_3d[1])
    return unproject_point_3d(
        (point.x(), point.y()),
        z,
        bond_length_px=canvas.renderer.style.bond_length_px,
        center_3d=center_3d,
        anchor_2d=anchor_2d,
    )


def apply_projected_atom_positions_for(
    canvas,
    atom_ids: set[int],
    coords_3d: dict[int, tuple[float, float, float]],
) -> None:
    """Project 3D coordinates then install them through the move owner.

    Exact cache entries are passed for every supplied atom, including atoms
    missing from the model, so the nonexistent-atom depth-cache behavior stays
    with this adapter. Bond/ring/selection refresh remains the caller's job.
    """
    positions: dict[int, tuple[float, float]] = {}
    exact_coords: dict[int, tuple[float, float, float]] = {}
    for atom_id in atom_ids:
        point = coords_3d.get(atom_id)
        if point is None:
            continue
        exact_coords[atom_id] = point
        atom = canvas.model.atom_for_id(atom_id)
        if atom is None:
            continue
        positions[atom_id] = project_point_3d_for(canvas, point)
    canvas.services.move_controller.apply_atom_geometry(
        positions, coords_3d=exact_coords
    )


def rotate_point_around_axis_for(
    canvas,
    point: tuple[float, float, float],
    axis_start: tuple[float, float, float],
    axis_end: tuple[float, float, float],
    angle: float,
) -> tuple[float, float, float]:
    return rotate_point_around_axis(point, axis_start, axis_end, angle)


__all__ = [
    "apply_projected_atom_positions_for",
    "atom_in_planar_system_for",
    "bond_ids_for_atom_ids_for",
    "bond_in_cycle_for",
    "bond_is_planar_fragment_edge_for",
    "center_for_coords_3d",
    "flatten_planar_fragments_for",
    "fragment_plane_normal_for",
    "normalize_3d",
    "planar_fragment_components_for",
    "rotate_point_around_axis_for",
    "unproject_scene_point_3d_for",
    "update_ring_fills_for_atoms_for",
]
