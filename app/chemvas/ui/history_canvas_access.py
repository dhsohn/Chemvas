from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from chemvas.core.history import (
    capture_history_transaction_for_command as _capture_history_transaction_for_command,
)
from chemvas.core.history import (
    release_history_transaction_for_command as _release_history_transaction_for_command,
)
from chemvas.core.history import (
    restore_history_transaction_for_command as _restore_history_transaction_for_command,
)
from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.atom_coords_access import atom_coords_3d_for_id
from chemvas.ui.bond_length_graphics_refresh import refresh_bond_length_graphics_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_service_ports import (
    history_atom_mutation_service_for,
    history_bond_mutation_service_for,
    history_hit_testing_service_for,
)
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.history_atom_position_restore import set_atom_positions_for_history
from chemvas.ui.move_access import move_atoms_for
from chemvas.ui.renderer_style_access import set_bond_length_for
from chemvas.ui.scene_item_access import restore_mark_from_state
from chemvas.ui.transactions.document import DocumentSavepoint, MoveGestureScope


def _add_move_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    original_error.add_note(
        "Move rollback also encountered "
        f"{type(rollback_error).__name__}: {rollback_error}"
    )


def capture_history_transaction_for_history(
    canvas,
    *,
    history_service=None,
    guard_scene_rect: bool = True,
    move_scope: MoveGestureScope | None = None,
) -> DocumentSavepoint:
    return DocumentSavepoint.capture(
        canvas,
        history_service=history_service,
        guard_scene_rect=guard_scene_rect,
        move_scope=move_scope,
    )


def restore_history_transaction_for_history(
    canvas,
    snapshot: DocumentSavepoint,
) -> RestoreOutcome:
    del canvas
    return snapshot.restore()


def release_history_transaction_for_history(
    canvas,
    snapshot: DocumentSavepoint,
) -> None:
    del canvas
    snapshot.release()


def verify_history_transaction_for_history(
    canvas,
    snapshot: DocumentSavepoint,
) -> None:
    del canvas
    errors = tuple(snapshot.verify())
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup(
            "document savepoint verification failed",
            list(errors),
        )


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
    transaction = _capture_history_transaction_for_command(canvas)
    before_positions: dict[int, tuple[float, float]] = {}
    before_coords_3d: dict[int, tuple[float, float, float]] = {}
    try:
        # Position and 3D-coordinate properties are live preflight ports. They
        # belong to the same exact transaction as the move so a fail-before
        # descriptor still publishes authoritative rollback to history stacks.
        for atom_id in atom_ids:
            atom = atom_for_id(canvas, atom_id)
            if atom is None:
                continue
            before_positions[atom_id] = (atom.x, atom.y)
            coords_3d = atom_coords_3d_for_id(canvas, atom_id)
            if coords_3d is not None:
                before_coords_3d[atom_id] = coords_3d
        move_atoms_for(
            canvas,
            atom_ids,
            dx,
            dy,
            bond_ids=bond_ids,
            redraw_bond_ids=redraw_bond_ids,
            update_selection=update_selection,
        )
        _release_history_transaction_for_command(canvas, transaction)
    except Exception as original_error:
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
        except Exception as rollback_error:
            _add_move_rollback_note(original_error, rollback_error)
        # The canonical setter is itself a multi-atom operation and can stop
        # after restoring only an early atom. The exact transaction snapshot
        # restores all model/3D/graphics/selection state independently of that
        # partial compensation while retaining the primary exception.
        restore_result = _restore_history_transaction_for_command(
            canvas,
            transaction,
            original_error,
        )
        for exact_restore_error in restore_result.errors:
            _add_move_rollback_note(original_error, exact_restore_error)
        raise


def restore_projection_state_for_history(
    canvas,
    projection_center_3d: tuple[float, float, float] | None,
    projection_anchor_2d: tuple[float, float] | None,
) -> None:
    rotation_state = rotation_state_for(canvas)
    rotation_state.projection_center_3d = projection_center_3d
    rotation_state.projection_anchor_2d = projection_anchor_2d


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
    history_bond_mutation_service_for(canvas).restore_bond_from_state(
        bond_id, bond_state
    )


def remove_bond_for_history(canvas, bond_id: int) -> None:
    history_bond_mutation_service_for(canvas).remove_bond_by_id(bond_id)


def trim_bonds_for_history(canvas, length: int) -> None:
    history_bond_mutation_service_for(canvas).trim_bonds_to_length(length)


__all__ = [
    "MoveGestureScope",
    "apply_atom_color_for_history",
    "capture_history_transaction_for_history",
    "move_atoms_for_history",
    "release_history_transaction_for_history",
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
    "verify_history_transaction_for_history",
]
