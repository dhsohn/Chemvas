from __future__ import annotations

from collections.abc import Iterable

from core.document_state import serialize_model_state, serialize_settings


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
            text_font_weight=canvas.text_font_weight,
            text_italic=canvas.text_italic,
        ),
        "last_smiles_input": canvas.last_smiles_input,
    }


def apply_document_settings(canvas, state: dict) -> None:
    settings = state.get("settings", {})
    bond_length = settings.get("bond_length_px", canvas.renderer.style.bond_length_px)
    canvas.renderer.set_bond_length(bond_length)
    canvas.arrow_line_width = settings.get("arrow_line_width", canvas.arrow_line_width)
    canvas.arrow_head_scale = settings.get("arrow_head_scale", canvas.arrow_head_scale)
    canvas.orbital_phase_enabled = settings.get("orbital_phase_enabled", canvas.orbital_phase_enabled)
    canvas.text_font_size = settings.get("text_font_size", canvas.text_font_size)
    canvas.text_font_weight = settings.get("text_font_weight", canvas.text_font_weight)
    canvas.text_italic = settings.get("text_italic", canvas.text_italic)
    canvas.last_smiles_input = state.get("last_smiles_input")


def restore_document_pre_model_items(canvas, state: dict) -> None:
    for ring_state in state.get("ring_fills", []):
        canvas._restore_ring_from_state(ring_state)


def restore_document_post_model_items(canvas, state: dict) -> None:
    for note_state in state.get("notes", []):
        canvas._restore_note_from_state(note_state)

    for mark_state in state.get("marks", []):
        canvas._restore_mark_from_state(
            {
                "kind": "mark",
                "mark_kind": mark_state.get("kind", "plus"),
                "text": mark_state.get("text"),
                "atom_id": mark_state.get("atom_id"),
                "dx": mark_state.get("dx"),
                "dy": mark_state.get("dy"),
                "x": mark_state.get("x"),
                "y": mark_state.get("y"),
            }
        )

    for arrow_state in state.get("arrows", []):
        canvas._restore_arrow_from_state(arrow_state)

    for ts_bracket_state in state.get("ts_brackets", []):
        canvas._restore_ts_bracket_from_state(ts_bracket_state)

    for orbital_state in state.get("orbitals", []):
        canvas._restore_orbital_from_state(
            {
                "kind": "orbital",
                "orbital_kind": orbital_state.get("kind", "s"),
                "center": orbital_state.get("center"),
                "scale": orbital_state.get("scale", 1.0),
                "rotation": orbital_state.get("rotation", 0.0),
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
                "points": ring_state.get("points", []),
                "atom_ids": ring_state.get("atom_ids"),
                "color": ring_state.get("color"),
                "alpha": ring_state.get("alpha", 0.0),
            }
        )
    return ring_fills


def _snapshot_notes(canvas) -> list[dict]:
    notes: list[dict] = []
    for item in _attached_items(canvas.note_items, canvas.scene()):
        note_state = canvas._note_state_dict(item)
        notes.append(
            {
                "text": note_state.get("text", ""),
                "x": note_state.get("x", 0.0),
                "y": note_state.get("y", 0.0),
            }
        )
    return notes


def _snapshot_marks(canvas) -> list[dict]:
    marks: list[dict] = []
    for item in _attached_items(canvas.mark_items, canvas.scene()):
        mark_state = canvas._mark_state_dict(item)
        marks.append(
            {
                "kind": mark_state.get("mark_kind"),
                "text": mark_state.get("text"),
                "atom_id": mark_state.get("atom_id"),
                "dx": mark_state.get("dx"),
                "dy": mark_state.get("dy"),
                "x": mark_state.get("x", 0.0),
                "y": mark_state.get("y", 0.0),
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
                "kind": orbital_state.get("orbital_kind", "s"),
                "center": orbital_state.get("center"),
                "scale": orbital_state.get("scale", 1.0),
                "rotation": orbital_state.get("rotation", 0.0),
            }
        )
    return orbitals
