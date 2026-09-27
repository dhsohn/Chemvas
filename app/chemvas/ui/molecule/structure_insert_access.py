from __future__ import annotations

from typing import Any

from chemvas.ui.molecule.atom_label_access import add_or_update_atom_label


def has_insert_mutation_since_for(
    canvas, before_next_atom_id: int, before_bond_count: int
) -> bool:
    return (
        int(canvas.model.next_atom_id) != before_next_atom_id
        or len(canvas.model.bonds) != before_bond_count
    )


def set_inserted_atom_metadata_for(
    canvas, atom_id: int, *, color: str | None, explicit_label: bool
) -> bool:
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return False
    atom.color = color
    atom.explicit_label = explicit_label
    return True


def set_inserted_atom_annotation_for(
    canvas, atom_id: int, annotation: dict[str, int] | None
) -> bool:
    if canvas.model.atom_for_id(atom_id) is None:
        return False
    canvas.model.set_atom_annotation(atom_id, annotation)
    return True


def set_inserted_bond_metadata_for(
    canvas, bond_id: int, *, style: str, color: str | None
) -> bool:
    bond = canvas.model.bond_for_id(bond_id)
    if bond is None:
        return False
    bond.style = style
    bond.color = color
    return True


def add_or_update_insert_atom_label_for(
    canvas, atom_id: int, element: str, **kwargs
) -> None:
    add_or_update_atom_label(canvas, atom_id, element, **kwargs)


def record_insert_additions_for(
    canvas,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    added_scene_items: list | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "before_next_atom_id": before_next_atom_id,
        "before_bond_count": before_bond_count,
    }
    if added_scene_items is not None:
        kwargs["added_scene_items"] = added_scene_items
    canvas.services.canvas_history_recording_service.record_additions(**kwargs)


def insert_bond_exists_for(canvas, a_id: int, b_id: int, *, bond_exists=None) -> bool:
    if bond_exists is not None:
        return bool(bond_exists(a_id, b_id))
    return any(
        bond is not None
        and ((bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id))
        for bond in canvas.model.bonds
    )


def build_insert_benzene_ring_for(
    canvas,
    center,
    *,
    attach_atom_id: int | None = None,
    attach_bond_id: int | None = None,
) -> object | None:
    return canvas.services.structure_build_service.build_benzene_ring(
        center,
        attach_atom_id=attach_atom_id,
        attach_bond_id=attach_bond_id,
    )


def add_insert_ring_from_points_for(
    canvas,
    points,
    elements: list[str] | None = None,
    merge: list | None = None,
) -> list[int]:
    return canvas.services.structure_build_service.add_ring_from_points(
        points,
        elements=elements,
        merge=merge,
    )


__all__ = [
    "add_insert_ring_from_points_for",
    "add_or_update_insert_atom_label_for",
    "build_insert_benzene_ring_for",
    "has_insert_mutation_since_for",
    "insert_bond_exists_for",
    "record_insert_additions_for",
    "set_inserted_atom_annotation_for",
    "set_inserted_atom_metadata_for",
    "set_inserted_bond_metadata_for",
]
