from __future__ import annotations

from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_model_access import atom_for_id, model_for


def extend_bounds_with_item_rect(xs: list[float], ys: list[float], item) -> None:
    if item is None:
        return
    rect = item.sceneBoundingRect()
    xs.extend([rect.left(), rect.right()])
    ys.extend([rect.top(), rect.bottom()])


def bounds_for_atoms_for(canvas, atom_ids: set[int], include_labels: bool = False):
    xs = []
    ys = []
    for atom_id in atom_ids:
        atom = atom_for_id(canvas, atom_id)
        if atom is None:
            continue
        xs.append(atom.x)
        ys.append(atom.y)
        if include_labels:
            extend_bounds_with_item_rect(xs, ys, atom_items_for(canvas).get(atom_id))
            extend_bounds_with_item_rect(xs, ys, atom_dots_for(canvas).get(atom_id))
    if not xs:
        return model_for(canvas).bounds()
    return min(xs), min(ys), max(xs), max(ys)


__all__ = ["bounds_for_atoms_for", "extend_bounds_with_item_rect"]
