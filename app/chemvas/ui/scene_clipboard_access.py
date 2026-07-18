from __future__ import annotations

import math
from collections.abc import Callable, Collection, Mapping, Sequence

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.domain.document import CLIPBOARD_SELECTION_PERSPECTIVE_VERSION, Bond
from chemvas.features.export import (
    render_scene_to_pdf_bytes,
    render_scene_to_svg_bytes,
)
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.bond_graphics_access import project_point_3d_for
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_clipboard_logic import build_selection_clipboard_payload
from chemvas.ui.scene_clipboard_state import scene_clipboard_state_for
from chemvas.ui.scene_clipboard_transaction_logic import visible_items_to_hide_for_copy
from chemvas.ui.scene_item_access import canvas_scene_for


def clipboard_paste_source_json_for(canvas) -> str | None:
    return scene_clipboard_state_for(canvas).paste_source_json


def set_clipboard_paste_source_json_for(canvas, value: str | None) -> None:
    scene_clipboard_state_for(canvas).paste_source_json = value


def clipboard_paste_count_for(canvas) -> int:
    return scene_clipboard_state_for(canvas).paste_count


def set_clipboard_paste_count_for(canvas, value: int) -> None:
    scene_clipboard_state_for(canvas).paste_count = int(value)


def build_selection_clipboard_payload_for_canvas(
    canvas,
    *,
    selected_items: Sequence[QGraphicsItem],
    explicit_atom_ids: set[int],
    selected_bond_ids: set[int],
    bonds: Sequence[Bond | None],
    ring_items: Sequence[QGraphicsItem],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
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
        ring_items=ring_items,
        marks_by_atom=marks_by_atom,
        scene=canvas_scene_for(canvas),
        atom_state_getter=atom_state_getter,
        bond_state_getter=bond_state_getter,
        scene_item_state_getter=scene_item_state_getter,
        perspective_state_getter=(
            lambda atom_ids: (
                _selection_perspective_state_for_canvas(canvas, atom_ids)
                if version == CLIPBOARD_SELECTION_PERSPECTIVE_VERSION
                else None
            )
        ),
        version=version,
    )


def _selection_perspective_state_for_canvas(canvas, atom_ids: set[int]) -> dict | None:
    model = model_for(canvas)
    stored_coords = atom_coords_3d_for(canvas)
    coords_3d = [
        {"atom_id": atom_id, "coords": stored_coords[atom_id]}
        for atom_id in sorted(atom_ids)
        if atom_id in model.atoms
        and atom_id in stored_coords
        and _stored_atom_coords_3d_matches_projection(
            canvas, atom_id, stored_coords[atom_id]
        )
    ]
    if not coords_3d:
        return None
    rotation = rotation_state_for(canvas)
    return {
        "atom_coords_3d": coords_3d,
        "projection_center_3d": rotation.projection_center_3d,
        "projection_anchor_2d": rotation.projection_anchor_2d,
    }


def _stored_atom_coords_3d_matches_projection(
    canvas, atom_id: int, coords: tuple[float, float, float]
) -> bool:
    atom = model_for(canvas).atoms.get(atom_id)
    if atom is None:
        return False
    proj_x, proj_y = project_point_3d_for(canvas, coords)
    tolerance = max(1.0, bond_length_px_for(canvas) * 0.15)
    return math.hypot(proj_x - atom.x, proj_y - atom.y) <= tolerance


def visible_canvas_items_to_hide_for_copy(
    canvas,
    source: QRectF,
    *,
    selected_items: Collection[QGraphicsItem],
) -> list[QGraphicsItem]:
    return visible_items_to_hide_for_copy(
        canvas_scene_for(canvas).items(source),
        selected_items=selected_items,
    )


def render_canvas_scene_region(canvas, painter, *, source: QRectF) -> None:
    target = QRectF(0, 0, source.width(), source.height())
    canvas_scene_for(canvas).render(painter, target, source)


def render_canvas_selection_vector_bytes(
    canvas,
    *,
    source: QRectF,
    items: Sequence[QGraphicsItem],
    title: str | None = None,
) -> tuple[bytes, bytes]:
    scene = canvas_scene_for(canvas)
    return (
        render_scene_to_svg_bytes(scene, source=source, items=items, title=title),
        render_scene_to_pdf_bytes(scene, source=source, items=items, title=title),
    )


__all__ = [
    "build_selection_clipboard_payload_for_canvas",
    "clipboard_paste_count_for",
    "clipboard_paste_source_json_for",
    "render_canvas_scene_region",
    "render_canvas_selection_vector_bytes",
    "set_clipboard_paste_count_for",
    "set_clipboard_paste_source_json_for",
    "visible_canvas_items_to_hide_for_copy",
]
