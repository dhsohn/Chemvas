from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from chemvas.domain.document.marks import mark_kinds_by_atom
from chemvas.features.insertion import build_atom_annotations
from chemvas.ui.canvas.canvas_scene_items_state import ring_items_for


def add_bond_to_model_for(canvas: Any, a_id: int, b_id: int, order: int = 1) -> int:
    return canvas.model.add_bond(a_id, b_id, order)


def ensure_next_atom_id_after_for(canvas: Any, atom_id: int) -> None:
    if atom_id >= int(canvas.model.next_atom_id):
        canvas.model.next_atom_id = atom_id + 1


def bond_ids_from(canvas: Any, start: int) -> range:
    return range(start, len(canvas.model.bonds))


def has_bond_slot_for(canvas: Any, bond_id: int) -> bool:
    return 0 <= bond_id < len(canvas.model.bonds)


def atom_for_id(canvas: Any, atom_id: int | None) -> Any | None:
    if atom_id is None:
        return None
    return canvas.model.atoms.get(atom_id)


def set_atom_for_id(canvas: Any, atom_id: int, atom: Any) -> None:
    canvas.model.atoms[atom_id] = atom
    clear_atom_annotation_for(canvas, atom_id)


def bond_for_id(canvas: Any, bond_id: int | None) -> Any | None:
    if bond_id is None or bond_id < 0:
        return None
    bonds = canvas.model.bonds
    try:
        return bonds[bond_id]
    except (IndexError, KeyError, TypeError):
        return None


def created_atom_ids_from(canvas: Any, before_next_atom_id: int) -> list[int]:
    return sorted(
        (atom_id for atom_id in canvas.model.atoms if atom_id >= before_next_atom_id),
        reverse=True,
    )


def remove_atom_direct_for(canvas: Any, atom_id: int) -> None:
    canvas.model.atoms.pop(atom_id, None)
    clear_atom_annotation_for(canvas, atom_id)


def atom_annotations_for(canvas: Any) -> dict[int, dict[str, int]]:
    model = canvas.model
    annotations = getattr(model, "atom_annotations", None)
    if isinstance(annotations, dict):
        return annotations
    annotations = {}
    model.atom_annotations = annotations
    return annotations


def atom_annotation_for(canvas: Any, atom_id: int) -> dict[str, int] | None:
    annotation = atom_annotations_for(canvas).get(atom_id)
    if not isinstance(annotation, Mapping):
        return None
    return {
        str(key): int(value)
        for key, value in annotation.items()
        if key in {"formal_charge", "radical_electrons"} and type(value) is int
    }


def set_atom_annotation_for(
    canvas: Any, atom_id: int, annotation: Mapping[str, int] | None
) -> None:
    annotations = atom_annotations_for(canvas)
    if annotation:
        annotations[atom_id] = {
            str(key): int(value)
            for key, value in annotation.items()
            if key in {"formal_charge", "radical_electrons"}
            and type(value) is int
            and value
        }
        if not annotations[atom_id]:
            annotations.pop(atom_id, None)
        return
    annotations.pop(atom_id, None)


def clear_atom_annotation_for(canvas: Any, atom_id: int) -> None:
    annotations = getattr(canvas.model, "atom_annotations", None)
    if isinstance(annotations, dict):
        annotations.pop(atom_id, None)


def sync_atom_annotation_from_marks_for(
    canvas: Any,
    atom_id: int,
) -> None:
    if atom_for_id(canvas, atom_id) is None:
        clear_atom_annotation_for(canvas, atom_id)
        return
    annotations = build_atom_annotations(
        {atom_id},
        {atom_id: atom_id},
        mark_kinds_by_atom(canvas.runtime_state.mark_state),
    )
    set_atom_annotation_for(canvas, atom_id, annotations.get(atom_id))


def clear_bond_for_id(canvas: Any, bond_id: int) -> None:
    bonds = canvas.model.bonds
    if 0 <= bond_id < len(bonds):
        bonds[bond_id] = None


def set_bond_for_id(canvas: Any, bond_id: int, bond: Any) -> None:
    bonds = canvas.model.bonds
    if bond_id < len(bonds):
        bonds[bond_id] = bond
        return
    bonds.extend([None] * (bond_id - len(bonds)))
    bonds.append(bond)


def trim_bonds_direct_for(canvas: Any, length: int) -> None:
    bonds = canvas.model.bonds
    if len(bonds) > length:
        del bonds[length:]


def rescale_model_for(canvas, scale: float) -> None:
    atoms = canvas.model.atoms
    xs = [atom.x for atom in atoms.values()]
    ys = [atom.y for atom in atoms.values()]
    center_x = sum(xs) / len(xs)
    center_y = sum(ys) / len(ys)

    for atom in atoms.values():
        atom.x = center_x + (atom.x - center_x) * scale
        atom.y = center_y + (atom.y - center_y) * scale

    for ring_item in ring_items_for(canvas):
        polygon = ring_item.polygon()
        scaled = QPolygonF()
        for point in polygon:
            x = center_x + (point.x() - center_x) * scale
            y = center_y + (point.y() - center_y) * scale
            scaled.append(QPointF(x, y))
        ring_item.setPolygon(scaled)


__all__ = [
    "add_bond_to_model_for",
    "atom_annotation_for",
    "atom_annotations_for",
    "atom_for_id",
    "bond_for_id",
    "bond_ids_from",
    "clear_atom_annotation_for",
    "clear_bond_for_id",
    "created_atom_ids_from",
    "ensure_next_atom_id_after_for",
    "has_bond_slot_for",
    "remove_atom_direct_for",
    "rescale_model_for",
    "set_atom_annotation_for",
    "set_atom_for_id",
    "set_bond_for_id",
    "sync_atom_annotation_from_marks_for",
    "trim_bonds_direct_for",
]
