from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from core.model import Bond
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QGraphicsPolygonItem

Point = tuple[float, float]


def ring_polygon_points_for_bond(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    ring_items: Sequence[QGraphicsPolygonItem],
) -> list[Point] | None:
    if not (0 <= bond_id < len(bonds)):
        return None
    bond = bonds[bond_id]
    if bond is None:
        return None
    return ring_polygon_points_for_atoms(bond.a, bond.b, ring_items=ring_items)


def ring_polygon_points_for_atoms(
    atom_a: int,
    atom_b: int,
    *,
    ring_items: Sequence[QGraphicsPolygonItem],
) -> list[Point] | None:
    for ring_item in ring_items:
        try:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if atom_a not in ring_atom_ids or atom_b not in ring_atom_ids:
                continue
            polygon = ring_item.polygon()
        except RuntimeError:
            continue
        return [(point.x(), point.y()) for point in cast(Any, polygon)]
    return None


def point_inside_any_ring(
    point: QPointF,
    *,
    ring_items: Sequence[QGraphicsPolygonItem],
) -> bool:
    for ring_item in ring_items:
        try:
            polygon = ring_item.polygon()
        except RuntimeError:
            continue
        if polygon.containsPoint(point, Qt.FillRule.WindingFill):
            return True
    return False


__all__ = [
    "point_inside_any_ring",
    "ring_polygon_points_for_atoms",
    "ring_polygon_points_for_bond",
]
