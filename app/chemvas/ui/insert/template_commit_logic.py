"""Committing a resolved ring template, independent of Qt graphics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.molecule.structure_mutation_access import add_bond_for

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chemvas.features.insertion import TemplateInsertPlan

# Rings grown from an existing atom or bond merge into it; others stand alone.
ATTACHED_TEMPLATE_GENERATORS = frozenset(
    ("atom_regular_ring", "bond_regular_ring", "bond_template_shape")
)


def bond_merge_seed(canvas, bond_id: int) -> list[tuple[int, float, float]]:
    bond = canvas.model.bond_for_id(bond_id)
    if bond is None:
        return []
    atom_a = canvas.model.atom_for_id(bond.a)
    atom_b = canvas.model.atom_for_id(bond.b)
    if atom_a is None or atom_b is None:
        return []
    return [(bond.a, atom_a.x, atom_a.y), (bond.b, atom_b.x, atom_b.y)]


def atom_merge_seed(canvas, atom_id: int) -> list[tuple[int, float, float]]:
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return []
    return [(atom_id, atom.x, atom.y)]


def commit_template_ring[Point](
    canvas,
    plan: TemplateInsertPlan,
    points: Sequence[Point],
    *,
    add_atom_with_merge: Callable[[Point, str, list], int],
    add_ring_from_points: Callable[[Sequence[Point]], object],
    add_ring_fill: Callable[[Sequence[Point], list[int]], object],
    bond_exists: Callable[[int, int], bool],
) -> bool:
    """Add a non-benzene template's atoms, bonds and ring fill to the model."""
    if plan.generator not in ATTACHED_TEMPLATE_GENERATORS:
        add_ring_from_points(points)
        return True
    if plan.generator == "atom_regular_ring":
        if plan.atom_id is None:
            return False
        merge = atom_merge_seed(canvas, plan.atom_id)
    elif plan.bond_id is not None:
        merge = bond_merge_seed(canvas, plan.bond_id)
    else:
        return False
    if not merge:
        return False
    atom_ids = [add_atom_with_merge(point, "C", merge) for point in points]
    bonds_start = len(canvas.model.bonds)
    for index, a_id in enumerate(atom_ids):
        b_id = atom_ids[(index + 1) % len(atom_ids)]
        if not bond_exists(a_id, b_id):
            add_bond_for(canvas, a_id, b_id)
    for new_bond_id in canvas.model.bond_ids_from(bonds_start):
        canvas.bond_renderer.add_bond_graphics(new_bond_id)
    add_ring_fill(points, atom_ids)
    return True


__all__ = [
    "ATTACHED_TEMPLATE_GENERATORS",
    "atom_merge_seed",
    "bond_merge_seed",
    "commit_template_ring",
]
