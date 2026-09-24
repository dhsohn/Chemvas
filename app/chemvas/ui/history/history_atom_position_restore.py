from __future__ import annotations

from PyQt6.QtCore import QPointF

from chemvas.features.selection import translate_projected_point_3d
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.molecule.atom_coords_access import set_atom_coords_3d_for_id
from chemvas.ui.selection.selection_rotation_access import (
    update_ring_fills_for_atoms_for,
)


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
    label_service = canvas.services.atom_label_service
    for atom_id, (x, y) in positions.items():
        atom = canvas.model.atom_for_id(atom_id)
        if atom is None:
            continue
        dx, dy = x - atom.x, y - atom.y
        atom.x = x
        atom.y = y
        atom_ids.add(atom_id)
        if coords_3d is not None and atom_id in coords_3d:
            set_atom_coords_3d_for_id(canvas, atom_id, coords_3d[atom_id])
        elif atom_id in canvas.runtime_state.atom_coords_3d_state.atom_coords_3d:
            # Screen coordinates are not world coordinates at nonzero depth.
            # Preserve both depth and any pre-existing stale projection residual,
            # exactly as the ordinary move path does.
            set_atom_coords_3d_for_id(
                canvas,
                atom_id,
                translate_projected_point_3d(
                    canvas.runtime_state.atom_coords_3d_state.atom_coords_3d[atom_id],
                    dx,
                    dy,
                    bond_length_px=canvas.renderer.style.bond_length_px,
                    center_3d=canvas.runtime_state.rotation_state.projection_center_3d,
                ),
            )
        label = canvas.runtime_state.atom_graphics_state.atom_items.get(atom_id)
        if label is not None:
            label_service.position_label(label, x, y)
        dot = canvas.runtime_state.atom_graphics_state.atom_dots.get(atom_id)
        if dot is not None:
            dot.setPos(x, y)
        marks = mark_registry_for(canvas).get_for_atom(atom_id)
        for mark in list(marks or ()):
            data = mark.data(1) or {}
            dx = data.get("dx")
            dy = data.get("dy")
            if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
                canvas.services.scene_decoration_build_service.set_mark_center(
                    mark, QPointF(x + dx, y + dy)
                )
            else:
                canvas.services.scene_decoration_build_service.set_mark_center(
                    mark, QPointF(x, y)
                )
    if coords_3d is not None:
        for atom_id, coord in coords_3d.items():
            atom = canvas.model.atom_for_id(atom_id)
            if atom is None:
                continue
            set_atom_coords_3d_for_id(canvas, atom_id, coord)
            atom_ids.add(atom_id)
    if atom_ids:
        move_service = canvas.services.move_controller
        update_geometries = getattr(
            move_service,
            "update_bond_geometries_for_atoms",
            None,
        )
        if callable(update_geometries):
            update_geometries(atom_ids, rebuild_stale_bond_topology=True)
        else:
            move_service.redraw_bonds_for_atoms(atom_ids)
        update_ring_fills_for_atoms_for(canvas, atom_ids)
    canvas.services.hit_testing_service.mark_spatial_index_dirty()
    if update_selection:
        canvas.services.selection.update_selection_outline()


__all__ = ["set_atom_positions_for_history"]
