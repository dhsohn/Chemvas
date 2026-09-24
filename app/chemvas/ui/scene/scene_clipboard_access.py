from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF

from chemvas.domain.document import CLIPBOARD_SELECTION_VERSION, Bond
from chemvas.domain.document.marks import mark_to_state
from chemvas.ui.canvas.canvas_document_state import snapshot_ring_fills
from chemvas.ui.export.export_render_service import (
    render_scene_to_pdf_bytes,
    render_scene_to_svg_bytes,
)
from chemvas.ui.molecule.atom_coords_access import (
    stored_atom_coords_3d_matches_projection_for,
)
from chemvas.ui.scene.scene_clipboard_logic import build_selection_clipboard_payload

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from PyQt6.QtWidgets import QGraphicsItem


def build_selection_clipboard_payload_for_canvas(
    canvas,
    *,
    selected_items: Sequence[QGraphicsItem],
    explicit_atom_ids: set[int],
    selected_bond_ids: set[int],
    bonds: Sequence[Bond | None],
    atom_state_getter: Callable[[int], dict],
    bond_state_getter: Callable[[object], dict],
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    version: int,
) -> dict | None:
    return build_selection_clipboard_payload(
        selected_items=selected_items,
        explicit_atom_ids=explicit_atom_ids,
        selected_bond_ids=selected_bond_ids,
        bonds=bonds,
        ring_states=[
            {"kind": "ring", **state} for state in snapshot_ring_fills(canvas)
        ],
        mark_states=[
            (
                record_id,
                mark_to_state(canvas.runtime_state.mark_state.records[record_id]),
            )
            for record_id in canvas.runtime_state.mark_state.order
        ],
        atom_state_getter=atom_state_getter,
        bond_state_getter=bond_state_getter,
        scene_item_state_getter=scene_item_state_getter,
        perspective_state_getter=(
            lambda atom_ids: (
                _selection_perspective_state_for_canvas(canvas, atom_ids)
                if version == CLIPBOARD_SELECTION_VERSION
                else None
            )
        ),
        version=version,
        groups=[
            (group.atom_ids, group.item_ids)
            for group in canvas.runtime_state.group_state.groups.values()
        ],
    )


def _selection_perspective_state_for_canvas(canvas, atom_ids: set[int]) -> dict | None:
    model = canvas.model
    stored_coords = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
    coords_3d = [
        {"atom_id": atom_id, "coords": stored_coords[atom_id]}
        for atom_id in sorted(atom_ids)
        if atom_id in model.atoms
        and atom_id in stored_coords
        and stored_atom_coords_3d_matches_projection_for(
            canvas, atom_id, stored_coords[atom_id]
        )
    ]
    if not coords_3d:
        return None
    rotation = canvas.runtime_state.rotation_state
    return {
        "atom_coords_3d": coords_3d,
        "projection_center_3d": rotation.projection_center_3d,
        "projection_anchor_2d": rotation.projection_anchor_2d,
    }


def render_canvas_scene_region(canvas, painter, *, source: QRectF) -> None:
    target = QRectF(0, 0, source.width(), source.height())
    canvas.scene().render(painter, target, source)


def render_canvas_selection_vector_bytes(
    canvas,
    *,
    source: QRectF,
    items: Sequence[QGraphicsItem],
    title: str | None = None,
) -> tuple[bytes, bytes]:
    scene = canvas.scene()
    return (
        render_scene_to_svg_bytes(scene, source=source, items=items, title=title),
        render_scene_to_pdf_bytes(scene, source=source, items=items, title=title),
    )


__all__ = [
    "build_selection_clipboard_payload_for_canvas",
    "render_canvas_scene_region",
    "render_canvas_selection_vector_bytes",
]
