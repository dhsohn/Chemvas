from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PyQt6.QtCore import QPointF

from core.model import Atom, Bond
from ui.ring_occupancy_logic import point_inside_any_ring


def plan_benzene_ring_points(
    center: QPointF,
    *,
    attach_atom_id: int | None,
    attach_bond_id: int | None,
    bonds: Sequence[Bond | None],
    atoms: Mapping[int, Atom],
    ring_items: Sequence,
    bond_length: float,
    regular_ring_points_for_bond: Callable[[int, int, QPointF], tuple[list[QPointF], list[tuple[int, float, float]]] | None],
    regular_ring_points_for_atom: Callable[[int, int], tuple[list[QPointF], list[tuple[int, float, float]]] | None],
    compute_free_points: Callable[..., list[tuple[float, float]]],
) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
    if attach_atom_id is None and attach_bond_id is None and point_inside_any_ring(center, ring_items=ring_items):
        return None

    if attach_bond_id is not None and 0 <= attach_bond_id < len(bonds):
        bond = bonds[attach_bond_id]
        if bond is not None:
            atom_a = atoms.get(bond.a)
            atom_b = atoms.get(bond.b)
            if atom_a is not None and atom_b is not None:
                result = regular_ring_points_for_bond(6, attach_bond_id, center)
                if result is None:
                    return None
                return result

    if attach_atom_id is not None and attach_atom_id in atoms:
        result = regular_ring_points_for_atom(6, attach_atom_id)
        if result is None:
            return None
        return result

    free_points = compute_free_points((center.x(), center.y()), bond_length=bond_length)
    return [QPointF(x, y) for x, y in free_points], []


__all__ = ["plan_benzene_ring_points"]
