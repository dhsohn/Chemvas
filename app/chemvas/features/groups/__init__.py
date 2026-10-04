"""Group membership rules shared by the desktop canvas and the browser adapter.

A group holds whole molecules (atom ids) and standalone annotations (record
ids). Callers own the id spaces; these rules only compare and combine them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.domain.document.groups import SceneGroup
from chemvas.domain.document.schema import VALID_ARROW_KINDS
from chemvas.features.graph import (
    adjacency_for_bonds,
    connected_components_for_nodes,
    reachable_from,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from chemvas.domain.document import Bond

GROUPABLE_STANDALONE_KINDS = frozenset(
    {"note", "image", "ts_bracket", "shape", "orbital"}
) | frozenset(VALID_ARROW_KINDS)

# Saved group item references name these state collections.
GROUP_ITEM_COLLECTIONS = (
    "images",
    "notes",
    "marks",
    "arrows",
    "ts_brackets",
    "shapes",
    "orbitals",
)

GROUP_CONNECTION_MESSAGE = (
    "These structures belong to different groups. Select both structures, "
    "use Edit > Group, then retry the connection."
)

GROUP_SIZE_MESSAGE = (
    "Group needs at least two objects: a molecule is one object. "
    "Select its caption or another object too, then use Edit > Group."
)


def group_ids_for_members(
    groups: Mapping[int, SceneGroup],
    atom_ids: set[int],
    item_ids: Iterable[int],
) -> set[int]:
    """Groups that hold any of the atoms or items."""
    items = set(item_ids)
    return {
        group_id
        for group_id, group in groups.items()
        if group.atom_ids & atom_ids or items.intersection(group.item_ids)
    }


def connection_allowed(
    groups: Mapping[int, SceneGroup],
    bonds: Iterable[Bond | None],
    anchors: set[int],
) -> bool:
    """Whether joining the anchors' molecules keeps every molecule in one group."""
    if len(groups) < 2:
        return True
    connected = reachable_from(anchors, adjacency_for_bonds(bonds))
    return len(group_ids_for_members(groups, connected, ())) < 2


def growth_anchors(
    bonds: Sequence[Bond | None],
    *,
    atom_id: int | None = None,
    bond_id: int | None = None,
) -> set[int]:
    """Atoms a growth shortcut attaches to: the hovered atom or bond ends."""
    anchors = {atom_id} if atom_id is not None else set()
    if bond_id is not None and 0 <= bond_id < len(bonds):
        bond = bonds[bond_id]
        if bond is not None:
            anchors.update((bond.a, bond.b))
    return anchors


def group_extensions(
    groups: Mapping[int, SceneGroup],
    bonds: Sequence[Bond | None],
    bond_ids: Iterable[int],
) -> dict[int, set[int]]:
    """New atom sets for groups whose molecule new bonds connected to more atoms.

    Raises ``ValueError`` when a new bond joined two groups' molecules.
    """
    if not groups:
        return {}
    touched = {
        atom_id
        for bond_id in bond_ids
        if (bond := bonds[bond_id]) is not None
        for atom_id in (bond.a, bond.b)
    }
    adjacency = adjacency_for_bonds(bonds)
    updates: dict[int, set[int]] = {}
    while touched:
        component = reachable_from({min(touched)}, adjacency)
        touched -= component
        owners = group_ids_for_members(groups, component, ())
        if len(owners) > 1:
            raise ValueError(GROUP_CONNECTION_MESSAGE)
        if owners:
            owner = next(iter(owners))
            updates.setdefault(owner, set(groups[owner].atom_ids)).update(component)
    return {
        group_id: atom_ids
        for group_id, atom_ids in sorted(updates.items())
        if atom_ids != groups[group_id].atom_ids
    }


def group_atoms_after_merge(
    groups: Mapping[int, SceneGroup],
    bonds: Iterable[Bond | None],
    survivor_id: int,
    removed_atom_ids: set[int],
) -> tuple[int, set[int]] | None:
    """The one group that keeps a merged atom's molecule, with its new atoms.

    Raises ``ValueError`` when the merge joined two groups' molecules.
    """
    if not groups or not removed_atom_ids:
        return None
    component = reachable_from({survivor_id}, adjacency_for_bonds(bonds))
    owners = group_ids_for_members(groups, component | removed_atom_ids, ())
    if len(owners) > 1:
        raise ValueError(GROUP_CONNECTION_MESSAGE)
    if not owners:
        return None
    group_id = next(iter(owners))
    previous = groups[group_id].atom_ids
    atom_ids = (previous - removed_atom_ids) | component
    return None if atom_ids == previous else (group_id, atom_ids)


@dataclass(frozen=True, slots=True)
class GroupingPlan:
    atom_ids: set[int]
    item_ids: list[int]
    absorbed: list[int]


def grouping_plan(
    groups: Mapping[int, SceneGroup],
    bonds: Iterable[Bond | None],
    atom_ids: set[int],
    item_ids: Sequence[int],
) -> GroupingPlan | None:
    """Plan Edit > Group for the selected atoms and standalone items.

    The group takes whole molecules and absorbs every group it overlaps. None
    means nothing changes. Raises ``ValueError`` when fewer than two objects
    would form a new group.
    """
    if not atom_ids and not item_ids:
        return None
    # A persistent group owns whole molecules; a group of partial molecules
    # would stretch bonds to ungrouped atoms when dragged.
    adjacency = adjacency_for_bonds(bonds)
    atom_ids = reachable_from(atom_ids, adjacency)
    overlapping = group_ids_for_members(groups, atom_ids, item_ids)
    if (
        not overlapping
        and len(connected_components_for_nodes(atom_ids, adjacency)) + len(item_ids) < 2
    ):
        raise ValueError(GROUP_SIZE_MESSAGE)
    merged_atom_ids = set(atom_ids)
    merged_items = list(item_ids)
    absorbed_ids: set[int] = set()
    # Older documents may hold partial-molecule groups; absorbing one also
    # absorbs groups its remaining molecule atoms reach.
    while remaining := overlapping - absorbed_ids:
        for group_id in sorted(remaining):
            for member in groups[group_id].item_ids:
                if member not in merged_items:
                    merged_items.append(member)
            merged_atom_ids |= groups[group_id].atom_ids
        absorbed_ids |= remaining
        merged_atom_ids = reachable_from(merged_atom_ids, adjacency)
        overlapping = group_ids_for_members(groups, merged_atom_ids, merged_items)
    if len(overlapping) == 1:
        existing = groups[next(iter(overlapping))]
        if merged_atom_ids <= existing.atom_ids and all(
            item in existing.item_ids for item in merged_items
        ):
            return None
    return GroupingPlan(merged_atom_ids, merged_items, sorted(overlapping))


def snapshot_groups(
    groups: Mapping[int, SceneGroup],
    live_atom_ids: Iterable[int],
    item_refs: Mapping[int, tuple[str, int]],
) -> list[dict[str, Any]]:
    """Saved group records, keeping only live members.

    Groups are disjoint at runtime; the first group keeps a member that drifted
    into two, since overlapping members fail validation. Emptied groups go.
    """
    live = set(live_atom_ids)
    saved: list[dict[str, Any]] = []
    seen_atoms: set[int] = set()
    seen_refs: set[tuple[str, int]] = set()
    for group_id in sorted(groups):
        group = groups[group_id]
        atoms = sorted(
            atom_id
            for atom_id in group.atom_ids
            if atom_id in live and atom_id not in seen_atoms
        )
        refs = [
            item_refs[item]
            for item in group.item_ids
            if item in item_refs and item_refs[item] not in seen_refs
        ]
        if not atoms and not refs:
            continue
        seen_atoms.update(atoms)
        seen_refs.update(refs)
        saved.append({"atoms": atoms, "items": [list(ref) for ref in refs]})
    return saved


def restored_groups(
    records: Iterable[Mapping[str, object]],
    live_atom_ids: Iterable[int],
    item_lists: Mapping[str, Sequence[int]],
) -> list[SceneGroup]:
    """Runtime groups for saved records, in saved order, skipping empty ones."""
    live = set(live_atom_ids)
    restored = []
    for record in records:
        atom_ids = {
            int(atom_id)
            for atom_id in record.get("atoms", [])  # type: ignore[attr-defined]
            if int(atom_id) in live
        }
        items = []
        for kind, index in record.get("items", []):  # type: ignore[attr-defined]
            candidates = item_lists.get(kind, ())
            if 0 <= index < len(candidates):
                items.append(candidates[index])
        if atom_ids or items:
            restored.append(SceneGroup(atom_ids, items))
    return restored


__all__ = [
    "GROUPABLE_STANDALONE_KINDS",
    "GROUP_CONNECTION_MESSAGE",
    "GROUP_ITEM_COLLECTIONS",
    "GROUP_SIZE_MESSAGE",
    "GroupingPlan",
    "connection_allowed",
    "group_atoms_after_merge",
    "group_extensions",
    "group_ids_for_members",
    "grouping_plan",
    "growth_anchors",
    "restored_groups",
    "snapshot_groups",
]
