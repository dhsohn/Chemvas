from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from ui.atom_coords_access import (
    atom_coords_3d_for,
    atom_coords_3d_for_id,
    set_atom_coords_3d_for_id,
)
from ui.atom_label_access import atom_label_service
from ui.bond_length_graphics_refresh import refresh_bond_length_graphics_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import atom_for_id
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_service_ports import (
    history_atom_mutation_service_for,
    history_bond_mutation_service_for,
    history_hit_testing_service_for,
)
from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.mark_item_access import set_mark_center_for
from ui.move_access import move_atoms_for, move_service_from_canvas
from ui.renderer_style_access import set_bond_length_for
from ui.scene_item_access import restore_mark_from_state
from ui.selection_rotation_access import update_ring_fills_for_atoms_for
from ui.selection_service_access import refresh_selection_outline_for


def capture_history_transaction_for_history(
    canvas,
    *,
    history_service=None,
):
    # Lazy import keeps the core history port free of an eager dependency on
    # the scene/history command graph (and therefore avoids an import cycle).
    from ui.canvas_delete_transaction import CanvasDeleteTransactionSnapshot

    return CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history_service,
    )


def restore_history_transaction_for_history(canvas, snapshot) -> None:
    del canvas
    errors = snapshot.restore()
    if errors:
        raise BaseExceptionGroup("History transaction rollback failed", errors)


def move_atoms_for_history(
    canvas,
    atom_ids: set[int],
    dx: float,
    dy: float,
    *,
    bond_ids: set[int] | None = None,
    redraw_bond_ids: set[int] | None = None,
    update_selection: bool = True,
) -> None:
    before_positions: dict[int, tuple[float, float]] = {}
    before_coords_3d: dict[int, tuple[float, float, float]] = {}
    for atom_id in atom_ids:
        atom = atom_for_id(canvas, atom_id)
        if atom is None:
            continue
        before_positions[atom_id] = (atom.x, atom.y)
        coords_3d = atom_coords_3d_for_id(canvas, atom_id)
        if coords_3d is not None:
            before_coords_3d[atom_id] = coords_3d
    try:
        move_atoms_for(
            canvas,
            atom_ids,
            dx,
            dy,
            bond_ids=bond_ids,
            redraw_bond_ids=redraw_bond_ids,
            update_selection=update_selection,
        )
    except BaseException as original_error:
        # The move controller mutates atoms one at a time before redrawing
        # dependent graphics. Restore absolute positions instead of applying
        # the inverse delta to every requested atom: some atoms may not have
        # been reached when the original call failed.
        try:
            set_atom_positions_for_history(
                canvas,
                before_positions,
                update_selection=update_selection,
                coords_3d=before_coords_3d or None,
            )
        except BaseException as rollback_error:
            add_note = getattr(original_error, "add_note", None)
            if callable(add_note):
                add_note(
                    "Move rollback also encountered "
                    f"{type(rollback_error).__name__}: {rollback_error}"
                )
        raise


def restore_projection_state_for_history(
    canvas,
    projection_center_3d: tuple[float, float, float] | None,
    projection_anchor_2d: tuple[float, float] | None,
) -> None:
    rotation_state = rotation_state_for(canvas)
    rotation_state.projection_center_3d = projection_center_3d
    rotation_state.projection_anchor_2d = projection_anchor_2d


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
        update_geometries = getattr(move_service, "update_bond_geometries_for_atoms", None)
        if callable(update_geometries):
            update_geometries(atom_ids)
        else:
            move_service.redraw_bonds_for_atoms(atom_ids)
        update_ring_fills_for_atoms_for(canvas, atom_ids)
    history_hit_testing_service_for(canvas).mark_spatial_index_dirty()
    if update_selection:
        refresh_selection_outline_for(canvas)


def set_ring_polygons_for_history(
    canvas,
    ring_items: list,
    polygons: list[list[tuple[float, float]]],
) -> None:
    for ring_item, points in zip(ring_items, polygons, strict=False):
        if ring_item is None:
            continue
        polygon = QPolygonF([QPointF(x, y) for x, y in points])
        ring_item.setPolygon(polygon)


def set_last_smiles_input_for_history(canvas, value: str | None) -> None:
    set_last_smiles_input_for(canvas, value)


def restore_bond_length_for_history(canvas, length_px: float) -> None:
    set_bond_length_for(canvas, length_px)
    refresh_bond_length_graphics_for(canvas)
    history_hit_testing_service_for(canvas).mark_spatial_index_dirty()


def remove_atom_for_history(canvas, atom_id: int, *, remove_marks: bool = True) -> None:
    history_atom_mutation_service_for(canvas).remove_atom_only(
        atom_id,
        remove_marks=remove_marks,
    )


def restore_atom_from_state_for_history(canvas, atom_id: int, state: dict) -> None:
    history_atom_mutation_service_for(canvas).restore_atom_from_state(atom_id, state)


def apply_atom_color_for_history(canvas, atom_id: int, color) -> None:
    history_atom_mutation_service_for(canvas).apply_atom_color(atom_id, color)


def restore_mark_from_state_for_history(canvas, mark_state: dict):
    return restore_mark_from_state(canvas, mark_state)


def restore_bond_from_state_for_history(canvas, bond_id: int, bond_state: dict) -> None:
    history_bond_mutation_service_for(canvas).restore_bond_from_state(bond_id, bond_state)


def remove_bond_for_history(canvas, bond_id: int) -> None:
    history_bond_mutation_service_for(canvas).remove_bond_by_id(bond_id)


def trim_bonds_for_history(canvas, length: int) -> None:
    history_bond_mutation_service_for(canvas).trim_bonds_to_length(length)


__all__ = [
    "apply_atom_color_for_history",
    "capture_history_transaction_for_history",
    "move_atoms_for_history",
    "remove_atom_for_history",
    "remove_bond_for_history",
    "restore_atom_from_state_for_history",
    "restore_bond_from_state_for_history",
    "restore_bond_length_for_history",
    "restore_history_transaction_for_history",
    "restore_mark_from_state_for_history",
    "restore_projection_state_for_history",
    "set_atom_positions_for_history",
    "set_last_smiles_input_for_history",
    "set_ring_polygons_for_history",
    "trim_bonds_for_history",
]
