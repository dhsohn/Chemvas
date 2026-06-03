from __future__ import annotations

from collections.abc import Iterable

from core.document_state import serialize_model_state, serialize_settings

from ui.scene_item_access import (
    restore_arrow_from_state,
    restore_mark_from_state,
    restore_note_from_state,
    restore_orbital_from_state,
    restore_ring_from_state,
    restore_ts_bracket_from_state,
)


def snapshot_canvas_document_state(canvas) -> dict:
    return {
        "model": serialize_model_state(
            canvas.model,
            explicit_label_atom_ids=canvas.atom_items.keys(),
        ),
        "ring_fills": _snapshot_ring_fills(canvas),
        "notes": _snapshot_notes(canvas),
        "marks": _snapshot_marks(canvas),
        "arrows": _snapshot_arrows(canvas),
        "ts_brackets": _snapshot_ts_brackets(canvas),
        "orbitals": _snapshot_orbitals(canvas),
        "settings": serialize_settings(
            bond_length_px=canvas.renderer.style.bond_length_px,
            arrow_line_width=canvas.arrow_line_width,
            arrow_head_scale=canvas.arrow_head_scale,
            orbital_phase_enabled=canvas.orbital_phase_enabled,
            text_font_size=canvas.text_font_size,
            text_font_weight=int(canvas.text_font_weight),
            text_italic=canvas.text_italic,
            sheet_size=canvas.sheet_size,
            sheet_orientation=canvas.sheet_orientation,
        ),
        "last_smiles_input": canvas.last_smiles_input,
    }


def apply_document_settings(canvas, state: dict) -> None:
    settings = state["settings"]
    canvas.renderer.set_bond_length(settings["bond_length_px"])
    canvas.arrow_line_width = settings["arrow_line_width"]
    canvas.arrow_head_scale = settings["arrow_head_scale"]
    canvas.orbital_phase_enabled = settings["orbital_phase_enabled"]
    canvas.text_font_size = settings["text_font_size"]
    canvas.text_font_weight = settings["text_font_weight"]
    canvas.text_italic = settings["text_italic"]
    canvas.set_sheet_setup(settings["sheet_size"], settings["sheet_orientation"])
    canvas.last_smiles_input = state["last_smiles_input"]


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


def _attached_items(items: Iterable, scene) -> list:
    attached_items = []
    for item in items:
        try:
            if item.scene() is not scene:
                continue
        except RuntimeError:
            continue
        attached_items.append(item)
    return attached_items


def _snapshot_ring_fills(canvas) -> list[dict]:
    ring_fills: list[dict] = []
    for ring_item in _attached_items(canvas.ring_items, canvas.scene()):
        ring_state = canvas._ring_state_dict(ring_item)
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
    for item in _attached_items(canvas.note_items, canvas.scene()):
        note_state = canvas._note_state_dict(item)
        notes.append(
            {
                "text": note_state["text"],
                "x": note_state["x"],
                "y": note_state["y"],
            }
        )
    return notes


def _snapshot_marks(canvas) -> list[dict]:
    marks: list[dict] = []
    for item in _attached_items(canvas.mark_items, canvas.scene()):
        mark_state = canvas._mark_state_dict(item)
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
    for item in _attached_items(canvas.arrow_items, canvas.scene()):
        arrow_state = canvas._arrow_state_dict(item)
        if not arrow_state:
            continue
        arrows.append(arrow_state)
    return arrows


def _snapshot_ts_brackets(canvas) -> list[dict]:
    ts_brackets: list[dict] = []
    for item in _attached_items(canvas.ts_bracket_items, canvas.scene()):
        ts_brackets.append(canvas._ts_bracket_state_dict(item))
    return ts_brackets


def _snapshot_orbitals(canvas) -> list[dict]:
    orbitals: list[dict] = []
    for item in _attached_items(canvas.orbital_items, canvas.scene()):
        orbital_state = canvas._orbital_state_dict(item)
        orbitals.append(
            {
                "kind": orbital_state["orbital_kind"],
                "center": orbital_state["center"],
                "scale": orbital_state["scale"],
                "rotation": orbital_state["rotation"],
            }
        )
    return orbitals
