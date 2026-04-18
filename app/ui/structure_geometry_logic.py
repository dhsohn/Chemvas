from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from core.model import Atom, Bond
from core.template_geometry import (
    place_template_on_bond as project_template_on_bond,
    regular_ring_points_for_atom as build_regular_ring_points_for_atom,
    regular_ring_points_for_bond as build_regular_ring_points_for_bond,
)

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
        return default_endpoint

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
    return (
        ox + math.cos(rad) * bond_length,
        oy + math.sin(rad) * bond_length,
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
    if points is None:
        return None
    ox, oy = origin
    return points, [(attach_atom_id, ox, oy)]


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
    if points is None:
        return None
    ax, ay = a_point
    bx, by = b_point
    return points, [(bond.a, ax, ay), (bond.b, bx, by)]


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
    if points is None:
        return None
    ax, ay = a_point
    bx, by = b_point
    return points, [(bond.a, ax, ay), (bond.b, bx, by)]


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
