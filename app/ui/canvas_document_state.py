from __future__ import annotations

from core.document_state import serialize_model_state, serialize_settings

from ui.canvas_atom_graphics_state import atom_items_for
from ui.canvas_model_access import model_for
from ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    ts_bracket_items_for,
)
from ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from ui.canvas_tool_settings_state import set_tool_setting_for, tool_settings_state_for
from ui.renderer_style_access import bond_length_px_for, set_bond_length_for
from ui.scene_item_access import (
    attached_canvas_scene_items,
    restore_arrow_from_state,
    restore_mark_from_state,
    restore_note_from_state,
    restore_orbital_from_state,
    restore_ring_from_state,
    restore_ts_bracket_from_state,
)
from ui.scene_item_state import (
    arrow_state_dict_for,
    mark_state_dict_for,
    note_state_dict_for,
    orbital_state_dict_for,
    ring_state_dict_for,
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
    return {
        "model": serialize_model_state(
            model_for(canvas),
            explicit_label_atom_ids=atom_items_for(canvas).keys(),
        ),
        "ring_fills": _snapshot_ring_fills(canvas),
        "notes": _snapshot_notes(canvas),
        "marks": _snapshot_marks(canvas),
        "arrows": _snapshot_arrows(canvas),
        "ts_brackets": _snapshot_ts_brackets(canvas),
        "orbitals": _snapshot_orbitals(canvas),
        "settings": serialize_settings(
            bond_length_px=bond_length_px_for(canvas),
            arrow_line_width=tool_settings.arrow_line_width,
            arrow_head_scale=tool_settings.arrow_head_scale,
            orbital_phase_enabled=tool_settings.orbital_phase_enabled,
            text_font_size=text_style.text_font_size,
            text_font_weight=int(text_style.text_font_weight),
            text_italic=text_style.text_italic,
            sheet_size=sheet_size_for(canvas),
            sheet_orientation=sheet_orientation_for(canvas),
        ),
        "last_smiles_input": last_smiles_input_for(canvas),
    }


def apply_document_settings(canvas, state: dict) -> None:
    settings = state["settings"]
    set_bond_length_for(canvas, settings["bond_length_px"])
    set_tool_setting_for(canvas, "arrow_line_width", settings["arrow_line_width"])
    set_tool_setting_for(canvas, "arrow_head_scale", settings["arrow_head_scale"])
    set_tool_setting_for(canvas, "orbital_phase_enabled", settings["orbital_phase_enabled"])
    set_text_style_for(canvas, "text_font_size", settings["text_font_size"])
    set_text_style_for(canvas, "text_font_weight", settings["text_font_weight"])
    set_text_style_for(canvas, "text_italic", settings["text_italic"])
    set_sheet_setup_for(canvas, settings["sheet_size"], settings["sheet_orientation"])
    set_last_smiles_input_for(canvas, state["last_smiles_input"])


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
