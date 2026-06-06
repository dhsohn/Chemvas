from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    set_atom_dots_for,
    set_atom_items_for,
)
from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
from ui.canvas_model_state import model_for, set_model_for
from ui.canvas_scene_items_state import ring_items_for
from ui.scene_item_access import (
    clear_canvas_scene_item_list_map,
    clear_canvas_scene_item_map,
)
from ui.structure_build_ports import structure_build_service_for_access


def atoms_for(canvas: Any) -> Any:
    return model_for(canvas).atoms


def add_atom_to_model_for(canvas: Any, element: str, x: float, y: float) -> int:
    return model_for(canvas).add_atom(element, x, y)


def bonds_for(canvas: Any) -> Any:
    return model_for(canvas).bonds


def add_bond_to_model_for(canvas: Any, a_id: int, b_id: int, order: int = 1) -> int:
    return model_for(canvas).add_bond(a_id, b_id, order)


def next_atom_id_for(canvas: Any) -> int:
    return int(model_for(canvas).next_atom_id)


def set_next_atom_id_for(canvas: Any, atom_id: int) -> None:
    model_for(canvas).next_atom_id = atom_id


def ensure_next_atom_id_after_for(canvas: Any, atom_id: int) -> None:
    if atom_id >= next_atom_id_for(canvas):
        set_next_atom_id_for(canvas, atom_id + 1)


def bond_count_for(canvas: Any) -> int:
    return len(bonds_for(canvas))


def bond_ids_from(canvas: Any, start: int) -> range:
    return range(start, bond_count_for(canvas))


def has_bond_slot_for(canvas: Any, bond_id: int) -> bool:
    return 0 <= bond_id < bond_count_for(canvas)


def atom_for_id(canvas: Any, atom_id: int | None) -> Any | None:
    if atom_id is None:
        return None
    return atoms_for(canvas).get(atom_id)


def required_atom_for(canvas: Any, atom_id: int) -> Any:
    return atoms_for(canvas)[atom_id]


def set_atom_for_id(canvas: Any, atom_id: int, atom: Any) -> None:
    atoms_for(canvas)[atom_id] = atom


def bond_for_id(canvas: Any, bond_id: int | None) -> Any | None:
    if bond_id is None or bond_id < 0:
        return None
    bonds = bonds_for(canvas)
    try:
        return bonds[bond_id]
    except (IndexError, KeyError, TypeError):
        return None


def created_atom_ids_from(canvas: Any, before_next_atom_id: int) -> list[int]:
    return sorted(
        (atom_id for atom_id in atoms_for(canvas) if atom_id >= before_next_atom_id),
        reverse=True,
    )


def remove_atom_direct_for(canvas: Any, atom_id: int) -> None:
    atoms_for(canvas).pop(atom_id, None)


def clear_bond_for_id(canvas: Any, bond_id: int) -> None:
    bonds = bonds_for(canvas)
    if 0 <= bond_id < len(bonds):
        bonds[bond_id] = None


def set_bond_for_id(canvas: Any, bond_id: int, bond: Any) -> None:
    bonds = bonds_for(canvas)
    if bond_id < len(bonds):
        bonds[bond_id] = bond
        return
    bonds.extend([None] * (bond_id - len(bonds)))
    bonds.append(bond)


def trim_bonds_direct_for(canvas: Any, length: int) -> None:
    bonds = bonds_for(canvas)
    if len(bonds) > length:
        del bonds[length:]


def has_atoms_for(canvas: Any) -> bool:
    return bool(atoms_for(canvas))


def rescale_model_for(canvas, scale: float) -> None:
    atoms = atoms_for(canvas)
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


def rebuild_graphics_for(canvas) -> None:
    set_bond_items_for(canvas, clear_canvas_scene_item_list_map(canvas, bond_items_for(canvas)))
    set_atom_items_for(canvas, clear_canvas_scene_item_map(canvas, atom_items_for(canvas)))
    set_atom_dots_for(canvas, clear_canvas_scene_item_map(canvas, atom_dots_for(canvas)))
    structure_build_service_for_access(canvas).render_model()


__all__ = [
    "add_atom_to_model_for",
    "add_bond_to_model_for",
    "atom_for_id",
    "atoms_for",
    "bond_count_for",
    "bond_for_id",
    "bond_ids_from",
    "bonds_for",
    "clear_bond_for_id",
    "created_atom_ids_from",
    "ensure_next_atom_id_after_for",
    "has_atoms_for",
    "has_bond_slot_for",
    "model_for",
    "next_atom_id_for",
    "rebuild_graphics_for",
    "remove_atom_direct_for",
    "required_atom_for",
    "rescale_model_for",
    "set_bond_for_id",
    "set_atom_for_id",
    "set_model_for",
    "set_next_atom_id_for",
    "trim_bonds_direct_for",
]
