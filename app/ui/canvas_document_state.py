from __future__ import annotations

import math

from core.document_state import serialize_model_state, serialize_settings
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from ui.bond_graphics_access import project_point_3d_for
from ui.canvas_atom_graphics_state import atom_items_for
from ui.canvas_model_access import model_for
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    shape_items_for,
    ts_bracket_items_for,
)
from ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from ui.canvas_text_style_state import (
    CanvasTextStyleState,
    set_text_style_for,
    text_style_state_for,
)
from ui.canvas_tool_settings_state import set_tool_setting_for, tool_settings_state_for
from ui.renderer_style_access import bond_length_px_for, set_bond_length_for
from ui.scene_item_access import (
    attached_canvas_scene_items,
    restore_arrow_from_state,
    restore_mark_from_state,
    restore_note_from_state,
    restore_orbital_from_state,
    restore_ring_from_state,
    restore_shape_from_state,
    restore_ts_bracket_from_state,
)
from ui.scene_item_state import (
    arrow_state_dict_for,
    mark_state_dict_for,
    note_state_dict_for,
    orbital_state_dict_for,
    ring_state_dict_for,
    shape_state_dict_for,
    ts_bracket_state_dict_for,
)
from ui.sheet_setup_access import (
    set_sheet_setup_for,
    sheet_orientation_for,
    sheet_size_for,
)


def snapshot_canvas_document_state(canvas) -> dict:
    tool_settings = tool_settings_state_for(canvas)
    text_style = text_style_state_for(canvas)
    state = {
        "model": serialize_model_state(
            model_for(canvas),
            explicit_label_atom_ids=atom_items_for(canvas).keys(),
        ),
        "ring_fills": _snapshot_ring_fills(canvas),
        "notes": _snapshot_notes(canvas),
        "marks": _snapshot_marks(canvas),
        "arrows": _snapshot_arrows(canvas),
        "ts_brackets": _snapshot_ts_brackets(canvas),
        "shapes": _snapshot_shapes(canvas),
        "orbitals": _snapshot_orbitals(canvas),
        "settings": serialize_settings(
            bond_length_px=bond_length_px_for(canvas),
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
        ),
        "last_smiles_input": last_smiles_input_for(canvas),
    }
    _add_projection_state(canvas, state)
    return state


def _add_projection_state(canvas, state: dict) -> None:
    model = model_for(canvas)
    coords_3d = {
        atom_id: coords
        for atom_id, coords in atom_coords_3d_for(canvas).items()
        if _stored_atom_coords_3d_matches_projection(canvas, atom_id, coords)
    }
    if not coords_3d:
        return
    rotation = rotation_state_for(canvas)
    state["perspective"] = {
        "atom_coords_3d": {
            atom_id: coords
            for atom_id, coords in coords_3d.items()
            if atom_id in model.atoms
        },
        "projection_center_3d": rotation.projection_center_3d,
        "projection_anchor_2d": rotation.projection_anchor_2d,
    }


def _stored_atom_coords_3d_matches_projection(canvas, atom_id: int, coords: tuple[float, float, float]) -> bool:
    atom = model_for(canvas).atoms.get(atom_id)
    if atom is None:
        return False
    proj_x, proj_y = project_point_3d_for(canvas, coords)
    tolerance = max(1.0, bond_length_px_for(canvas) * 0.15)
    return math.hypot(proj_x - atom.x, proj_y - atom.y) <= tolerance


def restore_document_projection_state(canvas, state: dict) -> None:
    perspective_state = state.get("perspective") or {}
    coords_state = perspective_state.get("atom_coords_3d", {})
    coords_3d = {
        int(atom_id): (float(coords[0]), float(coords[1]), float(coords[2]))
        for atom_id, coords in coords_state.items()
    }
    set_atom_coords_3d_for(canvas, coords_3d)
    rotation = rotation_state_for(canvas)
    center = perspective_state.get("projection_center_3d")
    anchor = perspective_state.get("projection_anchor_2d")
    rotation.projection_center_3d = (
        (float(center[0]), float(center[1]), float(center[2]))
        if center is not None
        else None
    )
    rotation.projection_anchor_2d = (
        (float(anchor[0]), float(anchor[1]))
        if anchor is not None
        else None
    )


def apply_document_settings(canvas, state: dict) -> None:
    settings = state["settings"]
    default_text_style = CanvasTextStyleState()
    set_bond_length_for(canvas, settings["bond_length_px"])
    set_tool_setting_for(canvas, "arrow_line_width", settings["arrow_line_width"])
    set_tool_setting_for(canvas, "arrow_head_scale", settings["arrow_head_scale"])
    set_tool_setting_for(canvas, "orbital_phase_enabled", settings["orbital_phase_enabled"])
    set_text_style_for(canvas, "text_font_family", settings.get("text_font_family", default_text_style.text_font_family))
    set_text_style_for(canvas, "text_font_size", settings["text_font_size"])
    set_text_style_for(canvas, "text_font_weight", settings["text_font_weight"])
    set_text_style_for(canvas, "text_italic", settings["text_italic"])
    set_text_style_for(
        canvas,
        "text_color",
        _color_from_setting(settings.get("text_color"), default_text_style.text_color),
    )
    set_text_style_for(
        canvas,
        "text_alignment",
        _alignment_from_name(settings.get("text_alignment"), default_text_style.text_alignment),
    )
    set_text_style_for(canvas, "text_line_spacing", settings.get("text_line_spacing", default_text_style.text_line_spacing))
    set_text_style_for(canvas, "note_box_enabled", settings.get("note_box_enabled", default_text_style.note_box_enabled))
    set_text_style_for(
        canvas,
        "note_box_color",
        _color_from_setting(settings.get("note_box_color"), default_text_style.note_box_color),
    )
    set_text_style_for(canvas, "note_box_alpha", settings.get("note_box_alpha", default_text_style.note_box_alpha))
    set_text_style_for(
        canvas,
        "note_border_enabled",
        settings.get("note_border_enabled", default_text_style.note_border_enabled),
    )
    set_text_style_for(
        canvas,
        "note_border_color",
        _color_from_setting(settings.get("note_border_color"), default_text_style.note_border_color),
    )
    set_text_style_for(canvas, "note_border_width", settings.get("note_border_width", default_text_style.note_border_width))
    set_text_style_for(canvas, "note_padding", settings.get("note_padding", default_text_style.note_padding))
    set_sheet_setup_for(canvas, settings["sheet_size"], settings["sheet_orientation"])
    set_last_smiles_input_for(canvas, state["last_smiles_input"])


def _alignment_name(alignment) -> str:
    if alignment == Qt.AlignmentFlag.AlignHCenter:
        return "center"
    if alignment == Qt.AlignmentFlag.AlignRight:
        return "right"
    if alignment == Qt.AlignmentFlag.AlignJustify:
        return "justify"
    return "left"


def _alignment_from_name(value, fallback):
    return {
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "justify": Qt.AlignmentFlag.AlignJustify,
    }.get(value, fallback)


def _color_from_setting(value, fallback: QColor) -> QColor:
    if isinstance(value, str):
        color = QColor(value)
        if color.isValid():
            return color
    return QColor(fallback)


def restore_document_pre_model_items(canvas, state: dict) -> None:
    for ring_state in state["ring_fills"]:
        restore_ring_from_state(canvas, ring_state)


def restore_document_post_model_items(canvas, state: dict) -> None:
    for note_state in state["notes"]:
        restore_note_from_state(canvas, note_state)

    for mark_state in state["marks"]:
        restore_mark_from_state(
            canvas,
            {
                "kind": "mark",
                "mark_kind": mark_state["kind"],
                "text": mark_state["text"],
                "atom_id": mark_state["atom_id"],
                "dx": mark_state["dx"],
                "dy": mark_state["dy"],
                "x": mark_state["x"],
                "y": mark_state["y"],
            }
        )

    for arrow_state in state["arrows"]:
        restore_arrow_from_state(canvas, arrow_state)

    for ts_bracket_state in state["ts_brackets"]:
        restore_ts_bracket_from_state(canvas, ts_bracket_state)

    for shape_state in state.get("shapes", []):
        restore_shape_from_state(canvas, shape_state)

    for orbital_state in state["orbitals"]:
        restore_orbital_from_state(
            canvas,
            {
                "kind": "orbital",
                "orbital_kind": orbital_state["kind"],
                "center": orbital_state["center"],
                "scale": orbital_state["scale"],
                "rotation": orbital_state["rotation"],
            }
        )


def _snapshot_ring_fills(canvas) -> list[dict]:
    ring_fills: list[dict] = []
    for ring_item in attached_canvas_scene_items(canvas, ring_items_for(canvas)):
        ring_state = ring_state_dict_for(canvas, ring_item)
        ring_fills.append(
            {
                "points": ring_state["points"],
                "atom_ids": ring_state["atom_ids"],
                "color": ring_state["color"],
                "alpha": ring_state["alpha"],
            }
        )
    return ring_fills


def _snapshot_notes(canvas) -> list[dict]:
    notes: list[dict] = []
    for item in attached_canvas_scene_items(canvas, note_items_for(canvas)):
        note_state = note_state_dict_for(canvas, item)
        snapshot = {
            "text": note_state["text"],
            "x": note_state["x"],
            "y": note_state["y"],
        }
        html = note_state.get("html")
        if isinstance(html, str):
            snapshot["html"] = html
        notes.append(snapshot)
    return notes


def _snapshot_marks(canvas) -> list[dict]:
    marks: list[dict] = []
    for item in attached_canvas_scene_items(canvas, mark_items_for(canvas)):
        mark_state = mark_state_dict_for(canvas, item)
        marks.append(
            {
                "kind": mark_state["mark_kind"],
                "text": mark_state["text"],
                "atom_id": mark_state["atom_id"],
                "dx": mark_state["dx"],
                "dy": mark_state["dy"],
                "x": mark_state["x"],
                "y": mark_state["y"],
            }
        )
    return marks


def _snapshot_arrows(canvas) -> list[dict]:
    arrows: list[dict] = []
    for item in attached_canvas_scene_items(canvas, arrow_items_for(canvas)):
        arrow_state = arrow_state_dict_for(canvas, item)
        if not arrow_state:
            continue
        arrows.append(arrow_state)
    return arrows


def _snapshot_ts_brackets(canvas) -> list[dict]:
    ts_brackets: list[dict] = []
    for item in attached_canvas_scene_items(canvas, ts_bracket_items_for(canvas)):
        ts_brackets.append(ts_bracket_state_dict_for(canvas, item))
    return ts_brackets


def _snapshot_shapes(canvas) -> list[dict]:
    shapes: list[dict] = []
    for item in attached_canvas_scene_items(canvas, shape_items_for(canvas)):
        shapes.append(shape_state_dict_for(canvas, item))
    return shapes


def _snapshot_orbitals(canvas) -> list[dict]:
    orbitals: list[dict] = []
    for item in attached_canvas_scene_items(canvas, orbital_items_for(canvas)):
        orbital_state = orbital_state_dict_for(canvas, item)
        orbitals.append(
            {
                "kind": orbital_state["orbital_kind"],
                "center": orbital_state["center"],
                "scale": orbital_state["scale"],
                "rotation": orbital_state["rotation"],
            }
        )
    return orbitals
