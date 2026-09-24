"""Validation of clipboard selection payloads against the document schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from chemvas.domain.document.schema import (
    CLIPBOARD_SELECTION_PAYLOAD_KEYS,
    CLIPBOARD_SELECTION_REQUIRED_KEYS,
    SUPPORTED_CLIPBOARD_VERSIONS,
    VALID_ARROW_KINDS,
    VALID_MARK_KINDS,
)
from chemvas.domain.document.state_validation import (
    _is_valid_choice,
    _validate_atom_annotation,
    _validate_atom_fields,
    _validate_bond_fields,
    _validate_group_states,
    _validate_mark_text,
    _validate_note_fields,
    _validate_optional_point_2d,
    _validate_optional_point_3d,
    _validate_orbital_fields,
    _validate_ring_fields,
    _validated_scene_state_list,
    validate_arrow_fields,
    validate_shape_fields,
    validate_ts_bracket_fields,
)
from chemvas.domain.document.state_values import (
    _is_hex_color,
    _is_number,
    _is_point_3d,
    _validated_clipboard_id,
)

from .images import validate_image_states

if TYPE_CHECKING:
    from decimal import Decimal


def validate_clipboard_selection_payload(payload: Mapping[str, object]) -> bool:
    """Whitelist-validate a decoded clipboard selection payload.

    Clipboard MIME data sits outside the application's trust boundary (any other
    app or script can inject it), so paste input is held to the same standard as
    ``.chemvas`` file loading. This verifies the envelope and structural content.
    Returns ``True`` only when every section is well-formed, otherwise ``False``
    so the caller can reject the whole paste rather than build invalid scene state.
    """
    try:
        if (
            not isinstance(payload, Mapping)
            or payload.get("format") != "chemvas-selection"
            or type(payload.get("version")) is not int
            or payload.get("version") not in SUPPORTED_CLIPBOARD_VERSIONS
            or not CLIPBOARD_SELECTION_REQUIRED_KEYS <= set(payload)
            or not set(payload) <= CLIPBOARD_SELECTION_PAYLOAD_KEYS
        ):
            raise ValueError("Invalid clipboard payload.")
        atom_ids, atom_positions = _validate_clipboard_atoms(payload.get("atoms"))
        bond_pairs = _validate_clipboard_bonds(payload.get("bonds"), atom_ids)
        for ring_state in _validated_scene_state_list(payload.get("rings")):
            _validate_clipboard_ring(ring_state, atom_ids, bond_pairs, atom_positions)
        for mark_state in _validated_scene_state_list(payload.get("marks")):
            _validate_clipboard_mark(mark_state, atom_ids)
        scene_items = _validated_scene_state_list(payload.get("scene_items"))
        validate_image_states(
            [item for item in scene_items if item.get("kind") == "image"]
        )
        for item_state in scene_items:
            _validate_clipboard_scene_item(item_state)
            if payload["version"] == 2:
                kind = item_state.get("kind")
                if (kind == "note" and "rotation" in item_state) or (
                    kind in {"image", "shape"} and "z" in item_state
                ):
                    raise ValueError("Clipboard transforms require version 3.")
        _validate_clipboard_perspective(payload, atom_ids)
        _validate_group_states(
            payload, atom_ids, item_keys=frozenset(("marks", "scene_items"))
        )
    except ValueError:
        return False
    return True


def _validate_clipboard_atoms(
    atoms: object,
) -> tuple[set[int], dict[int, tuple[int | float | Decimal, int | float | Decimal]]]:
    if not isinstance(atoms, list):
        raise ValueError("Invalid clipboard payload.")
    atom_ids: set[int] = set()
    atom_positions: dict[int, tuple[int | float | Decimal, int | float | Decimal]] = {}
    for atom_state in atoms:
        if not isinstance(atom_state, Mapping):
            raise ValueError("Invalid clipboard payload.")
        required_keys = {"id", "element", "x", "y", "color", "explicit_label"}
        if not required_keys <= set(atom_state) or not set(
            atom_state
        ) <= required_keys | {"annotation"}:
            raise ValueError("Invalid clipboard payload.")
        atom_id = _validated_clipboard_id(atom_state.get("id"))
        if atom_id in atom_ids:
            raise ValueError("Invalid clipboard payload.")
        _validate_atom_fields(atom_state, error="Invalid clipboard payload.")
        _validate_atom_annotation(atom_state.get("annotation", {}))
        atom_ids.add(atom_id)
        atom_positions[atom_id] = (
            cast("int | float | Decimal", atom_state.get("x")),
            cast("int | float | Decimal", atom_state.get("y")),
        )
    return atom_ids, atom_positions


def _validate_clipboard_perspective(
    payload: Mapping[str, object], atom_ids: set[int]
) -> None:
    perspective_state = payload.get("perspective")
    if perspective_state is None:
        return
    version = payload.get("version")
    if type(version) is not int or version not in SUPPORTED_CLIPBOARD_VERSIONS:
        raise ValueError("Invalid clipboard payload.")
    if not isinstance(perspective_state, Mapping):
        raise ValueError("Invalid clipboard payload.")
    if set(perspective_state) != {
        "atom_coords_3d",
        "projection_center_3d",
        "projection_anchor_2d",
    }:
        raise ValueError("Invalid clipboard payload.")
    atom_coords_3d = perspective_state.get("atom_coords_3d")
    if not isinstance(atom_coords_3d, list):
        raise ValueError("Invalid clipboard payload.")
    seen_atom_ids: set[int] = set()
    for entry in atom_coords_3d:
        if not isinstance(entry, Mapping) or set(entry) != {"atom_id", "coords"}:
            raise ValueError("Invalid clipboard payload.")
        atom_id = _validated_clipboard_id(entry.get("atom_id"))
        if (
            atom_id in seen_atom_ids
            or atom_id not in atom_ids
            or not _is_point_3d(entry.get("coords"))
        ):
            raise ValueError("Invalid clipboard payload.")
        seen_atom_ids.add(atom_id)
    _validate_optional_point_3d(perspective_state.get("projection_center_3d"))
    _validate_optional_point_2d(perspective_state.get("projection_anchor_2d"))


def _validate_clipboard_bonds(
    bonds: object, atom_ids: set[int]
) -> set[tuple[int, int]]:
    if not isinstance(bonds, list):
        raise ValueError("Invalid clipboard payload.")
    bond_pairs: set[tuple[int, int]] = set()
    for bond_state in bonds:
        if not isinstance(bond_state, Mapping):
            raise ValueError("Invalid clipboard payload.")
        bond_pair = _validate_bond_fields(
            bond_state,
            atom_ids,
            id_validator=_validated_clipboard_id,
            error="Invalid clipboard payload.",
        )
        if bond_pair in bond_pairs:
            raise ValueError("Invalid clipboard payload.")
        bond_pairs.add(bond_pair)
    return bond_pairs


def _validate_clipboard_ring(
    ring_state: Mapping[str, object],
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
    atom_positions: Mapping[int, tuple[int | float | Decimal, int | float | Decimal]],
) -> None:
    if ring_state.get("kind") != "ring":
        raise ValueError("Invalid clipboard payload.")
    _validate_ring_fields(
        ring_state,
        atom_ids,
        bond_pairs,
        atom_positions,
        required_keys=frozenset(("kind", "points", "atom_ids", "color", "alpha")),
        clipboard=True,
        error="Invalid clipboard payload.",
    )


def _validate_clipboard_mark(
    mark_state: Mapping[str, object], atom_ids: set[int]
) -> None:
    if mark_state.get("kind") != "mark":
        raise ValueError("Invalid clipboard payload.")
    required = {
        "kind",
        "mark_kind",
        "text",
        "atom_id",
        "dx",
        "dy",
        "x",
        "y",
    }
    keys = set(mark_state)
    if not required <= keys or keys - required - {"color"}:
        raise ValueError("Invalid clipboard payload.")
    if "color" in keys and not _is_hex_color(mark_state["color"]):
        raise ValueError("Invalid clipboard payload. Mark color must be a hex color.")
    mark_kind = mark_state.get("mark_kind")
    if not _is_valid_choice(mark_kind, VALID_MARK_KINDS):
        raise ValueError("Invalid clipboard payload.")
    text = mark_state.get("text")
    _validate_mark_text(text, error="Invalid clipboard payload.")
    if not _is_number(mark_state.get("x")) or not _is_number(mark_state.get("y")):
        raise ValueError("Invalid clipboard payload.")
    atom_id = mark_state.get("atom_id")
    dx = mark_state.get("dx")
    dy = mark_state.get("dy")
    if atom_id is None:
        if dx is not None or dy is not None:
            raise ValueError("Invalid clipboard payload.")
        return
    if type(atom_id) is not int or atom_id not in atom_ids:
        raise ValueError("Invalid clipboard payload.")
    if (dx is None and dy is None) or (_is_number(dx) and _is_number(dy)):
        return
    raise ValueError("Invalid clipboard payload.")


def _validate_clipboard_scene_item(item_state: Mapping[str, object]) -> None:
    kind = item_state.get("kind")
    if not isinstance(kind, str):
        raise ValueError("Invalid clipboard payload.")
    if kind == "note":
        _validate_note_fields(
            item_state,
            required_keys=frozenset(("kind", "text", "x", "y")),
            error="Invalid clipboard payload.",
        )
        return
    if kind in VALID_ARROW_KINDS:
        validate_arrow_fields(item_state, error="Invalid clipboard payload.")
        return
    if kind == "ts_bracket":
        validate_ts_bracket_fields(item_state, error="Invalid clipboard payload.")
        return
    if kind == "shape":
        validate_shape_fields(item_state, error="Invalid clipboard payload.")
        return
    if kind == "image":
        # The complete image set was validated together before scene traversal.
        return
    if kind == "orbital":
        _validate_orbital_fields(
            item_state,
            kind_key="orbital_kind",
            required_keys=frozenset(
                ("kind", "orbital_kind", "center", "scale", "rotation")
            ),
            error="Invalid clipboard payload.",
        )
        return
    raise ValueError("Invalid clipboard payload.")


__all__ = [
    "validate_clipboard_selection_payload",
]
