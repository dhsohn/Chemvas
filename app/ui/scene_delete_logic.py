from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from core.model import Bond
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem, QGraphicsTextItem

from ui.scene_item_state import ARROW_KINDS


@dataclass(slots=True)
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

    def has_single_bond_only(self) -> bool:
        return (
            len(self.bond_ids) == 1
            and not self.atom_ids
            and not self.ring_items
            and not self.note_items
            and not self.mark_items
            and not self.arrow_items
            and not self.ts_bracket_items
            and not self.orbital_items
            and not self.other_items
        )


@dataclass(slots=True)
class DeleteSelectionPlan:
    single_bond_id: int | None = None
    bond_ids_to_remove: list[int] = field(default_factory=list)
    atom_ids: list[int] = field(default_factory=list)
    mark_states_for_atoms: list[dict] = field(default_factory=list)
    scene_items: list[QGraphicsItem] = field(default_factory=list)
    clear_handles: bool = False
    clear_smiles_input: bool = False

    def has_work(self) -> bool:
        return self.single_bond_id is not None or bool(
            self.bond_ids_to_remove or self.atom_ids or self.scene_items
        )


def classify_delete_selection(items: Sequence[QGraphicsItem]) -> DeleteSelectionBuckets:
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
        elif kind in ARROW_KINDS:
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
    mark_state_getter: Callable[[QGraphicsItem], dict],
) -> DeleteSelectionPlan:
    if selection.has_single_bond_only():
        bond_id = next(iter(selection.bond_ids))
        if 0 <= bond_id < len(bonds) and bonds[bond_id] is not None:
            return DeleteSelectionPlan(single_bond_id=bond_id)

    bonds_to_remove = set(selection.bond_ids)
    for bond_id, bond in enumerate(bonds):
        if bond is None:
            continue
        if bond.a in selection.atom_ids or bond.b in selection.atom_ids:
            bonds_to_remove.add(bond_id)

    filtered_marks: list[QGraphicsItem] = []
    for item in selection.mark_items:
        data = item.data(1) or {}
        atom_id = data.get("atom_id")
        if isinstance(atom_id, int) and atom_id in selection.atom_ids:
            continue
        filtered_marks.append(item)

    mark_states_for_atoms: list[dict] = []
    for atom_id in sorted(selection.atom_ids):
        for mark in marks_by_atom.get(atom_id, []):
            mark_states_for_atoms.append(mark_state_getter(mark))

    scene_items: list[QGraphicsItem] = []
    scene_items.extend(selection.ring_items)
    scene_items.extend(selection.note_items)
    scene_items.extend(filtered_marks)
    scene_items.extend(selection.arrow_items)
    scene_items.extend(selection.ts_bracket_items)
    scene_items.extend(selection.orbital_items)
    scene_items.extend(selection.other_items)

    return DeleteSelectionPlan(
        bond_ids_to_remove=sorted(bonds_to_remove, reverse=True),
        atom_ids=sorted(selection.atom_ids),
        mark_states_for_atoms=mark_states_for_atoms,
        scene_items=scene_items,
        clear_handles=bool(scene_items and (selection.arrow_items or selection.ts_bracket_items or selection.orbital_items)),
        clear_smiles_input=bool(bonds_to_remove or selection.atom_ids),
    )


__all__ = [
    "DeleteSelectionBuckets",
    "DeleteSelectionPlan",
    "build_delete_selection_plan",
    "classify_delete_selection",
]
