"""Shared deletion planning; Qt item classification stays at its input boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    bond_endpoint_ids,
    orphaned_atom_ids,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem, QGraphicsTextItem

    from chemvas.domain.document import Bond


@dataclass(slots=True, kw_only=True)
class DeleteSelectionBuckets:
    atom_ids: set[int] = field(default_factory=set)
    bond_ids: set[int] = field(default_factory=set)
    ring_items: list[QGraphicsPolygonItem] = field(default_factory=list)
    note_items: list[QGraphicsTextItem] = field(default_factory=list)
    mark_items: list[QGraphicsItem] = field(default_factory=list)
    arrow_items: list[QGraphicsItem] = field(default_factory=list)
    ts_bracket_items: list[QGraphicsItem] = field(default_factory=list)
    orbital_items: list[QGraphicsItem] = field(default_factory=list)
    other_items: list[QGraphicsItem] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class DeleteSelectionPlan:
    bond_ids_to_remove: list[int] = field(default_factory=list)
    atom_ids: list[int] = field(default_factory=list)
    scene_items: list[QGraphicsItem] = field(default_factory=list)
    mark_owner_ids: set[int] = field(default_factory=set)
    clear_handles: bool = False


def classify_delete_selection(items: Sequence[QGraphicsItem]) -> DeleteSelectionBuckets:
    from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsTextItem

    buckets = DeleteSelectionBuckets()
    for item in items:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                buckets.atom_ids.add(atom_id)
        elif kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                buckets.bond_ids.add(bond_id)
        elif kind == "ring":
            if isinstance(item, QGraphicsPolygonItem):
                buckets.ring_items.append(item)
        elif kind == "note":
            if isinstance(item, QGraphicsTextItem):
                buckets.note_items.append(item)
        elif kind == "mark":
            buckets.mark_items.append(item)
        elif kind in VALID_ARROW_KINDS:
            buckets.arrow_items.append(item)
        elif kind == "ts_bracket":
            buckets.ts_bracket_items.append(item)
        elif kind == "orbital":
            buckets.orbital_items.append(item)
        elif kind in {"handle", "note_box", "note_select"}:
            continue
        else:
            buckets.other_items.append(item)
    return buckets


def build_delete_selection_plan(
    selection: DeleteSelectionBuckets,
    *,
    bonds: Sequence[Bond | None],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
    atom_has_visible_label: Callable[[int], bool],
) -> DeleteSelectionPlan:
    bonds_to_remove = {
        bond_id
        for bond_id in selection.bond_ids
        if 0 <= bond_id < len(bonds) and bonds[bond_id] is not None
    }
    for bond_id, bond in enumerate(bonds):
        if bond is None:
            continue
        if bond.a in selection.atom_ids or bond.b in selection.atom_ids:
            bonds_to_remove.add(bond_id)

    # Marks selected for this same deletion cannot keep an endpoint visible:
    # they die with it, so counting them would leave an invisible orphan.
    selected_mark_item_ids = {id(item) for item in selection.mark_items}
    atom_ids_to_remove = set(selection.atom_ids)
    atom_ids_to_remove.update(
        orphaned_atom_ids(
            bonds,
            candidate_atom_ids=bond_endpoint_ids(bonds, bonds_to_remove),
            removed_bond_ids=bonds_to_remove,
            removed_atom_ids=atom_ids_to_remove,
            keeps_visible=lambda atom_id: (
                atom_has_visible_label(atom_id)
                or any(
                    id(mark) not in selected_mark_item_ids
                    for mark in marks_by_atom.get(atom_id, ())
                )
            ),
        )
    )

    # Bound and standalone marks share one scene-item history owner. Keep the
    # original objects, including marks selected both directly and via an atom.
    marks = list(selection.mark_items)
    mark_ids = {id(mark) for mark in marks}
    for atom_id in sorted(atom_ids_to_remove):
        for mark in marks_by_atom.get(atom_id, []):
            if id(mark) not in mark_ids:
                marks.append(mark)
                mark_ids.add(id(mark))

    scene_items: list[QGraphicsItem] = []
    scene_items.extend(selection.ring_items)
    scene_items.extend(selection.note_items)
    scene_items.extend(marks)
    scene_items.extend(selection.arrow_items)
    scene_items.extend(selection.ts_bracket_items)
    scene_items.extend(selection.orbital_items)
    scene_items.extend(selection.other_items)

    return DeleteSelectionPlan(
        bond_ids_to_remove=sorted(bonds_to_remove, reverse=True),
        atom_ids=sorted(atom_ids_to_remove),
        scene_items=scene_items,
        mark_owner_ids={
            owner_id
            for item in marks
            if isinstance(owner_id := (item.data(1) or {}).get("atom_id"), int)
        }
        - atom_ids_to_remove,
        clear_handles=bool(
            scene_items
            and (
                selection.arrow_items
                or selection.ts_bracket_items
                or selection.orbital_items
            )
        ),
    )


def hover_delete_target(
    atom_id: int | None,
    bond_id: int | None,
    *,
    bonds: Sequence[Bond | None],
    atom_has_visible_label: Callable[[int], bool],
) -> tuple[str, int] | None:
    """Native Delete strips a bonded label before removing its atom."""
    if atom_id is not None:
        has_bond = any(
            bond is not None
            and atom_id in (getattr(bond, "a", None), getattr(bond, "b", None))
            for bond in bonds
        )
        # Delete strips a bonded atom's label first. A lone labelled atom
        # has nothing to fall back to: hiding its label would leave an
        # invisible carbon on the sheet, so it is deleted outright.
        if atom_has_visible_label(atom_id) and has_bond:
            return "label", atom_id
        return "atom", atom_id
    if bond_id is not None:
        return "bond", bond_id
    return None


__all__ = [
    "DeleteSelectionBuckets",
    "DeleteSelectionPlan",
    "build_delete_selection_plan",
    "classify_delete_selection",
    "hover_delete_target",
]
