from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chemvas.core.template_geometry import (
    place_template_on_bond as project_template_on_bond,
)
from chemvas.core.template_geometry import (
    regular_ring_points_for_atom as build_regular_ring_points_for_atom,
)
from chemvas.core.template_geometry import (
    regular_ring_points_for_bond as build_regular_ring_points_for_bond,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from chemvas.domain.document import Atom, Bond

Point = tuple[float, float]
MergeEntry = tuple[int, float, float]


def compute_sprout_bond_endpoint(
    atom_id: int,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
    bond_length: float,
    cyclic: bool,
    default_endpoint: Point | None = None,
) -> Point | None:
    atom_data = _atom_neighbor_points(atom_id, atoms=atoms, bonds=bonds)
    if atom_data is None:
        return None
    origin, neighbor_points = atom_data
    if not cyclic:
        return _uncrossed_sprout_endpoint(
            atom_id, origin, default_endpoint, atoms=atoms, bonds=bonds
        )

    vectors: list[Point] = []
    ox, oy = origin
    for nx, ny in neighbor_points:
        dx = nx - ox
        dy = ny - oy
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            continue
        vectors.append((dx / length, dy / length))

    if not vectors:
        angle = 60.0
    elif len(vectors) == 1:
        angle = math.degrees(math.atan2(vectors[0][1], vectors[0][0])) + 120.0
    else:
        sx = sum(vx for vx, _ in vectors)
        sy = sum(vy for _, vy in vectors)
        if math.hypot(sx, sy) > 1e-6:
            angle = math.degrees(math.atan2(-sy, -sx))
        else:
            angle = math.degrees(math.atan2(vectors[0][1], vectors[0][0])) + 120.0
    snap_angle = round(angle / 60.0) * 60.0
    rad = math.radians(snap_angle)
    return _uncrossed_sprout_endpoint(
        atom_id,
        origin,
        (ox + math.cos(rad) * bond_length, oy + math.sin(rad) * bond_length),
        atoms=atoms,
        bonds=bonds,
    )


def _uncrossed_sprout_endpoint(
    atom_id: int,
    origin: Point,
    endpoint: Point | None,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
) -> Point | None:
    """Keep the preferred direction unless it crosses another drawn bond.

    A concave ring vertex's opposite-neighbor bisector points into the ring.
    Try the same bounded 60-degree directions used by cyclic sprouting; this
    is a local drawing correction, not a molecular layout or stereo policy.
    """
    if endpoint is None:
        return None
    segments = [
        ((atoms[bond.a].x, atoms[bond.a].y), (atoms[bond.b].x, atoms[bond.b].y))
        for bond in bonds
        if bond is not None
        and atom_id not in (bond.a, bond.b)
        and bond.a in atoms
        and bond.b in atoms
    ]

    def crosses(end: Point) -> bool:
        dx, dy = end[0] - origin[0], end[1] - origin[1]
        for a, b in segments:
            ex, ey = b[0] - a[0], b[1] - a[1]
            determinant = dx * ey - dy * ex
            if abs(determinant) <= 1e-9:
                continue
            ax, ay = a[0] - origin[0], a[1] - origin[1]
            t = (ax * ey - ay * ex) / determinant
            u = (ax * dy - ay * dx) / determinant
            if 0.0 < t <= 1.0 and 0.0 <= u <= 1.0:
                return True
        return False

    if not crosses(endpoint):
        return endpoint
    dx, dy = endpoint[0] - origin[0], endpoint[1] - origin[1]
    candidates = []
    for degrees in (60, -60, 120, -120, 180):
        angle = math.radians(degrees)
        candidate = (
            origin[0] + dx * math.cos(angle) - dy * math.sin(angle),
            origin[1] + dx * math.sin(angle) + dy * math.cos(angle),
        )
        if not crosses(candidate):
            # Among unblocked directions, prefer open space rather than a
            # near-parallel bond ending on (or beside) an existing neighbor.
            clearance = min(
                math.hypot(candidate[0] - atom.x, candidate[1] - atom.y)
                for other_id, atom in atoms.items()
                if other_id != atom_id
            )
            if clearance > 1e-6:
                candidates.append((clearance, candidate))
    return (
        max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None
    )


def compute_regular_ring_points_for_atom(
    n: int,
    attach_atom_id: int,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
    bond_length: float,
) -> tuple[list[Point], list[MergeEntry]] | None:
    if n < 3:
        return None
    atom_data = _atom_neighbor_points(attach_atom_id, atoms=atoms, bonds=bonds)
    if atom_data is None:
        return None
    origin, neighbor_points = atom_data
    points = build_regular_ring_points_for_atom(
        n,
        origin,
        neighbor_points,
        bond_length,
    )
    return _atom_geometry_result(points, attach_atom_id, origin)


def compute_regular_ring_points_for_bond(
    n: int,
    bond_id: int,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
    center_hint: Point | None = None,
    occupied_polygon: list[Point] | None = None,
) -> tuple[list[Point], list[MergeEntry]] | None:
    if n < 3:
        return None
    bond_data = _bond_endpoints(bond_id, atoms=atoms, bonds=bonds)
    if bond_data is None:
        return None
    bond, a_point, b_point = bond_data
    points = build_regular_ring_points_for_bond(
        n,
        a_point,
        b_point,
        center_hint=center_hint,
        occupied_polygon=occupied_polygon,
    )
    return _bond_geometry_result(points, bond, a_point, b_point)


def compute_template_points_for_bond(
    points_local: list[Point],
    bond_id: int,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
    center_hint: Point | None = None,
    occupied_polygon: list[Point] | None = None,
) -> tuple[list[Point], list[MergeEntry]] | None:
    if len(points_local) < 2:
        return None
    bond_data = _bond_endpoints(bond_id, atoms=atoms, bonds=bonds)
    if bond_data is None:
        return None
    bond, a_point, b_point = bond_data
    points = project_template_on_bond(
        points_local,
        a_point,
        b_point,
        center_hint=center_hint,
        occupied_polygon=occupied_polygon,
    )
    return _bond_geometry_result(points, bond, a_point, b_point)


def _geometry_result(
    points: list[Point] | None,
    merge_entries: list[MergeEntry],
) -> tuple[list[Point], list[MergeEntry]] | None:
    if points is None:
        return None
    return points, merge_entries


def _merge_entry(atom_id: int, point: Point) -> MergeEntry:
    x, y = point
    return atom_id, x, y


def _atom_geometry_result(
    points: list[Point] | None,
    atom_id: int,
    origin: Point,
) -> tuple[list[Point], list[MergeEntry]] | None:
    return _geometry_result(points, [_merge_entry(atom_id, origin)])


def _bond_geometry_result(
    points: list[Point] | None,
    bond: Bond,
    a_point: Point,
    b_point: Point,
) -> tuple[list[Point], list[MergeEntry]] | None:
    return _geometry_result(
        points,
        [_merge_entry(bond.a, a_point), _merge_entry(bond.b, b_point)],
    )


def compute_free_benzene_ring_points(
    center: Point,
    *,
    bond_length: float,
) -> list[Point]:
    cx, cy = center
    return [
        (
            cx + bond_length * math.cos(math.radians(60 * index - 30)),
            cy + bond_length * math.sin(math.radians(60 * index - 30)),
        )
        for index in range(6)
    ]


def _atom_neighbor_points(
    atom_id: int,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
) -> tuple[Point, list[Point]] | None:
    atom = atoms.get(atom_id)
    if atom is None:
        return None
    neighbor_points: list[Point] = []
    for bond in bonds:
        if bond is None or (bond.a != atom_id and bond.b != atom_id):
            continue
        other_id = bond.b if bond.a == atom_id else bond.a
        other = atoms.get(other_id)
        if other is None:
            continue
        neighbor_points.append((other.x, other.y))
    return (atom.x, atom.y), neighbor_points


def _bond_endpoints(
    bond_id: int,
    *,
    atoms: Mapping[int, Atom],
    bonds: Sequence[Bond | None],
) -> tuple[Bond, Point, Point] | None:
    if not (0 <= bond_id < len(bonds)):
        return None
    bond = bonds[bond_id]
    if bond is None:
        return None
    a = atoms.get(bond.a)
    b = atoms.get(bond.b)
    if a is None or b is None:
        return None
    return bond, (a.x, a.y), (b.x, b.y)


__all__ = [
    "compute_free_benzene_ring_points",
    "compute_regular_ring_points_for_atom",
    "compute_regular_ring_points_for_bond",
    "compute_sprout_bond_endpoint",
    "compute_template_points_for_bond",
]
