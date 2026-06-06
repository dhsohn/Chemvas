from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from ui.atom_coords_access import set_atom_coords_3d_for_id
from ui.atom_label_access import atom_label_service
from ui.bond_graphics_access import project_point_3d_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_graph_state import graph_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id, bonds_for
from ui.canvas_ring_fill_scene_access import (
    rotate_ring_fills_for,
    update_ring_fills_for_atoms_for,
)
from ui.canvas_rotation_state import rotation_state_for
from ui.mark_item_access import set_mark_center_for
from ui.move_access import move_service_from_canvas
from ui.renderer_style_access import bond_length_px_for
from ui.selection_center_logic import center_for_atoms
from ui.selection_collection_access import selected_ids_for
from ui.selection_rotation_geometry import (
    center_for_coords_3d,
    fragment_plane_normal_for,
    normalize_3d,
    rotate_point_around_axis,
)
from ui.selection_rotation_logic import (
    rotated_atom_positions,
    selected_rotation_atom_ids,
)
from ui.selection_rotation_planarity import (
    atom_in_planar_system_for,
    bond_in_cycle_for,
    bond_is_planar_fragment_edge_for,
    flatten_planar_fragments_for,
    planar_fragment_components_for,
)
from ui.selection_service_access import refresh_selection_outline_for


def _perspective_camera_distance_for(canvas) -> float:
    return max(bond_length_px_for(canvas) * 8.0, 120.0)


def bond_ids_for_atom_ids_for(canvas, atom_ids: set[int]) -> set[int]:
    graph = graph_state_for(canvas)
    bond_ids: set[int] = set()
    for atom_id in atom_ids:
        bond_ids.update(graph.atom_bond_ids.get(atom_id, ()))
    return bond_ids


def bond_ids_within_atom_ids_for(canvas, atom_ids: set[int]) -> set[int]:
    if not atom_ids:
        return set()
    bond_ids = bond_ids_for_atom_ids_for(canvas, atom_ids)
    if not bond_ids:
        return {
            bond_id
            for bond_id, bond in enumerate(bonds_for(canvas))
            if bond is not None and bond.a in atom_ids and bond.b in atom_ids
        }
    selected_bond_ids: set[int] = set()
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is None:
            continue
        if bond.a in atom_ids and bond.b in atom_ids:
            selected_bond_ids.add(bond_id)
    return selected_bond_ids


def average_bond_length_for_atoms_for(
    canvas,
    atom_ids: set[int],
    coords: dict[int, tuple[float, float, float]],
) -> float | None:
    if not atom_ids:
        return None
    bond_ids = bond_ids_within_atom_ids_for(canvas, atom_ids)
    if not bond_ids:
        return None
    total = 0.0
    count = 0
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is None:
            continue
        if bond.a not in atom_ids or bond.b not in atom_ids:
            continue
        a_coords = coords.get(bond.a)
        b_coords = coords.get(bond.b)
        if a_coords is None or b_coords is None:
            continue
        dist = math.hypot(a_coords[0] - b_coords[0], a_coords[1] - b_coords[1])
        if dist > 1e-9:
            total += dist
            count += 1
    if count == 0:
        return None
    return total / count


def rotation_scale_for_coords_for(
    canvas,
    atom_ids: set[int],
    rotated_coords: dict[int, tuple[float, float, float]],
    extra_atom_ids: set[int] | tuple[int, ...] = (),
) -> float:
    rotation = rotation_state_for(canvas)
    if not rotation.base_bond_length:
        return 1.0
    scale_atom_ids = set(atom_ids)
    scale_atom_ids.update(extra_atom_ids)
    current_coords = dict(rotation.base_coords)
    current_coords.update(rotated_coords)
    current_avg = average_bond_length_for_atoms_for(canvas, scale_atom_ids, current_coords)
    if not current_avg or current_avg <= 1e-9:
        return 1.0
    scale = rotation.base_bond_length / current_avg
    if not math.isfinite(scale) or scale <= 0.0:
        return 1.0
    return scale


def unproject_scene_point_3d_for(
    canvas,
    point: QPointF,
    z: float,
    *,
    center_3d: tuple[float, float, float] | None = None,
    anchor_2d: tuple[float, float] | None = None,
) -> tuple[float, float, float]:
    rotation = rotation_state_for(canvas)
    if center_3d is None:
        center_3d = rotation.projection_center_3d
    if center_3d is None:
        return point.x(), point.y(), z
    if anchor_2d is None:
        anchor_2d = rotation.projection_anchor_2d or (center_3d[0], center_3d[1])
    cx, cy, cz = center_3d
    anchor_x, anchor_y = anchor_2d
    focal = _perspective_camera_distance_for(canvas)
    dz = max(min(z - cz, focal * 0.7), -focal * 0.8)
    denom = max(focal - dz, focal * 0.2)
    scale = focal / denom
    return (
        cx + (point.x() - anchor_x) / scale,
        cy + (point.y() - anchor_y) / scale,
        z,
    )


def apply_projected_atom_positions_for(
    canvas,
    atom_ids: set[int],
    coords_3d: dict[int, tuple[float, float, float]],
) -> None:
    label_service = atom_label_service(canvas)
    mark_registry = mark_registry_for(canvas)
    for atom_id in atom_ids:
        point = coords_3d.get(atom_id)
        if point is None:
            continue
        set_atom_coords_3d_for_id(canvas, atom_id, point)
        atom = atom_for_id(canvas, atom_id)
        if atom is None:
            continue
        proj_x, proj_y = project_point_3d_for(canvas, point)
        atom.x = proj_x
        atom.y = proj_y
        label = atom_items_for(canvas).get(atom_id)
        if label is not None:
            label_service.position_label(label, atom.x, atom.y)
        dot = atom_dots_for(canvas).get(atom_id)
        if dot is not None:
            dot.setPos(atom.x, atom.y)
        marks = mark_registry.get_for_atom(atom_id)
        if not marks:
            continue
        for mark in list(marks):
            data = mark.data(1) or {}
            dx = data.get("dx")
            dy = data.get("dy")
            if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
                set_mark_center_for(canvas, mark, QPointF(atom.x + dx, atom.y + dy))
            else:
                set_mark_center_for(canvas, mark, QPointF(atom.x, atom.y))


def rotate_selection_for(canvas, angle_degrees: float) -> None:
    atom_ids, bond_ids = selected_ids_for(canvas)
    atom_ids = selected_rotation_atom_ids(atom_ids, bond_ids, bonds=bonds_for(canvas))
    if not atom_ids:
        return
    center = center_for_atoms(atom_ids, atoms=atoms_for(canvas))
    if center is None:
        return
    angle = math.radians(angle_degrees)
    label_service = atom_label_service(canvas)
    for atom_id, (x, y) in rotated_atom_positions(
        atom_ids,
        atoms=atoms_for(canvas),
        center=center,
        angle_radians=angle,
    ).items():
        atom = atom_for_id(canvas, atom_id)
        if atom is None:
            continue
        atom.x = x
        atom.y = y
        label = atom_items_for(canvas).get(atom_id)
        if label is not None:
            label_service.position_label(label, atom.x, atom.y)
    move_controller = move_service_from_canvas(canvas)
    for atom_id in atom_ids:
        move_controller.redraw_connected_bonds(atom_id)
    rotate_ring_fills_for(canvas, atom_ids, center, angle)
    refresh_selection_outline_for(canvas)


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
    "average_bond_length_for_atoms_for",
    "bond_ids_for_atom_ids_for",
    "bond_ids_within_atom_ids_for",
    "bond_in_cycle_for",
    "bond_is_planar_fragment_edge_for",
    "center_for_coords_3d",
    "flatten_planar_fragments_for",
    "fragment_plane_normal_for",
    "normalize_3d",
    "planar_fragment_components_for",
    "rotation_scale_for_coords_for",
    "rotate_selection_for",
    "rotate_point_around_axis_for",
    "unproject_scene_point_3d_for",
    "update_ring_fills_for_atoms_for",
]
