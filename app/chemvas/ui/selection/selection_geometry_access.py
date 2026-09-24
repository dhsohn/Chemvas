from __future__ import annotations

from chemvas.ui.canvas.canvas_model_access import atom_for_id


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
            extend_bounds_with_item_rect(
                xs, ys, canvas.runtime_state.atom_graphics_state.atom_items.get(atom_id)
            )
            extend_bounds_with_item_rect(
                xs, ys, canvas.runtime_state.atom_graphics_state.atom_dots.get(atom_id)
            )
    if not xs:
        return canvas.model.bounds()
    return min(xs), min(ys), max(xs), max(ys)


__all__ = ["bounds_for_atoms_for", "extend_bounds_with_item_rect"]
