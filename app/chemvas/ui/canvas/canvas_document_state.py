from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt

from chemvas.domain.document import (
    VALID_MARK_KINDS,
    arrow_to_state,
    calculation_plan_save_warning,
    is_hex_color,
    model_bond_pairs,
    ring_atom_ids_form_cycle,
    serialize_model_state_with_warnings,
    serialize_settings,
    shape_to_state,
    ts_bracket_to_state,
)
from chemvas.domain.document.images import image_to_state
from chemvas.domain.document.marks import mark_to_state
from chemvas.domain.document.notes import note_to_document_state
from chemvas.domain.document.orbitals import orbital_to_state
from chemvas.domain.document.perspective import saved_perspective
from chemvas.domain.document.ring_fills import ring_fill_to_state
from chemvas.features.groups import restored_groups, snapshot_groups
from chemvas.ui.annotations.state import (
    note_state_dict_for,
)
from chemvas.ui.canvas.canvas_calculation_plan_state import calculation_plan_for
from chemvas.ui.canvas.canvas_group_state import (
    clear_groups_for,
    register_group_for,
)
from chemvas.ui.canvas.sheet_setup_access import (
    sheet_orientation_for,
    sheet_size_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView


def snapshot_canvas_document_state(canvas) -> dict:
    state, _warnings = snapshot_canvas_document_state_with_warnings(canvas)
    return state


def snapshot_canvas_document_state_with_warnings(canvas) -> tuple[dict, list[str]]:
    tool_settings = canvas.runtime_state.tool_settings_state
    text_style = canvas.runtime_state.text_style_state
    model_state, warnings = serialize_model_state_with_warnings(
        canvas.model,
        explicit_label_atom_ids=canvas.runtime_state.atom_graphics_state.atom_items.keys(),
    )
    state = {
        "model": model_state,
        "ring_fills": snapshot_ring_fills(canvas),
        "notes": canvas.runtime_state.note_state.snapshot(note_to_document_state),
        "marks": _snapshot_marks(canvas),
        "arrows": canvas.runtime_state.arrow_state.snapshot(arrow_to_state),
        "ts_brackets": canvas.runtime_state.ts_bracket_state.snapshot(
            ts_bracket_to_state
        ),
        "shapes": canvas.runtime_state.shape_state.snapshot(shape_to_state),
        "orbitals": _snapshot_orbitals(canvas),
        "settings": serialize_settings(
            bond_length_px=canvas.renderer.style.bond_length_px,
            arrow_line_width=tool_settings.arrow_line_width,
            arrow_head_scale=tool_settings.arrow_head_scale,
            orbital_phase_enabled=tool_settings.orbital_phase_enabled,
            text_font_family=text_style.text_font_family,
            text_font_size=text_style.text_font_size,
            text_font_weight=int(text_style.text_font_weight),
            text_italic=text_style.text_italic,
            text_color=text_style.text_color.name(),
            text_alignment=_alignment_name(text_style.text_alignment),
            text_line_spacing=text_style.text_line_spacing,
            note_box_enabled=text_style.note_box_enabled,
            note_box_color=text_style.note_box_color.name(),
            note_box_alpha=text_style.note_box_alpha,
            note_border_enabled=text_style.note_border_enabled,
            note_border_color=text_style.note_border_color.name(),
            note_border_width=text_style.note_border_width,
            note_padding=text_style.note_padding,
            sheet_size=sheet_size_for(canvas),
            sheet_orientation=sheet_orientation_for(canvas),
            sheet_custom_size_mm=canvas.runtime_state.sheet_setup_state.custom_size_mm,
        ),
        "last_smiles_input": None,
    }
    _add_projection_state(canvas, state)
    if canvas.runtime_state.image_state.order:
        state["images"] = canvas.runtime_state.image_state.snapshot(image_to_state)
    calculation_plan = calculation_plan_for(canvas)
    plan_warning = calculation_plan_save_warning(canvas.model, calculation_plan)
    if plan_warning is not None:
        warnings.append(plan_warning)
    elif calculation_plan is not None:
        state["calculation_plan"] = calculation_plan
    groups = _snapshot_groups(canvas)
    if groups:
        state["groups"] = groups
    return state, warnings


PRESERVED_CALCULATION_PLAN_SAVE_ERROR = (
    "This document contains a calculation plan from an earlier version of "
    "Chemvas. Chemvas keeps that plan unchanged but can no longer edit it, and "
    "the drawing no longer matches the atoms and bonds it refers to, so saving "
    "now would lose it. Undo the structure edits that changed those atoms or "
    "bonds, then try again."
)


def require_preserved_calculation_plan_for(canvas: CanvasView) -> None:
    """Refuse to write a document that would drop its existing calculation plan.

    The document snapshot leaves out a plan whose references no longer match
    the drawing. A file written from that snapshot would silently lose data
    Chemvas can no longer recreate, so callers check here before writing.
    Raises ``ValueError`` with a message for the user.
    """
    if (
        calculation_plan_save_warning(canvas.model, calculation_plan_for(canvas))
        is not None
    ):
        raise ValueError(PRESERVED_CALCULATION_PLAN_SAVE_ERROR)


def _add_projection_state(canvas, state: dict) -> None:
    rotation = canvas.runtime_state.rotation_state
    perspective = saved_perspective(
        canvas.runtime_state.atom_coords_3d_state.atom_coords_3d,
        {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
        rotation.projection_center_3d,
        rotation.projection_anchor_2d,
        bond_length_px=canvas.renderer.style.bond_length_px,
    )
    if perspective is not None:
        state["perspective"] = perspective


def _alignment_name(alignment) -> str:
    if alignment == Qt.AlignmentFlag.AlignHCenter:
        return "center"
    if alignment == Qt.AlignmentFlag.AlignRight:
        return "right"
    if alignment == Qt.AlignmentFlag.AlignJustify:
        return "justify"
    return "left"


GROUP_COLLECTION_STATES = {
    "images": "image_items",
    "notes": "note_items",
    "marks": "mark_items",
    "arrows": "arrow_items",
    "ts_brackets": "ts_bracket_items",
    "shapes": "shape_items",
    "orbitals": "orbital_items",
}


def document_item_lists_for(canvas) -> dict[str, list]:
    # Group indices follow the saved arrays. Record-owned annotations keep
    # document order even when a projection is detached or missing; filtering
    # those views would silently shift references onto another annotation.
    return {
        "images": canvas.runtime_state.scene_items("image_items"),
        "notes": canvas.runtime_state.scene_items("note_items"),
        "marks": canvas.runtime_state.scene_items("mark_items"),
        "arrows": canvas.runtime_state.scene_items("arrow_items"),
        "ts_brackets": canvas.runtime_state.scene_items("ts_bracket_items"),
        "shapes": canvas.runtime_state.scene_items("shape_items"),
        "orbitals": canvas.runtime_state.scene_items("orbital_items"),
    }


def _snapshot_groups(canvas) -> list[dict]:
    return snapshot_groups(
        canvas.runtime_state.group_state.groups,
        canvas.model.atoms,
        {
            record_id: (kind_key, index)
            for kind_key, name in GROUP_COLLECTION_STATES.items()
            for index, record_id in enumerate(
                canvas.runtime_state.document_collection(name).order
            )
        },
    )


def restore_document_groups(canvas, state: dict) -> None:
    clear_groups_for(canvas)
    records = state.get("groups") or []
    if not records:
        return
    for group in restored_groups(
        records,
        canvas.model.atoms,
        {
            key: canvas.runtime_state.document_collection(name).order
            for key, name in GROUP_COLLECTION_STATES.items()
        },
    ):
        register_group_for(canvas, group.atom_ids, group.item_ids)


def snapshot_ring_fills(canvas) -> list[dict]:
    # Ring fills are healed on the way out: points are rewritten from the live
    # atom coordinates (the validator requires an exact match), and rings whose
    # atoms no longer form a bonded cycle are dropped instead of making the
    # whole save fail validation.
    model = canvas.model
    atom_ids = set(model.atoms)
    bond_pairs = model_bond_pairs(model)
    ring_fills: list[dict] = []
    document = canvas.runtime_state.ring_state
    for record_id in document.order:
        ring_state = ring_fill_to_state(document.records[record_id], model.atoms)
        ring_atom_ids = ring_state["atom_ids"]
        if not isinstance(ring_atom_ids, (list, tuple)):
            continue
        ring_atom_ids = [
            atom_id for atom_id in ring_atom_ids if isinstance(atom_id, int)
        ]
        if len(ring_atom_ids) != len(document.records[record_id].atom_ids):
            continue
        if not ring_atom_ids_form_cycle(ring_atom_ids, atom_ids, bond_pairs):
            continue
        alpha = ring_state["alpha"]
        color = ring_state["color"]
        ring_fills.append(
            {
                "points": [
                    (model.atoms[atom_id].x, model.atoms[atom_id].y)
                    for atom_id in ring_atom_ids
                ],
                "atom_ids": list(ring_atom_ids),
                "color": color if color is None or is_hex_color(color) else None,
                "alpha": min(max(float(alpha), 0.0), 1.0)
                if isinstance(alpha, (int, float))
                else 1.0,
            }
        )
    return ring_fills


def snapshot_note_document_state(canvas, item) -> dict:
    note_state = note_state_dict_for(canvas, item)
    snapshot = {
        "text": note_state["text"],
        "x": note_state["x"],
        "y": note_state["y"],
    }
    if "rotation" in note_state:
        snapshot["rotation"] = note_state["rotation"]
    html = note_state.get("html")
    if isinstance(html, str):
        snapshot["html"] = html
    return snapshot


def _snapshot_marks(canvas) -> list[dict]:
    # Marks are healed in place (never dropped) so their indices stay aligned
    # with the group [kind, index] references built from the same item list. A
    # mark whose atom no longer exists degrades to a free-floating mark instead
    # of making the whole save fail validation.
    live_atom_ids = set(canvas.model.atoms)
    marks: list[dict] = []
    for mark_state in canvas.runtime_state.mark_state.snapshot(mark_to_state):
        atom_id = mark_state["atom_id"]
        bound = isinstance(atom_id, int) and atom_id in live_atom_ids
        dx = mark_state["dx"] if bound else None
        dy = mark_state["dy"] if bound else None
        if (dx is None) != (dy is None):
            dx = dy = None
        mark_kind = mark_state["mark_kind"]
        marks.append(
            {
                "kind": mark_kind
                if isinstance(mark_kind, str) and mark_kind in VALID_MARK_KINDS
                else "plus",
                "text": mark_state["text"],
                "atom_id": atom_id if bound else None,
                "dx": dx,
                "dy": dy,
                "x": mark_state["x"],
                "y": mark_state["y"],
                **({"color": mark_state["color"]} if "color" in mark_state else {}),
            }
        )
    return marks


def _snapshot_orbitals(canvas) -> list[dict]:
    orbitals: list[dict] = []
    for orbital_state in canvas.runtime_state.orbital_state.snapshot(orbital_to_state):
        orbitals.append(
            {
                "kind": orbital_state["orbital_kind"],
                "center": orbital_state["center"],
                "scale": orbital_state["scale"],
                "rotation": orbital_state["rotation"],
            }
        )
    return orbitals
