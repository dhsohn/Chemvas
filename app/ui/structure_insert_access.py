from __future__ import annotations

from typing import Any

from ui.atom_label_access import add_or_update_atom_label, atom_label_service
from ui.bond_graphics_access import add_bond_graphics_for
from ui.canvas_model_access import (
    atom_for_id,
    bond_count_for,
    bond_for_id,
    bond_ids_from,
    bonds_for,
    created_atom_ids_from,
    next_atom_id_for,
    remove_atom_direct_for,
    set_next_atom_id_for,
    trim_bonds_direct_for,
)
from ui.canvas_service_ports import structure_insert_build_service_for_access
from ui.history_canvas_access import remove_atom_for_history, trim_bonds_for_history
from ui.history_recording_access import record_additions_for
from ui.selection_style_access import restore_selection_from_ids_for
from ui.structure_mutation_access import (
    add_atom_for,
    add_benzene_ring_for,
    add_bond_for,
)


def insert_next_atom_id_for(canvas) -> int:
    return next_atom_id_for(canvas)


def insert_bond_count_for(canvas) -> int:
    return bond_count_for(canvas)


def add_insert_atom_for(canvas, element: str, x: float, y: float) -> int:
    return add_atom_for(canvas, element, x, y)


def add_insert_bond_for(canvas, a_id: int, b_id: int, order: int = 1) -> int:
    return add_bond_for(canvas, a_id, b_id, order)


def insert_atom_for_id(canvas, atom_id: int):
    return atom_for_id(canvas, atom_id)


def insert_bond_for_id(canvas, bond_id: int | None):
    return bond_for_id(canvas, bond_id)


def new_insert_bond_ids_from(canvas, start: int) -> range:
    return bond_ids_from(canvas, start)


def add_insert_bond_graphics_for(canvas, bond_id: int) -> None:
    add_bond_graphics_for(canvas, bond_id)


def has_insert_mutation_since_for(canvas, before_next_atom_id: int, before_bond_count: int) -> bool:
    return insert_next_atom_id_for(canvas) != before_next_atom_id or insert_bond_count_for(canvas) != before_bond_count


def set_inserted_atom_metadata_for(canvas, atom_id: int, *, color: str | None, explicit_label: bool) -> bool:
    atom = insert_atom_for_id(canvas, atom_id)
    if atom is None:
        return False
    atom.color = color
    atom.explicit_label = explicit_label
    return True


def set_inserted_bond_metadata_for(canvas, bond_id: int, *, style: str, color: str | None) -> bool:
    bond = insert_bond_for_id(canvas, bond_id)
    if bond is None:
        return False
    bond.style = style
    bond.color = color
    return True


def add_insert_benzene_ring_for(
    canvas,
    center,
    *,
    attach_atom_id: int | None = None,
    attach_bond_id: int | None = None,
    before_smiles_input: str | None = None,
):
    return add_benzene_ring_for(
        canvas,
        center,
        attach_atom_id=attach_atom_id,
        attach_bond_id=attach_bond_id,
        before_smiles_input=before_smiles_input,
    )


def ensure_insert_carbon_dot_for(canvas, atom_id: int) -> None:
    atom_label_service(canvas).ensure_carbon_dot(atom_id)


def add_or_update_insert_atom_label_for(canvas, atom_id: int, element: str, **kwargs) -> None:
    add_or_update_atom_label(canvas, atom_id, element, **kwargs)


def record_insert_additions_for(
    canvas,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: str | None,
    added_scene_items: list | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "before_next_atom_id": before_next_atom_id,
        "before_bond_count": before_bond_count,
        "before_smiles_input": before_smiles_input,
    }
    if added_scene_items is not None:
        kwargs["added_scene_items"] = added_scene_items
    record_additions_for(canvas, **kwargs)


def add_atom_with_merge_for(canvas, point, element: str, merge: list) -> int:
    return structure_insert_build_service_for_access(canvas).add_atom_with_merge(point, element, merge)


def insert_bond_exists_for(canvas, a_id: int, b_id: int, *, bond_exists=None) -> bool:
    if bond_exists is not None:
        return bool(bond_exists(a_id, b_id))
    return any(
        bond is not None and ((bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id))
        for bond in bonds_for(canvas)
    )


def add_insert_ring_from_points_for(
    canvas,
    points,
    elements: list[str] | None = None,
    merge: list | None = None,
) -> list[int]:
    kwargs = {}
    if elements is not None:
        kwargs["elements"] = elements
    if merge is not None:
        kwargs["merge"] = merge
    return structure_insert_build_service_for_access(canvas).add_ring_from_points(points, **kwargs)


def restore_insert_selection_from_ids_for(canvas, atom_ids: set[int], bond_ids: set[int]) -> None:
    restore_selection_from_ids_for(canvas, atom_ids, bond_ids)


def rollback_insert_mutation_for(canvas, *, before_next_atom_id: int, before_bond_count: int) -> None:
    try:
        trim_bonds_for_history(canvas, before_bond_count)
    except AttributeError:
        trim_bonds_direct_for(canvas, before_bond_count)

    for atom_id in created_atom_ids_from(canvas, before_next_atom_id):
        try:
            remove_atom_for_history(canvas, atom_id)
        except AttributeError:
            remove_atom_direct_for(canvas, atom_id)

    set_next_atom_id_for(canvas, before_next_atom_id)


__all__ = [
    "add_atom_with_merge_for",
    "add_insert_atom_for",
    "add_insert_benzene_ring_for",
    "add_insert_bond_for",
    "add_insert_bond_graphics_for",
    "add_insert_ring_from_points_for",
    "add_or_update_insert_atom_label_for",
    "ensure_insert_carbon_dot_for",
    "has_insert_mutation_since_for",
    "insert_atom_for_id",
    "insert_bond_count_for",
    "insert_bond_exists_for",
    "insert_bond_for_id",
    "insert_next_atom_id_for",
    "new_insert_bond_ids_from",
    "record_insert_additions_for",
    "restore_insert_selection_from_ids_for",
    "rollback_insert_mutation_for",
    "set_inserted_atom_metadata_for",
    "set_inserted_bond_metadata_for",
]
