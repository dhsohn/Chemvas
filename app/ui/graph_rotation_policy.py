from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any


def rotation_side_for_bond_policy(
    bond,
    comp_a: set[int],
    comp_b: set[int],
    selected_atom_ids: set[int],
    *,
    allow_fallback: bool,
) -> set[int] | None:
    effective_selected = set(selected_atom_ids) - {bond.a, bond.b}
    selected_in_a = effective_selected & comp_a
    selected_in_b = effective_selected & comp_b
    if selected_in_a and not selected_in_b:
        return comp_a
    if selected_in_b and not selected_in_a:
        return comp_b
    if not selected_in_a and not selected_in_b:
        a_selected = bond.a in selected_atom_ids
        b_selected = bond.b in selected_atom_ids
        if a_selected ^ b_selected:
            return comp_a if a_selected else comp_b
    if allow_fallback:
        count_a = len(selected_in_a)
        count_b = len(selected_in_b)
        if count_a != count_b:
            return comp_a if count_a > count_b else comp_b
        size_a = max(0, len(comp_a) - 1)
        size_b = max(0, len(comp_b) - 1)
        if size_a != size_b:
            return comp_a if size_a > size_b else comp_b
        return comp_a if len(comp_a) >= len(comp_b) else comp_b
    return None


def preferred_rotation_side_for_bond_policy(
    bond,
    comp_a: set[int],
    comp_b: set[int],
    selected_atom_ids: set[int],
    *,
    atom_a,
    atom_b,
    press_pos=None,
    bond_length_px: float | None = None,
    allow_fallback: bool,
) -> set[int] | None:
    component = comp_a | comp_b
    selected_in_component = set(selected_atom_ids) & component
    is_partial_selection = 0 < len(selected_in_component) < len(component)
    effective_selected = selected_in_component - {bond.a, bond.b}
    selected_in_a = effective_selected & comp_a
    selected_in_b = effective_selected & comp_b
    overlap_a = selected_in_component & comp_a
    overlap_b = selected_in_component & comp_b
    dist_a = None
    dist_b = None
    if is_partial_selection:
        if selected_in_a and not selected_in_b:
            return comp_a
        if selected_in_b and not selected_in_a:
            return comp_b
        if overlap_a and not overlap_b:
            return comp_a
        if overlap_b and not overlap_a:
            return comp_b
        coverage_a = len(overlap_a) / max(1, len(comp_a))
        coverage_b = len(overlap_b) / max(1, len(comp_b))
        if abs(coverage_a - coverage_b) > 1e-9:
            return comp_a if coverage_a > coverage_b else comp_b
        if len(selected_in_a) != len(selected_in_b):
            return comp_a if len(selected_in_a) > len(selected_in_b) else comp_b
        if len(overlap_a) != len(overlap_b):
            return comp_a if len(overlap_a) > len(overlap_b) else comp_b
    elif not selected_in_a and not selected_in_b:
        a_selected = bond.a in selected_atom_ids
        b_selected = bond.b in selected_atom_ids
        if a_selected ^ b_selected:
            return comp_a if a_selected else comp_b
    if press_pos is not None and atom_a is not None and atom_b is not None:
        dist_a = math.hypot(press_pos.x() - atom_a.x, press_pos.y() - atom_a.y)
        dist_b = math.hypot(press_pos.x() - atom_b.x, press_pos.y() - atom_b.y)
        tol = (bond_length_px or 0.0) * 0.05
        if abs(dist_a - dist_b) > tol:
            return comp_a if dist_a < dist_b else comp_b
    if not allow_fallback:
        return None
    size_a = max(0, len(comp_a) - 1)
    size_b = max(0, len(comp_b) - 1)
    if size_a != size_b:
        return comp_a if size_a < size_b else comp_b
    if dist_a is not None and dist_b is not None:
        return comp_a if dist_a <= dist_b else comp_b
    return comp_a if bond.a <= bond.b else comp_b


def rotatable_axis_from_selection_policy(
    selected_atom_ids: set[int],
    selected_bond_ids: set[int],
    *,
    bonds: Sequence[Any],
    bond_for_id: Callable[[int], Any | None],
    bond_is_rotatable: Callable[[int], bool],
    preferred_rotation_side_for_bond: Callable[..., set[int] | None],
    rotation_side_for_bond: Callable[..., set[int] | None],
) -> tuple[int, set[int]] | None:
    explicit_atoms = set(selected_atom_ids)
    bond_atoms: set[int] = set()
    selected_bonds: set[int] = set()
    for bond_id in selected_bond_ids:
        bond = bond_for_id(bond_id)
        if bond is None:
            continue
        selected_bonds.add(bond_id)
        bond_atoms.add(bond.a)
        bond_atoms.add(bond.b)
    atoms_for_boundary = explicit_atoms | bond_atoms
    if selected_bonds and len(selected_bonds) == 1:
        bond_id = next(iter(selected_bonds))
        if bond_is_rotatable(bond_id):
            rotating = preferred_rotation_side_for_bond(
                bond_id,
                atoms_for_boundary,
                allow_fallback=True,
            )
            if rotating is not None:
                return bond_id, rotating
    if not explicit_atoms and len(selected_bonds) > 1:
        selected_degree: dict[int, int] = {}
        for bond_id in selected_bonds:
            bond = bond_for_id(bond_id)
            if bond is None:
                continue
            selected_degree[bond.a] = selected_degree.get(bond.a, 0) + 1
            selected_degree[bond.b] = selected_degree.get(bond.b, 0) + 1
        has_unselected_bond: dict[int, bool] = {}
        for other_id, other in enumerate(bonds):
            if other is None or other_id in selected_bonds:
                continue
            has_unselected_bond[other.a] = True
            has_unselected_bond[other.b] = True
        candidates = []
        for bond_id in selected_bonds:
            bond = bond_for_id(bond_id)
            if bond is None:
                continue
            a_leaf = selected_degree.get(bond.a, 0) == 1 and has_unselected_bond.get(bond.a, False)
            b_leaf = selected_degree.get(bond.b, 0) == 1 and has_unselected_bond.get(bond.b, False)
            if a_leaf ^ b_leaf:
                candidates.append(bond_id)
        if len(candidates) == 1:
            bond_id = candidates[0]
            if bond_is_rotatable(bond_id):
                rotating = rotation_side_for_bond(
                    bond_id,
                    bond_atoms,
                    allow_fallback=True,
                )
                if rotating is not None:
                    return bond_id, rotating
            return None
    if not atoms_for_boundary:
        return None
    boundary = []
    for bond_id, bond in enumerate(bonds):
        if bond is None:
            continue
        a_sel = bond.a in atoms_for_boundary
        b_sel = bond.b in atoms_for_boundary
        if a_sel ^ b_sel:
            boundary.append(bond_id)
    if len(boundary) == 1:
        bond_id = boundary[0]
        if not bond_is_rotatable(bond_id):
            return None
        rotating = rotation_side_for_bond(
            bond_id,
            atoms_for_boundary,
            allow_fallback=not explicit_atoms,
        )
        if rotating is not None:
            return bond_id, rotating
    atoms_for_axis = set(atoms_for_boundary)
    candidates: list[tuple[int, set[int]]] = []
    for bond_id, bond in enumerate(bonds):
        if bond is None or not bond_is_rotatable(bond_id):
            continue
        rotating = rotation_side_for_bond(
            bond_id,
            atoms_for_axis,
            allow_fallback=False,
        )
        if rotating is None:
            continue
        candidates.append((bond_id, rotating))
    return candidates[0] if len(candidates) == 1 else None


def axis_from_rotation_hint_policy(
    axis_hint: int,
    rotation_atom_ids: set[int],
    *,
    bond_is_rotatable: Callable[[int], bool],
    bond_component_atoms: Callable[[int], set[int] | None],
    preferred_rotation_side_for_bond: Callable[..., set[int] | None],
    press_pos=None,
) -> tuple[int, set[int]] | None:
    if not bond_is_rotatable(axis_hint):
        return None
    component = bond_component_atoms(axis_hint)
    if component is None:
        return None
    selected_in_component = rotation_atom_ids & component
    if not selected_in_component:
        return None
    rotating = preferred_rotation_side_for_bond(
        axis_hint,
        selected_in_component,
        press_pos=press_pos,
        allow_fallback=True,
    )
    if rotating is None:
        return None
    return axis_hint, rotating


__all__ = [
    "axis_from_rotation_hint_policy",
    "preferred_rotation_side_for_bond_policy",
    "rotatable_axis_from_selection_policy",
    "rotation_side_for_bond_policy",
]
