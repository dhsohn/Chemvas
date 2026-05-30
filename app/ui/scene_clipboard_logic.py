from __future__ import annotations

import json
from typing import Callable, Mapping, Sequence

from PyQt6.QtCore import QMimeData
from PyQt6.QtWidgets import QGraphicsItem


CLIPBOARD_SELECTION_FORMAT = "chemvas-selection"


def build_selection_clipboard_payload(
    *,
    selected_items: Sequence[QGraphicsItem],
    explicit_atom_ids: set[int],
    selected_bond_ids: set[int],
    bonds: Sequence[object | None],
    ring_items: Sequence[QGraphicsItem],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
    scene,
    atom_state_getter: Callable[[int], dict],
    bond_state_getter: Callable[[object], dict],
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    version: int,
) -> dict | None:
    atom_ids = set(explicit_atom_ids)
    for bond_id in selected_bond_ids:
        if not (0 <= bond_id < len(bonds)):
            continue
        bond = bonds[bond_id]
        if bond is None:
            continue
        atom_ids.add(bond.a)
        atom_ids.add(bond.b)

    atoms: list[dict] = []
    for atom_id in sorted(atom_ids):
        atom_state = atom_state_getter(atom_id)
        if not atom_state:
            continue
        atoms.append({"id": atom_id, **atom_state})

    serialized_bonds: list[dict] = []
    if atom_ids:
        for bond in bonds:
            if bond is None or bond.a not in atom_ids or bond.b not in atom_ids:
                continue
            serialized_bonds.append(bond_state_getter(bond))

    rings: list[dict] = []
    for ring_item in ring_items:
        try:
            if ring_item.scene() is not scene:
                continue
        except RuntimeError:
            continue
        ring_atom_ids = ring_item.data(2)
        if not isinstance(ring_atom_ids, list) or not ring_atom_ids:
            continue
        if not all(isinstance(atom_id, int) and atom_id in atom_ids for atom_id in ring_atom_ids):
            continue
        ring_state = scene_item_state_getter(ring_item)
        if ring_state:
            rings.append(ring_state)

    marks: list[dict] = []
    seen_mark_items: set[QGraphicsItem] = set()
    for atom_id in sorted(atom_ids):
        for mark_item in list(marks_by_atom.get(atom_id, [])):
            try:
                if mark_item.scene() is not scene:
                    continue
            except RuntimeError:
                continue
            if mark_item in seen_mark_items:
                continue
            mark_state = scene_item_state_getter(mark_item)
            if not mark_state:
                continue
            seen_mark_items.add(mark_item)
            marks.append(mark_state)
    for item in selected_items:
        if item.data(0) != "mark" or item in seen_mark_items:
            continue
        mark_state = scene_item_state_getter(item)
        if not mark_state:
            continue
        seen_mark_items.add(item)
        marks.append(mark_state)

    scene_item_states: list[dict] = []
    for item in selected_items:
        kind = item.data(0)
        if kind in {"atom", "bond", "ring", "mark"}:
            continue
        state = scene_item_state_getter(item)
        if state:
            scene_item_states.append(state)

    if not atoms and not marks and not rings and not scene_item_states:
        return None
    return {
        "format": CLIPBOARD_SELECTION_FORMAT,
        "version": version,
        "atoms": atoms,
        "bonds": serialized_bonds,
        "rings": rings,
        "marks": marks,
        "scene_items": scene_item_states,
    }


def clipboard_payload_candidates(
    mime_data: QMimeData | None,
    *,
    mime_type: str,
) -> list[str]:
    payload_candidates: list[str] = []
    if mime_data is not None and mime_data.hasFormat(mime_type):
        try:
            payload_candidates.append(bytes(mime_data.data(mime_type)).decode("utf-8"))
        except UnicodeDecodeError:
            pass
    return payload_candidates


def decode_clipboard_selection_payload(
    payload_candidates: Sequence[str],
    *,
    version: int,
) -> tuple[dict | None, str | None]:
    for payload_json in payload_candidates:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("format") != CLIPBOARD_SELECTION_FORMAT:
            continue
        if payload.get("version") != version:
            continue
        return payload, payload_json
    return None, None


__all__ = [
    "CLIPBOARD_SELECTION_FORMAT",
    "build_selection_clipboard_payload",
    "clipboard_payload_candidates",
    "decode_clipboard_selection_payload",
]
