from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from chemvas.ui.bond_length_graphics_refresh import refresh_bond_length_graphics_for
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_service_ports import (
    history_hit_testing_service_for,
    structure_mutation_atom_service,
    structure_mutation_bond_service,
)
from chemvas.ui.history_atom_position_restore import set_atom_positions_for_history
from chemvas.ui.renderer_style_access import set_bond_length_for
from chemvas.ui.transactions.document import DocumentSavepoint, MoveGestureScope

if TYPE_CHECKING:
    from chemvas.domain.transactions import RestoreOutcome


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


def restore_bond_length_for_history(canvas, length_px: float) -> None:
    set_bond_length_for(canvas, length_px)
    refresh_bond_length_graphics_for(canvas)
    history_hit_testing_service_for(canvas).mark_spatial_index_dirty()


def remove_atom_for_history(canvas, atom_id: int, *, remove_marks: bool = True) -> None:
    structure_mutation_atom_service(canvas).remove_atom_only(
        atom_id,
        remove_marks=remove_marks,
    )


def apply_atom_color_for_history(canvas, atom_id: int, color) -> None:
    structure_mutation_atom_service(canvas).apply_atom_color(atom_id, color)


def trim_bonds_for_history(canvas, length: int) -> None:
    structure_mutation_bond_service(canvas).trim_bonds_to_length(length)


__all__ = [
    "MoveGestureScope",
    "apply_atom_color_for_history",
    "capture_history_transaction_for_history",
    "release_history_transaction_for_history",
    "remove_atom_for_history",
    "restore_bond_length_for_history",
    "restore_history_transaction_for_history",
    "restore_projection_state_for_history",
    "set_atom_positions_for_history",
    "set_ring_polygons_for_history",
    "trim_bonds_for_history",
]
