from __future__ import annotations

import math
from collections.abc import Collection, Mapping

from core.model import Atom, Bond, MoleculeModel


CHEMVAS_FILE_TYPE = "chemvas"
LEGACY_DOCUMENT_FILE_TYPE = "litedraw"
SUPPORTED_FILE_TYPES = frozenset((CHEMVAS_FILE_TYPE, LEGACY_DOCUMENT_FILE_TYPE))
SINGLE_SHEET_FILE_VERSION = 1
WORKBOOK_FILE_VERSION = 2
SUPPORTED_FILE_VERSIONS = frozenset((SINGLE_SHEET_FILE_VERSION, WORKBOOK_FILE_VERSION))
VALID_BOND_ORDERS = frozenset((1, 2, 3))
VALID_BOND_STYLES = frozenset(
    (
        "single",
        "double",
        "double_center",
        "double_outer",
        "triple",
        "wedge",
        "hash",
        "dotted",
        "dotted_double",
        "dotted_double_outer",
        "bold",
        "bold_in",
        "bold_out",
    )
)


def atom_to_state(atom: Atom, explicit_label: bool) -> dict:
    return {
        "element": atom.element,
        "x": atom.x,
        "y": atom.y,
        "color": atom.color,
        "explicit_label": explicit_label or atom.explicit_label,
    }


def bond_to_state(bond: Bond | None) -> dict | None:
    if bond is None:
        return None
    return {
        "a": bond.a,
        "b": bond.b,
        "order": bond.order,
        "style": bond.style,
        "color": bond.color,
    }


def serialize_model_state(
    model: MoleculeModel,
    explicit_label_atom_ids: Collection[int] = (),
) -> dict:
    explicit_ids = set(explicit_label_atom_ids)
    atoms = {
        atom_id: atom_to_state(
            atom,
            explicit_label=(atom.element.upper() == "C" and atom_id in explicit_ids),
        )
        for atom_id, atom in model.atoms.items()
    }
    bonds = [bond_to_state(bond) for bond in model.bonds]
    return {
        "atoms": atoms,
        "bonds": bonds,
        "next_atom_id": model.next_atom_id,
    }


def deserialize_model_state(model_state: Mapping[str, object]) -> MoleculeModel:
    atoms_state = model_state.get("atoms", {})
    bonds_state = model_state.get("bonds", [])
    model = MoleculeModel()
    if isinstance(atoms_state, Mapping):
        model.atoms = {
            int(atom_id): Atom(
                element=_mapping_value(atom_data, "element", "C"),
                x=float(_mapping_value(atom_data, "x", 0.0)),
                y=float(_mapping_value(atom_data, "y", 0.0)),
                color=_mapping_value(atom_data, "color", "#000000"),
                explicit_label=bool(_mapping_value(atom_data, "explicit_label", False)),
            )
            for atom_id, atom_data in atoms_state.items()
            if isinstance(atom_data, Mapping)
        }
    bonds: list[Bond | None] = []
    if isinstance(bonds_state, list):
        for bond_data in bonds_state:
            if bond_data is None:
                bonds.append(None)
                continue
            if not isinstance(bond_data, Mapping):
                continue
            bonds.append(
                Bond(
                    a=int(_mapping_value(bond_data, "a", 0)),
                    b=int(_mapping_value(bond_data, "b", 0)),
                    order=int(_mapping_value(bond_data, "order", 1)),
                    style=_mapping_value(bond_data, "style", "single"),
                    color=_mapping_value(bond_data, "color", "#000000"),
                )
            )
    model.bonds = bonds
    minimum_next_atom_id = max(model.atoms, default=-1) + 1
    parsed_next_atom_id = int(model_state.get("next_atom_id", minimum_next_atom_id))
    model.next_atom_id = max(parsed_next_atom_id, minimum_next_atom_id)
    return model


def serialize_settings(
    *,
    bond_length_px: float,
    arrow_line_width: float,
    arrow_head_scale: float,
    orbital_phase_enabled: bool,
    text_font_size: int,
    text_font_weight: int,
    text_italic: bool,
    sheet_size: str,
    sheet_orientation: str,
) -> dict:
    return {
        "bond_length_px": bond_length_px,
        "arrow_line_width": arrow_line_width,
        "arrow_head_scale": arrow_head_scale,
        "orbital_phase_enabled": orbital_phase_enabled,
        "text_font_size": text_font_size,
        "text_font_weight": text_font_weight,
        "text_italic": text_italic,
        "sheet_size": sheet_size,
        "sheet_orientation": sheet_orientation,
    }


def build_document_payload(state: dict, version: int) -> dict:
    _validate_document_state(state, version)
    return {
        "type": CHEMVAS_FILE_TYPE,
        "version": version,
        "state": state,
    }


def extract_document_state(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid Chemvas file.")
    if any(key in payload for key in ("type", "version", "state")):
        return _extract_wrapped_document_state(payload)
    _validate_bare_document_state(payload)
    return payload


def _extract_wrapped_document_state(payload: Mapping[str, object]) -> dict:
    if payload.get("type") not in SUPPORTED_FILE_TYPES:
        raise ValueError("Invalid Chemvas file.")
    version = payload.get("version")
    if type(version) is not int or version not in SUPPORTED_FILE_VERSIONS:
        raise ValueError("Invalid Chemvas file.")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("Invalid Chemvas file.")
    _validate_document_state(state, version)
    return state


def _validate_bare_document_state(state: Mapping[str, object]) -> None:
    state_kind = _state_kind(state)
    if state_kind is None:
        raise ValueError("Invalid Chemvas file.")
    if state_kind == "single_sheet":
        _validate_single_sheet_state(state)
    else:
        _validate_workbook_state(state)


def _validate_document_state(state: Mapping[str, object], version: int) -> None:
    if type(version) is not int or version not in SUPPORTED_FILE_VERSIONS:
        raise ValueError("Invalid Chemvas file.")
    state_kind = _state_kind(state)
    expected_kind = (
        "single_sheet"
        if version == SINGLE_SHEET_FILE_VERSION
        else "workbook"
    )
    if state_kind != expected_kind:
        raise ValueError("Invalid Chemvas file.")
    if state_kind == "single_sheet":
        _validate_single_sheet_state(state)
    else:
        _validate_workbook_state(state)


def _state_kind(state: Mapping[str, object]) -> str | None:
    model_state = state.get("model")
    if isinstance(model_state, Mapping):
        return "single_sheet"
    sheets_state = state.get("sheets")
    if isinstance(sheets_state, list):
        return "workbook"
    return None


def _validate_single_sheet_state(state: Mapping[str, object]) -> None:
    model_state = state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    _validate_model_state(model_state)


def _validate_workbook_state(state: Mapping[str, object]) -> None:
    sheets_state = state.get("sheets")
    if not isinstance(sheets_state, list):
        raise ValueError("Invalid Chemvas file.")
    active_sheet_index = state.get("active_sheet_index", 0)
    if not _is_int(active_sheet_index) or active_sheet_index < 0:
        raise ValueError("Invalid Chemvas file.")
    if sheets_state and active_sheet_index >= len(sheets_state):
        raise ValueError("Invalid Chemvas file.")
    for sheet_state in sheets_state:
        if not isinstance(sheet_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        sheet_kind = sheet_state.get("kind", "canvas")
        if sheet_kind != "canvas":
            continue
        content = sheet_state.get("content")
        if not isinstance(content, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_single_sheet_state(content)


def _validate_model_state(model_state: Mapping[str, object]) -> None:
    atoms_state = model_state.get("atoms")
    bonds_state = model_state.get("bonds")
    if not isinstance(atoms_state, Mapping) or not isinstance(bonds_state, list):
        raise ValueError("Invalid Chemvas file.")

    atom_ids: set[int] = set()
    for atom_id_value, atom_state in atoms_state.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id in atom_ids or not isinstance(atom_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_atom_state(atom_state)
        atom_ids.add(atom_id)

    next_atom_id = model_state.get("next_atom_id", max(atom_ids, default=-1) + 1)
    if not _is_int(next_atom_id) or next_atom_id < max(atom_ids, default=-1) + 1:
        raise ValueError("Invalid Chemvas file.")

    for bond_state in bonds_state:
        if bond_state is None:
            continue
        if not isinstance(bond_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_bond_state(bond_state, atom_ids)


def _validate_atom_state(atom_state: Mapping[str, object]) -> None:
    element = atom_state.get("element", "C")
    if not isinstance(element, str) or not element.strip():
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(atom_state.get("x", 0.0)) or not _is_number(atom_state.get("y", 0.0)):
        raise ValueError("Invalid Chemvas file.")
    color = atom_state.get("color", "#000000")
    if not _is_hex_color(color):
        raise ValueError("Invalid Chemvas file.")
    explicit_label = atom_state.get("explicit_label", False)
    if type(explicit_label) is not bool:
        raise ValueError("Invalid Chemvas file.")


def _validate_bond_state(bond_state: Mapping[str, object], atom_ids: set[int]) -> None:
    a = _validated_id(bond_state.get("a"))
    b = _validated_id(bond_state.get("b"))
    if a not in atom_ids or b not in atom_ids:
        raise ValueError("Invalid Chemvas file.")
    order = bond_state.get("order", 1)
    if not _is_int(order) or order not in VALID_BOND_ORDERS:
        raise ValueError("Invalid Chemvas file.")
    style = bond_state.get("style", "single")
    if not isinstance(style, str) or style not in VALID_BOND_STYLES:
        raise ValueError("Invalid Chemvas file.")
    color = bond_state.get("color", "#000000")
    if not _is_hex_color(color):
        raise ValueError("Invalid Chemvas file.")


def _validated_id(value: object) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        parsed = int(value)
    else:
        raise ValueError("Invalid Chemvas file.")
    if parsed < 0:
        raise ValueError("Invalid Chemvas file.")
    return parsed


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _is_hex_color(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("#"):
        return False
    digits = value[1:]
    if len(digits) not in (3, 6):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in digits)


def _mapping_value(mapping: object, key: str, default):
    if not isinstance(mapping, Mapping):
        return default
    value = mapping.get(key, default)
    return default if value is None else value
