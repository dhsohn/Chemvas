from __future__ import annotations

import math

from core.template_geometry import (
    cyclohexane_boat_points,
    cyclohexane_chair_flipped_points,
    cyclohexane_chair_points,
    regular_ring_radius,
    ring_points,
    scale_points_to_bond_length,
)
from PyQt6.QtCore import QPointF

from ui.canvas_model_access import atom_for_id, atoms_for, bonds_for, required_atom_for
from ui.canvas_scene_items_state import ring_items_for
from ui.renderer_style_access import bond_length_px_for
from ui.ring_occupancy_logic import ring_polygon_points_for_bond
from ui.structure_geometry_logic import (
    compute_regular_ring_points_for_atom,
    compute_regular_ring_points_for_bond,
    compute_sprout_bond_endpoint,
    compute_template_points_for_bond,
)


def _bond_length(canvas) -> float:
    return bond_length_px_for(canvas)


def qpoints_from_pairs(points: list[tuple[float, float]]) -> list[QPointF]:
    return [QPointF(x, y) for x, y in points]


def point_pairs(points: list[QPointF]) -> list[tuple[float, float]]:
    return [(point.x(), point.y()) for point in points]


def point_pair(point: QPointF | None) -> tuple[float, float] | None:
    if point is None:
        return None
    return point.x(), point.y()


def template_geometry_result(
    result: tuple[list[tuple[float, float]], list[tuple[int, float, float]]] | None,
) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
    if result is None:
        return None
    points, merge = result
    return qpoints_from_pairs(points), merge


def scale_qpoints_to_bond_length(
    points: list[QPointF],
    center: QPointF,
    bond_length: float,
) -> list[QPointF]:
    scaled = scale_points_to_bond_length(
        point_pairs(points),
        (center.x(), center.y()),
        bond_length,
    )
    return qpoints_from_pairs(scaled)


def atom_point_for(canvas, atom_id: int) -> QPointF:
    atom = required_atom_for(canvas, atom_id)
    return QPointF(atom.x, atom.y)


def connected_atom_unit_vectors_for(canvas, atom_id: int) -> list[tuple[float, float]]:
    atom = atom_for_id(canvas, atom_id)
    if atom is None:
        return []
    vectors: list[tuple[float, float]] = []
    atoms = atoms_for(canvas)
    for bond in bonds_for(canvas):
        if bond is None or (bond.a != atom_id and bond.b != atom_id):
            continue
        other_id = bond.b if bond.a == atom_id else bond.a
        other = atoms.get(other_id)
        if other is None:
            continue
        dx = other.x - atom.x
        dy = other.y - atom.y
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        vectors.append((dx / length, dy / length))
    return vectors


def default_bond_angle_for_vectors(vectors: list[tuple[float, float]]) -> float:
    if len(vectors) >= 2:
        sx = sum(dx for dx, _ in vectors)
        sy = sum(dy for _, dy in vectors)
        if math.hypot(sx, sy) > 1e-6:
            return math.degrees(math.atan2(-sy, -sx))
        return math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 90.0
    if vectors:
        return math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 120.0
    return 0.0


def default_bond_endpoint_for(canvas, start: QPointF, start_atom_id: int | None) -> QPointF:
    angle = 0.0
    if start_atom_id is not None:
        angle = default_bond_angle_for_vectors(connected_atom_unit_vectors_for(canvas, start_atom_id))
    rad = math.radians(angle)
    bond_len = _bond_length(canvas)
    return QPointF(start.x() + math.cos(rad) * bond_len, start.y() + math.sin(rad) * bond_len)


def sprout_bond_endpoint_for(canvas, atom_id: int, *, cyclic: bool = False) -> QPointF | None:
    atom = atom_for_id(canvas, atom_id)
    default_endpoint = None
    if atom is not None and not cyclic:
        start = QPointF(atom.x, atom.y)
        endpoint = default_bond_endpoint_for(canvas, start, atom_id)
        default_endpoint = (endpoint.x(), endpoint.y())
    point = compute_sprout_bond_endpoint(
        atom_id,
        atoms=atoms_for(canvas),
        bonds=bonds_for(canvas),
        bond_length=_bond_length(canvas),
        cyclic=cyclic,
        default_endpoint=default_endpoint,
    )
    if point is None:
        return None
    return QPointF(point[0], point[1])


def regular_ring_radius_for(canvas, n: int, bond_length: float | None = None) -> float:
    return regular_ring_radius(n, bond_length if bond_length is not None else _bond_length(canvas))


def ring_points_for(canvas, center: QPointF, n: int, radius: float | None = None) -> list[QPointF]:
    points = ring_points((center.x(), center.y()), n, radius or _bond_length(canvas))
    return qpoints_from_pairs(points)


def cyclohexane_chair_points_for(canvas, center: QPointF) -> list[QPointF]:
    points = cyclohexane_chair_points((center.x(), center.y()), _bond_length(canvas))
    return qpoints_from_pairs(points)


def cyclohexane_chair_flipped_points_for(canvas, center: QPointF) -> list[QPointF]:
    points = cyclohexane_chair_flipped_points((center.x(), center.y()), _bond_length(canvas))
    return qpoints_from_pairs(points)


def cyclohexane_boat_points_for(canvas, center: QPointF) -> list[QPointF]:
    points = cyclohexane_boat_points((center.x(), center.y()), _bond_length(canvas))
    return qpoints_from_pairs(points)


def ring_polygon_points_for_bond_for(canvas, bond_id: int) -> list[tuple[float, float]] | None:
    return ring_polygon_points_for_bond(
        bond_id,
        bonds=bonds_for(canvas),
        ring_items=ring_items_for(canvas),
    )


def regular_ring_points_for_atom_for(
    canvas,
    n: int,
    atom_id: int,
) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
    result = compute_regular_ring_points_for_atom(
        n,
        atom_id,
        atoms=atoms_for(canvas),
        bonds=bonds_for(canvas),
        bond_length=_bond_length(canvas),
    )
    return template_geometry_result(result)


def _compute_bond_template_geometry_for(
    canvas,
    geometry_fn,
    geometry_input,
    bond_id: int,
    *,
    center_hint: QPointF | None = None,
) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
    result = geometry_fn(
        geometry_input,
        bond_id,
        atoms=atoms_for(canvas),
        bonds=bonds_for(canvas),
        center_hint=point_pair(center_hint),
        occupied_polygon=ring_polygon_points_for_bond_for(canvas, bond_id),
    )
    return template_geometry_result(result)


def regular_ring_points_for_bond_for(
    canvas,
    n: int,
    bond_id: int,
    center_hint: QPointF | None = None,
) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
    return _compute_bond_template_geometry_for(
        canvas,
        compute_regular_ring_points_for_bond,
        n,
        bond_id,
        center_hint=center_hint,
    )


def template_points_for_bond_for(
    canvas,
    points_local: list[QPointF],
    bond_id: int,
    center_hint: QPointF | None = None,
) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
    return _compute_bond_template_geometry_for(
        canvas,
        compute_template_points_for_bond,
        point_pairs(points_local),
        bond_id,
        center_hint=center_hint,
    )


__all__ = [
    "atom_point_for",
    "connected_atom_unit_vectors_for",
    "cyclohexane_boat_points_for",
    "cyclohexane_chair_flipped_points_for",
    "cyclohexane_chair_points_for",
    "default_bond_angle_for_vectors",
    "default_bond_endpoint_for",
    "point_pair",
    "point_pairs",
    "qpoints_from_pairs",
    "regular_ring_points_for_atom_for",
    "regular_ring_points_for_bond_for",
    "regular_ring_radius_for",
    "ring_points_for",
    "ring_polygon_points_for_bond_for",
    "scale_qpoints_to_bond_length",
    "sprout_bond_endpoint_for",
    "template_geometry_result",
    "template_points_for_bond_for",
]
