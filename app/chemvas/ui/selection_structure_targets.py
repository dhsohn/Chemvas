from __future__ import annotations

from collections.abc import Callable

from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id

STRUCTURE_OVERLAY_KINDS = {
    "arrow",
    "equilibrium",
    "resonance",
    "curved_single",
    "curved_double",
    "inhibit",
    "dotted",
    "ts_bracket",
    "shape",
    "orbital",
    "note",
    "mark",
}


def structure_selection_targets_for_item(
    canvas,
    item,
    *,
    atom_item_for_id: Callable[[int], object | None] | None = None,
) -> list:
    if item is None:
        return []
    atom_item_for_id = atom_item_for_id or (
        lambda atom_id: visible_atom_item_for(canvas, atom_id)
    )
    kind = item.data(0)
    if kind == "atom":
        atom_id = item.data(1)
        if not isinstance(atom_id, int):
            return []
        atom_item = atom_item_for_id(atom_id)
        return [atom_item] if atom_item is not None else []
    if kind == "bond":
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return []
        return [
            bond_item
            for bond_item in bond_items_for_id(canvas, bond_id)
            if bond_item is not None
        ]
    if kind == "ring" or kind in STRUCTURE_OVERLAY_KINDS:
        return [item]
    return []


__all__ = [
    "STRUCTURE_OVERLAY_KINDS",
    "structure_selection_targets_for_item",
]
