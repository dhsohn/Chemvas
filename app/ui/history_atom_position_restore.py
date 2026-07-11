from __future__ import annotations

from PyQt6.QtCore import QPointF

from ui.atom_coords_access import (
    atom_coords_3d_for,
    set_atom_coords_3d_for_id,
)
from ui.atom_label_access import atom_label_service
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import atom_for_id
from ui.canvas_service_ports import history_hit_testing_service_for
from ui.mark_item_access import set_mark_center_for
from ui.move_access import move_service_from_canvas
from ui.selection_rotation_access import update_ring_fills_for_atoms_for
from ui.selection_service_access import refresh_selection_outline_for


def set_atom_positions_for_history(
    canvas,
    positions: dict[int, tuple[float, float]],
    *,
    update_selection: bool = True,
    coords_3d: dict[int, tuple[float, float, float]] | None = None,
) -> None:
    if not positions and not coords_3d:
        return
    atom_ids = set()
    label_service = atom_label_service(canvas)
    for atom_id, (x, y) in positions.items():
        atom = atom_for_id(canvas, atom_id)
        if atom is None:
            continue
        atom.x = x
        atom.y = y
        atom_ids.add(atom_id)
        if coords_3d is not None and atom_id in coords_3d:
            set_atom_coords_3d_for_id(canvas, atom_id, coords_3d[atom_id])
        elif atom_id in atom_coords_3d_for(canvas):
            _, _, z = atom_coords_3d_for(canvas)[atom_id]
            set_atom_coords_3d_for_id(canvas, atom_id, (x, y, z))
        label = atom_items_for(canvas).get(atom_id)
        if label is not None:
            label_service.position_label(label, x, y)
        dot = atom_dots_for(canvas).get(atom_id)
        if dot is not None:
            dot.setPos(x, y)
        marks = mark_registry_for(canvas).get_for_atom(atom_id)
        for mark in list(marks or ()):
            data = mark.data(1) or {}
            dx = data.get("dx")
            dy = data.get("dy")
            if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
                set_mark_center_for(canvas, mark, QPointF(x + dx, y + dy))
            else:
                set_mark_center_for(canvas, mark, QPointF(x, y))
    if coords_3d is not None:
        for atom_id, coord in coords_3d.items():
            atom = atom_for_id(canvas, atom_id)
            if atom is None:
                continue
            set_atom_coords_3d_for_id(canvas, atom_id, coord)
            atom_ids.add(atom_id)
    if atom_ids:
        move_service = move_service_from_canvas(canvas)
        update_geometries = getattr(
            move_service,
            "update_bond_geometries_for_atoms",
            None,
        )
        if callable(update_geometries):
            update_geometries(atom_ids)
        else:
            move_service.redraw_bonds_for_atoms(atom_ids)
        update_ring_fills_for_atoms_for(canvas, atom_ids)
    history_hit_testing_service_for(canvas).mark_spatial_index_dirty()
    if update_selection:
        refresh_selection_outline_for(canvas)


__all__ = ["set_atom_positions_for_history"]
