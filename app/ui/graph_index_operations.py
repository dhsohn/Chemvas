"""Pure operations on the derived atom-neighbor / atom-bond indexes.

Consistency contract (shared by every consumer):

- The indexes are derived state; the bond list on the model is the truth.
- Read helpers use populated index entries as the fast path. Missing or empty
  entries fall back to scanning the model because they cannot prove absence.
- A missing or empty entry means the index may never have learned about that
  atom, so it cannot prove that no model bond exists.
- ``CanvasGraphService`` repairs stale derived indexes when a read path finds
  model truth that the index missed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, MutableMapping, Sequence
from typing import Any


def ensure_neighbor_entry(
    atom_neighbors: MutableMapping[int, set[int]],
    atom_id: int,
) -> None:
    atom_neighbors.setdefault(atom_id, set())


def ensure_bond_index_entry(
    atom_bond_ids: MutableMapping[int, set[int]],
    atom_id: int,
) -> None:
    atom_bond_ids.setdefault(atom_id, set())


def add_neighbor_edge(
    atom_neighbors: MutableMapping[int, set[int]],
    a_id: int,
    b_id: int,
) -> None:
    atom_neighbors.setdefault(a_id, set()).add(b_id)
    atom_neighbors.setdefault(b_id, set()).add(a_id)


def remove_neighbor_edge(
    atom_neighbors: MutableMapping[int, set[int]],
    a_id: int,
    b_id: int,
) -> bool:
    changed = False
    neighbors_a = atom_neighbors.get(a_id)
    if neighbors_a is not None and b_id in neighbors_a:
        neighbors_a.remove(b_id)
        changed = True
    neighbors_b = atom_neighbors.get(b_id)
    if neighbors_b is not None and a_id in neighbors_b:
        neighbors_b.remove(a_id)
        changed = True
    return changed


def add_bond_to_atom_index(
    atom_bond_ids: MutableMapping[int, set[int]],
    bond_id: int,
    a_id: int,
    b_id: int,
) -> None:
    atom_bond_ids.setdefault(a_id, set()).add(bond_id)
    atom_bond_ids.setdefault(b_id, set()).add(bond_id)


def remove_bond_from_atom_index(
    atom_bond_ids: MutableMapping[int, set[int]],
    bond_id: int,
    a_id: int,
    b_id: int,
) -> None:
    bonds_a = atom_bond_ids.get(a_id)
    if bonds_a is not None:
        bonds_a.discard(bond_id)
    bonds_b = atom_bond_ids.get(b_id)
    if bonds_b is not None:
        bonds_b.discard(bond_id)


def bond_matches_atoms(bond: Any, a_id: int, b_id: int) -> bool:
    if bond is None:
        return False
    return (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id)


def first_matching_bond_id(
    bonds: Iterable[Any],
    a_id: int,
    b_id: int,
    *,
    skip_bond_id: int | None = None,
) -> int | None:
    for bond_id, bond in enumerate(bonds):
        if skip_bond_id is not None and bond_id == skip_bond_id:
            continue
        if bond_matches_atoms(bond, a_id, b_id):
            return bond_id
    return None


def bond_id_between_indexed_atoms(
    atom_bond_ids: MutableMapping[int, set[int]],
    bonds: Iterable[Any],
    a_id: int,
    b_id: int,
    *,
    bond_for_id: Callable[[int], Any | None],
    skip_bond_id: int | None = None,
) -> int | None:
    if a_id == b_id:
        return None
    bonds_a = atom_bond_ids.get(a_id)
    bonds_b = atom_bond_ids.get(b_id)
    if bonds_a is None or bonds_b is None:
        return first_matching_bond_id(
            bonds,
            a_id,
            b_id,
            skip_bond_id=skip_bond_id,
        )
    if not bonds_a or not bonds_b:
        return first_matching_bond_id(
            bonds,
            a_id,
            b_id,
            skip_bond_id=skip_bond_id,
        )
    shared = bonds_a & bonds_b
    if skip_bond_id is not None and skip_bond_id in shared:
        shared = set(shared)
        shared.discard(skip_bond_id)
    if not shared:
        return None
    for bond_id in sorted(shared):
        if bond_matches_atoms(bond_for_id(bond_id), a_id, b_id):
            return bond_id
    return first_matching_bond_id(
        bonds,
        a_id,
        b_id,
        skip_bond_id=skip_bond_id,
    )


def build_bond_adjacency_index(
    atom_ids: Iterable[int],
    bonds: Iterable[Any],
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    atom_neighbors: dict[int, set[int]] = {atom_id: set() for atom_id in atom_ids}
    atom_bond_ids: dict[int, set[int]] = {atom_id: set() for atom_id in atom_ids}
    for bond_id, bond in enumerate(bonds):
        if bond is None:
            continue
        atom_neighbors.setdefault(bond.a, set()).add(bond.b)
        atom_neighbors.setdefault(bond.b, set()).add(bond.a)
        atom_bond_ids.setdefault(bond.a, set()).add(bond_id)
        atom_bond_ids.setdefault(bond.b, set()).add(bond_id)
    return atom_neighbors, atom_bond_ids


def bond_sets_for_atom_ids(
    atom_ids: set[int],
    atom_bond_ids: MutableMapping[int, set[int]],
    bonds: Sequence[Any],
    *,
    bond_for_id: Callable[[int], Any | None],
) -> tuple[set[int], set[int]]:
    internal: set[int] = set()
    boundary: set[int] = set()
    if not atom_ids:
        return internal, boundary
    bond_ids: set[int] = set()
    # Atoms with missing or empty index entries get a scan fallback, mirroring
    # bond_id_between_indexed_atoms: those entries cannot prove that no model
    # bond exists.
    scan_atom_ids: set[int] = set()
    for atom_id in atom_ids:
        indexed = atom_bond_ids.get(atom_id)
        if indexed:
            bond_ids.update(indexed)
        else:
            scan_atom_ids.add(atom_id)
    if scan_atom_ids:
        for bond_id, bond in enumerate(bonds):
            if bond is None:
                continue
            if bond.a in scan_atom_ids or bond.b in scan_atom_ids:
                bond_ids.add(bond_id)
    for bond_id in bond_ids:
        bond = bond_for_id(bond_id)
        if bond is None:
            continue
        a_in = bond.a in atom_ids
        b_in = bond.b in atom_ids
        if a_in and b_in:
            internal.add(bond_id)
        elif a_in or b_in:
            boundary.add(bond_id)
    return internal, boundary


__all__ = [
    "add_bond_to_atom_index",
    "add_neighbor_edge",
    "bond_id_between_indexed_atoms",
    "bond_matches_atoms",
    "bond_sets_for_atom_ids",
    "build_bond_adjacency_index",
    "ensure_bond_index_entry",
    "ensure_neighbor_entry",
    "first_matching_bond_id",
    "remove_bond_from_atom_index",
    "remove_neighbor_edge",
]
