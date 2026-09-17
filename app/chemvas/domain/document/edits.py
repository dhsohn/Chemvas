"""Pure rules for what one document edit changes beyond its target.

The desktop editor and the headless Graph Patch both remove bonds; what else
that removal has to take with it (atoms left bare, ring fills that no longer
describe a bonded cycle) is a property of the document, not of the caller.
This module holds those rules once so every path computes the same answer.
The functions only compute; applying the result, recording history and
refreshing the scene stay with the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .state import ring_atom_ids_form_cycle

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Sequence

    from .model import Bond


def bond_endpoint_ids(
    bonds: Sequence[Bond | None], bond_ids: Iterable[int]
) -> tuple[int, ...]:
    """The atoms at the ends of ``bond_ids``, in bond order, each once."""
    seen: dict[int, None] = {}
    for bond_id in bond_ids:
        if not (0 <= bond_id < len(bonds)):
            continue
        bond = bonds[bond_id]
        if bond is None:
            continue
        seen.setdefault(bond.a, None)
        seen.setdefault(bond.b, None)
    return tuple(seen)


def orphaned_atom_ids(
    bonds: Sequence[Bond | None],
    *,
    candidate_atom_ids: Iterable[int],
    keeps_visible: Callable[[int], bool],
    removed_bond_ids: Collection[int] = (),
    removed_atom_ids: Collection[int] = (),
    atom_exists: Callable[[int], bool] | None = None,
) -> tuple[int, ...]:
    """Candidates a bond removal leaves bare and nothing keeps on the sheet.

    A candidate survives when it keeps a bond outside ``removed_bond_ids``, is
    already being removed, no longer exists, or ``keeps_visible`` says a label
    or a mark still shows it. ``bonds`` may be the model before or after the
    removal; a removed bond that is already gone simply has no index to skip.
    The result keeps the candidates' order so callers build history in the
    same sequence they always did.
    """
    removed_bonds = set(removed_bond_ids)
    removed_atoms = set(removed_atom_ids)
    surviving: set[int] = set()
    for bond_id, bond in enumerate(bonds):
        if bond is None or bond_id in removed_bonds:
            continue
        surviving.add(bond.a)
        surviving.add(bond.b)
    orphaned: dict[int, None] = {}
    for atom_id in candidate_atom_ids:
        if atom_id in orphaned or atom_id in removed_atoms or atom_id in surviving:
            continue
        if atom_exists is not None and not atom_exists(atom_id):
            continue
        if keeps_visible(atom_id):
            continue
        orphaned[atom_id] = None
    return tuple(orphaned)


def broken_ring_fill_indices(
    ring_fill_atom_ids: Sequence[object],
    *,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
) -> tuple[int, ...]:
    """Ring fills whose atom list no longer forms a bonded cycle.

    ``ring_fill_atom_ids`` holds each fill's stored atom list as found; a
    value that is not a list of ints is broken too, since it cannot describe
    a cycle. ``atom_ids`` and ``bond_pairs`` are the document as it will be
    once the edit is applied.
    """
    return tuple(
        index
        for index, raw in enumerate(ring_fill_atom_ids)
        if not ring_fill_is_intact(raw, atom_ids=atom_ids, bond_pairs=bond_pairs)
    )


def ring_fill_is_intact(
    ring_fill_atom_ids: object,
    *,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
) -> bool:
    """Whether one fill's stored atom list still describes a bonded cycle."""
    return (
        isinstance(ring_fill_atom_ids, list)
        and all(type(atom_id) is int for atom_id in ring_fill_atom_ids)
        and ring_atom_ids_form_cycle(ring_fill_atom_ids, atom_ids, bond_pairs)
    )


__all__ = [
    "bond_endpoint_ids",
    "broken_ring_fill_indices",
    "orphaned_atom_ids",
    "ring_fill_is_intact",
]
