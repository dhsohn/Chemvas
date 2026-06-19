from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt

from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id
from ui.selection_hit_logic import build_selection_snapshot
from ui.selection_scene_access import scene_selected_items_for, selected_scene_notes_for

TRANSFORM_SELECTION_EXCLUDED_KINDS = {"handle", "note_box", "note_select", "selection_outline"}
COPY_SELECTION_EXCLUDED_KINDS = {"handle", "note_select", "selection_outline"}
STATUS_SELECTION_EXCLUDED_KINDS = {"handle", "note_box", "note_select", "selection_outline"}


def append_ring_selection_atom_ids(canvas, atom_ids: set[int], ring_atom_ids) -> None:
    if not isinstance(ring_atom_ids, list):
        return
    for atom_id in ring_atom_ids:
        if isinstance(atom_id, int) and atom_for_id(canvas, atom_id) is not None:
            atom_ids.add(atom_id)


def append_polygon_selection_atom_ids(canvas, atom_ids: set[int], polygon) -> None:
    for atom_id, atom in atoms_for(canvas).items():
        if polygon.containsPoint(QPointF(atom.x, atom.y), Qt.FillRule.WindingFill):
            atom_ids.add(atom_id)


def append_selected_item_ids(canvas, atom_ids: set[int], bond_ids: set[int], item) -> None:
    data = getattr(item, "data", None)
    if not callable(data):
        return
    kind = item.data(0)
    if kind == "atom":
        atom_id = item.data(1)
        if isinstance(atom_id, int):
            atom_ids.add(atom_id)
        return
    if kind == "bond":
        bond_id = item.data(1)
        if isinstance(bond_id, int):
            bond_ids.add(bond_id)
        return
    if kind != "ring":
        return
    ring_atom_ids = item.data(2)
    if isinstance(ring_atom_ids, list):
        append_ring_selection_atom_ids(canvas, atom_ids, ring_atom_ids)
        return
    if hasattr(item, "polygon"):
        append_polygon_selection_atom_ids(canvas, atom_ids, item.polygon())


def selected_ids_for(canvas) -> tuple[set[int], set[int]]:
    atom_ids: set[int] = set()
    bond_ids: set[int] = set()
    for item in scene_selected_items_for(canvas):
        append_selected_item_ids(canvas, atom_ids, bond_ids, item)
    return atom_ids, bond_ids


def selected_mark_atom_ids_for(canvas) -> set[int]:
    try:
        model_atoms = atoms_for(canvas)
    except AttributeError:
        model_atoms = {}
    atom_ids: set[int] = set()
    for item in scene_selected_items_for(canvas):
        data = getattr(item, "data", None)
        if not callable(data) or item.data(0) != "mark":
            continue
        mark_data = item.data(1) or {}
        atom_id = mark_data.get("atom_id") if isinstance(mark_data, dict) else None
        if isinstance(atom_id, int) and atom_id in model_atoms:
            atom_ids.add(atom_id)
    return atom_ids


def selected_chemical_ids_for(canvas) -> tuple[set[int], set[int]]:
    atom_ids, bond_ids = selected_ids_for(canvas)
    if atom_ids or bond_ids:
        return atom_ids, bond_ids
    # Scene-only items such as arrows, notes, and bracket annotations should not
    # suppress a real atom-bound annotation selection from the 3D/export path.
    atom_ids.update(selected_mark_atom_ids_for(canvas))
    return atom_ids, bond_ids


def selected_structure_ids_for(canvas, *, require_non_empty: bool = False) -> tuple[set[int], set[int]]:
    atom_ids, bond_ids = selected_chemical_ids_for(canvas)
    if require_non_empty and not atom_ids and not bond_ids:
        raise ValueError("Select a molecular structure on the canvas first.")
    return atom_ids, bond_ids


def selection_signature_for(atom_ids: set[int], bond_ids: set[int]) -> tuple[frozenset[int], frozenset[int]]:
    return frozenset(atom_ids), frozenset(bond_ids)


def selection_target_item(item) -> bool:
    return item.data(0) not in {"selection_outline", "note_box", "note_select", "handle"}


def selected_bond_atom_ids_for(canvas, bond_ids: set[int]) -> tuple[tuple[int, int], ...]:
    atom_pairs: list[tuple[int, int]] = []
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is None:
            continue
        atom_pairs.append((bond.a, bond.b))
    return tuple(atom_pairs)


def selection_snapshot_for(canvas):
    selected = tuple(scene_selected_items_for(canvas))
    if not selected:
        return None
    atom_ids, bond_ids = selected_ids_for(canvas)
    return build_selection_snapshot(
        selected_atom_ids=atom_ids,
        selected_bond_ids=bond_ids,
        selected_bond_atom_ids=selected_bond_atom_ids_for(canvas, bond_ids),
        selection_items=tuple(item for item in selected if selection_target_item(item)),
    )


def append_unique_scene_item(items: list, seen: set, item, *, excluded_kinds: set[str]) -> bool:
    if item in seen:
        return False
    if item.data(0) in excluded_kinds:
        return False
    seen.add(item)
    items.append(item)
    return True


def selected_scene_items_for(canvas, *, excluded_kinds: set[str]) -> list:
    items: list = []
    seen: set = set()
    for item in scene_selected_items_for(canvas):
        append_unique_scene_item(items, seen, item, excluded_kinds=excluded_kinds)
    for note in selected_scene_notes_for(canvas):
        append_unique_scene_item(items, seen, note, excluded_kinds=excluded_kinds)
    return items


def selection_status_item_identity(item) -> tuple[str, object]:
    kind = item.data(0)
    item_id = item.data(1)
    if kind in {"atom", "bond"} and isinstance(item_id, int):
        return str(kind), item_id
    ring_ids = item.data(2) if kind == "ring" else None
    if isinstance(ring_ids, list):
        return "ring", tuple(ring_ids)
    return "item", id(item)


def selection_status_count_for(canvas) -> int:
    identities: set[tuple[str, object]] = set()
    for item in scene_selected_items_for(canvas):
        kind = item.data(0)
        if kind in STATUS_SELECTION_EXCLUDED_KINDS:
            continue
        identities.add(selection_status_item_identity(item))
    for note in selected_scene_notes_for(canvas):
        identities.add(("note", id(note)))
    return len(identities)


def selected_items_for_transform_for(canvas) -> list:
    return selected_scene_items_for(canvas, excluded_kinds=TRANSFORM_SELECTION_EXCLUDED_KINDS)


def selection_items_for_copy_for(canvas) -> list:
    selected = selected_scene_items_for(canvas, excluded_kinds=COPY_SELECTION_EXCLUDED_KINDS)
    if not selected:
        return []
    items: list = []
    seen: set = set()

    def add_with_children(item) -> None:
        if not append_unique_scene_item(items, seen, item, excluded_kinds=COPY_SELECTION_EXCLUDED_KINDS):
            return
        for child in item.childItems():
            add_with_children(child)

    for item in selected:
        kind = item.data(0)
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                for bond_item in bond_items_for_id(canvas, bond_id):
                    add_with_children(bond_item)
                continue
        add_with_children(item)
    return items


def selected_atom_ids_for_transform_for(canvas) -> set[int]:
    atom_ids, bond_ids = selected_ids_for(canvas)
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is None:
            continue
        atom_ids.add(bond.a)
        atom_ids.add(bond.b)
    return atom_ids


__all__ = [
    "COPY_SELECTION_EXCLUDED_KINDS",
    "STATUS_SELECTION_EXCLUDED_KINDS",
    "TRANSFORM_SELECTION_EXCLUDED_KINDS",
    "append_polygon_selection_atom_ids",
    "append_ring_selection_atom_ids",
    "append_selected_item_ids",
    "append_unique_scene_item",
    "selected_atom_ids_for_transform_for",
    "selected_bond_atom_ids_for",
    "selected_chemical_ids_for",
    "selected_ids_for",
    "selected_items_for_transform_for",
    "selected_mark_atom_ids_for",
    "selected_scene_items_for",
    "selected_structure_ids_for",
    "selection_items_for_copy_for",
    "selection_signature_for",
    "selection_snapshot_for",
    "selection_status_count_for",
    "selection_status_item_identity",
    "selection_target_item",
]
