from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from chemvas.domain.document import Atom, Bond


def plan_benzene_ring_points[PointT](
    center: tuple[float, float],
    *,
    attach_atom_id: int | None,
    attach_bond_id: int | None,
    bonds: Sequence[Bond | None],
    atoms: Mapping[int, Atom],
    bond_length: float,
    center_inside_existing_ring: Callable[[], bool],
    regular_ring_points_for_bond: Callable[
        [int, int, tuple[float, float]],
        tuple[list[PointT], list[tuple[int, float, float]]] | None,
    ],
    regular_ring_points_for_atom: Callable[
        [int, int], tuple[list[PointT], list[tuple[int, float, float]]] | None
    ],
    compute_free_points: Callable[..., list[tuple[float, float]]],
    make_point: Callable[[float, float], PointT],
) -> tuple[list[PointT], list[tuple[int, float, float]]] | None:
    if (
        attach_atom_id is None
        and attach_bond_id is None
        and center_inside_existing_ring()
    ):
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

    free_points = compute_free_points(center, bond_length=bond_length)
    return [make_point(x, y) for x, y in free_points], []


__all__ = ["plan_benzene_ring_points"]
