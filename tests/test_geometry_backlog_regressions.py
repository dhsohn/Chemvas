"""Numerical witnesses for real-use geometry reports, independent of painting."""

import math
from itertools import pairwise

import pytest

from chemvas.core.template_geometry import (
    cyclohexane_chair_flipped_points,
    cyclohexane_chair_points,
)
from chemvas.domain.document import Atom, Bond
from chemvas.features.rendering import arc_midpoint, arc_points
from chemvas.ui.structure_geometry_access import default_bond_angle_for_vectors
from chemvas.ui.structure_geometry_logic import compute_sprout_bond_endpoint


@pytest.mark.parametrize("end", [(60.0, 0.0), (-60.0, 0.0), (36.0, 48.0)])
@pytest.mark.parametrize("sweep", [90, 180, 270])
@pytest.mark.parametrize("left", [True, False])
def test_arc_has_uniform_segments_and_correct_midpoint(end, sweep, left):
    start = (0.0, 0.0)
    points = arc_points(start, end, sweep_degrees=sweep, bulge_left=left)
    assert points[0] == start
    assert points[-1] == end
    lengths = [math.dist(a, b) for a, b in pairwise(points)]
    assert lengths == pytest.approx([lengths[0]] * len(lengths))
    mid = arc_midpoint(start, end, sweep_degrees=sweep, bulge_left=left)
    assert mid == pytest.approx(points[len(points) // 2])
    normal = (end[1] / 60, -end[0] / 60)
    offset = (mid[0] - end[0] / 2, mid[1] - end[1] / 2)
    side = offset[0] * normal[0] + offset[1] * normal[1]
    assert (side > 0) is left


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    return (
        _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0
    )


@pytest.mark.parametrize(
    "template", [cyclohexane_chair_points, cyclohexane_chair_flipped_points]
)
@pytest.mark.parametrize("atom_id", range(6))
@pytest.mark.parametrize("cyclic", [False, True])
def test_chair_sprouts_do_not_cross_nonincident_ring_bonds(template, atom_id, cyclic):
    points = template((0.0, 0.0), 20.0)
    atoms = {index: Atom("C", *point) for index, point in enumerate(points)}
    bonds = [Bond(index, (index + 1) % 6, 1) for index in range(6)]
    origin = points[atom_id]
    vectors = []
    for neighbor in ((atom_id - 1) % 6, (atom_id + 1) % 6):
        distance = math.dist(origin, points[neighbor])
        vectors.append(
            tuple(
                (value - base) / distance
                for value, base in zip(points[neighbor], origin, strict=True)
            )
        )
    angle = math.radians(default_bond_angle_for_vectors(vectors))
    default = (origin[0] + 20 * math.cos(angle), origin[1] + 20 * math.sin(angle))
    end = compute_sprout_bond_endpoint(
        atom_id,
        atoms=atoms,
        bonds=bonds,
        bond_length=20,
        cyclic=cyclic,
        default_endpoint=default,
    )
    assert end is not None
    assert math.dist(origin, end) == pytest.approx(20)
    assert not any(
        _intersects(origin, end, points[bond.a], points[bond.b])
        for bond in bonds
        if atom_id not in (bond.a, bond.b)
    )
    assert (
        min(
            math.dist(end, point)
            for index, point in enumerate(points)
            if index != atom_id
        )
        > 10.0
    )
