from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Mapping, Sequence

from core.document_state import validate_clipboard_selection_payload
from core.model import Bond
from PyQt6.QtCore import QMimeData
from PyQt6.QtWidgets import QGraphicsItem

CLIPBOARD_SELECTION_FORMAT = "chemvas-selection"


def _item_in_scene(item: QGraphicsItem, scene) -> bool:
    """True if the item still belongs to the scene; deleted items count as gone."""
    try:
        return item.scene() is scene
    except RuntimeError:
        return False


def _selection_atom_ids(
    explicit_atom_ids: set[int],
    selected_bond_ids: set[int],
    bonds: Sequence[Bond | None],
) -> set[int]:
    atom_ids = set(explicit_atom_ids)
    for bond_id in selected_bond_ids:
        if not (0 <= bond_id < len(bonds)):
            continue
        bond = bonds[bond_id]
        if bond is None:
            continue
        atom_ids.add(bond.a)
        atom_ids.add(bond.b)
    return atom_ids


def _serialize_atoms(atom_ids: set[int], atom_state_getter: Callable[[int], dict]) -> list[dict]:
    atoms: list[dict] = []
    for atom_id in sorted(atom_ids):
        atom_state = atom_state_getter(atom_id)
        if atom_state:
            atoms.append({"id": atom_id, **atom_state})
    return atoms


def _serialize_bonds(
    atom_ids: set[int],
    bonds: Sequence[Bond | None],
    bond_state_getter: Callable[[object], dict],
) -> list[dict]:
    if not atom_ids:
        return []
    return [
        bond_state_getter(bond)
        for bond in bonds
        if bond is not None and bond.a in atom_ids and bond.b in atom_ids
    ]


def _serialize_rings(
    ring_items: Sequence[QGraphicsItem],
    atom_ids: set[int],
    scene,
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
) -> list[dict]:
    rings: list[dict] = []
    for ring_item in ring_items:
        if not _item_in_scene(ring_item, scene):
            continue
        ring_atom_ids = ring_item.data(2)
        if not isinstance(ring_atom_ids, list) or not ring_atom_ids:
            continue
        if not all(isinstance(atom_id, int) and atom_id in atom_ids for atom_id in ring_atom_ids):
            continue
        ring_state = scene_item_state_getter(ring_item)
        if ring_state:
            rings.append(ring_state)
    return rings


def _serialize_marks(
    atom_ids: set[int],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
    selected_items: Sequence[QGraphicsItem],
    scene,
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
) -> list[dict]:
    marks: list[dict] = []
    seen_mark_items: set[QGraphicsItem] = set()
    for atom_id in sorted(atom_ids):
        for mark_item in list(marks_by_atom.get(atom_id, [])):
            if not _item_in_scene(mark_item, scene):
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
        marks.append(_selected_mark_state_for_payload(mark_state, atom_ids))
    return marks


def _selected_mark_state_for_payload(mark_state: dict, atom_ids: set[int]) -> dict:
    atom_id = mark_state.get("atom_id")
    if not isinstance(atom_id, int) or atom_id in atom_ids:
        return mark_state
    detached = dict(mark_state)
    detached["atom_id"] = None
    detached["dx"] = None
    detached["dy"] = None
    return detached


def _serialize_scene_items(
    selected_items: Sequence[QGraphicsItem],
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
) -> list[dict]:
    scene_item_states: list[dict] = []
    for item in selected_items:
        if item.data(0) in {"atom", "bond", "ring", "mark"}:
            continue
        state = scene_item_state_getter(item)
        if state:
            scene_item_states.append(state)
    return scene_item_states


def build_selection_clipboard_payload(
    *,
    selected_items: Sequence[QGraphicsItem],
    explicit_atom_ids: set[int],
    selected_bond_ids: set[int],
    bonds: Sequence[Bond | None],
    ring_items: Sequence[QGraphicsItem],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
    scene,
    atom_state_getter: Callable[[int], dict],
    bond_state_getter: Callable[[object], dict],
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    version: int,
) -> dict | None:
    atom_ids = _selection_atom_ids(explicit_atom_ids, selected_bond_ids, bonds)
    atoms = _serialize_atoms(atom_ids, atom_state_getter)
    serialized_bonds = _serialize_bonds(atom_ids, bonds, bond_state_getter)
    rings = _serialize_rings(ring_items, atom_ids, scene, scene_item_state_getter)
    marks = _serialize_marks(atom_ids, marks_by_atom, selected_items, scene, scene_item_state_getter)
    scene_item_states = _serialize_scene_items(selected_items, scene_item_state_getter)

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
        with contextlib.suppress(UnicodeDecodeError):
            payload_candidates.append(mime_data.data(mime_type).data().decode("utf-8"))
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
        # Clipboard MIME is outside the trust boundary: reject any payload whose
        # content does not pass the same whitelist used for .chemvas files.
        if not validate_clipboard_selection_payload(payload):
            continue
        return payload, payload_json
    return None, None


__all__ = [
    "CLIPBOARD_SELECTION_FORMAT",
    "build_selection_clipboard_payload",
    "clipboard_payload_candidates",
    "decode_clipboard_selection_payload",
]
