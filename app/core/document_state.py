from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from typing import Any, TypeGuard, cast

from core.model import Atom, Bond, MoleculeModel

CHEMVAS_FILE_TYPE = "chemvas"
SINGLE_SHEET_FILE_VERSION = 1
WORKBOOK_FILE_VERSION = 2
SUPPORTED_FILE_VERSIONS = frozenset((SINGLE_SHEET_FILE_VERSION, WORKBOOK_FILE_VERSION))
SINGLE_SHEET_STATE_KEYS = frozenset(
    (
        "model",
        "ring_fills",
        "notes",
        "marks",
        "arrows",
        "ts_brackets",
        "orbitals",
        "settings",
        "last_smiles_input",
    )
)
SETTINGS_KEYS = frozenset(
    (
        "bond_length_px",
        "arrow_line_width",
        "arrow_head_scale",
        "orbital_phase_enabled",
        "text_font_size",
        "text_font_weight",
        "text_italic",
        "sheet_size",
        "sheet_orientation",
    )
)
# Legacy keys accepted for files written while journal presets existed. New
# saves do not emit these keys.
OPTIONAL_SETTINGS_KEYS = frozenset(("style_preset",))
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
VALID_ARROW_KINDS = frozenset(
    (
        "arrow",
        "equilibrium",
        "resonance",
        "curved_single",
        "curved_double",
        "inhibit",
        "dotted",
    )
)
VALID_MARK_KINDS = frozenset(("plus", "minus", "circled_plus", "circled_minus", "radical"))
VALID_TS_BRACKET_KINDS = frozenset(
    (
        "square_pair",
        "square_pair_double_dagger",
        "parentheses_pair",
        "braces_pair",
        "double_dagger",
        "square_left",
        "parenthesis_left",
        "brace_left",
        "dagger",
    )
)
VALID_ORBITAL_KINDS = frozenset(
    ("s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding")
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
    atoms_state = cast(Mapping[object, Mapping[str, object]], model_state["atoms"])
    bonds_state = cast(list[Mapping[str, object] | None], model_state["bonds"])
    model = MoleculeModel()
    model.atoms = {
        int(cast(Any, atom_id)): Atom(
            element=cast(str, atom_data["element"]),
            x=float(cast(Any, atom_data["x"])),
            y=float(cast(Any, atom_data["y"])),
            color=cast(str, atom_data["color"]),
            explicit_label=cast(bool, atom_data["explicit_label"]),
        )
        for atom_id, atom_data in atoms_state.items()
    }
    bonds: list[Bond | None] = []
    for bond_data in bonds_state:
        if bond_data is None:
            bonds.append(None)
            continue
        bonds.append(
            Bond(
                a=int(cast(Any, bond_data["a"])),
                b=int(cast(Any, bond_data["b"])),
                order=int(cast(Any, bond_data["order"])),
                style=cast(str, bond_data["style"]),
                color=cast(str, bond_data["color"]),
            )
        )
    model.bonds = bonds
    model.next_atom_id = int(cast(Any, model_state["next_atom_id"]))
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
    return _extract_wrapped_document_state(payload)


def _extract_wrapped_document_state(payload: Mapping[str, object]) -> dict:
    if payload.get("type") != CHEMVAS_FILE_TYPE:
        raise ValueError("Invalid Chemvas file.")
    version = payload.get("version")
    if type(version) is not int or version not in SUPPORTED_FILE_VERSIONS:
        raise ValueError("Invalid Chemvas file.")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("Invalid Chemvas file.")
    _validate_document_state(state, version)
    return state


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
    if set(state) != SINGLE_SHEET_STATE_KEYS:
        raise ValueError("Invalid Chemvas file.")
    model_state = state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    atom_ids = _validate_model_state(model_state)
    _validate_ring_fill_states(state.get("ring_fills"), atom_ids)
    _validate_note_states(state.get("notes"))
    _validate_mark_states(state.get("marks"), atom_ids)
    _validate_arrow_states(state.get("arrows"))
    _validate_ts_bracket_states(state.get("ts_brackets"))
    _validate_orbital_states(state.get("orbitals"))
    settings = state.get("settings")
    if not isinstance(settings, Mapping):
        raise ValueError("Invalid Chemvas file.")
    _validate_settings_state(settings)
    last_smiles_input = state.get("last_smiles_input")
    if last_smiles_input is not None and not isinstance(last_smiles_input, str):
        raise ValueError("Invalid Chemvas file.")


def _validate_workbook_state(state: Mapping[str, object]) -> None:
    if set(state) != {"active_sheet_index", "sheets"}:
        raise ValueError("Invalid Chemvas file.")
    sheets_state = state.get("sheets")
    if not isinstance(sheets_state, list) or not sheets_state:
        raise ValueError("Invalid Chemvas file.")
    active_sheet_index = state.get("active_sheet_index")
    if not _is_int(active_sheet_index) or active_sheet_index < 0:
        raise ValueError("Invalid Chemvas file.")
    if active_sheet_index >= len(sheets_state):
        raise ValueError("Invalid Chemvas file.")
    for sheet_state in sheets_state:
        if not isinstance(sheet_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        if set(sheet_state) != {"name", "kind", "content"}:
            raise ValueError("Invalid Chemvas file.")
        name = sheet_state.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Invalid Chemvas file.")
        sheet_kind = sheet_state.get("kind")
        if sheet_kind != "canvas":
            raise ValueError("Invalid Chemvas file.")
        content = sheet_state.get("content")
        if not isinstance(content, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_single_sheet_state(content)


def _validate_model_state(model_state: Mapping[str, object]) -> set[int]:
    atoms_state = model_state.get("atoms")
    bonds_state = model_state.get("bonds")
    if set(model_state) != {"atoms", "bonds", "next_atom_id"}:
        raise ValueError("Invalid Chemvas file.")
    if not isinstance(atoms_state, Mapping) or not isinstance(bonds_state, list):
        raise ValueError("Invalid Chemvas file.")

    atom_ids: set[int] = set()
    for atom_id_value, atom_state in atoms_state.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id in atom_ids or not isinstance(atom_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_atom_state(atom_state)
        atom_ids.add(atom_id)

    next_atom_id = model_state.get("next_atom_id")
    if not _is_int(next_atom_id) or next_atom_id < max(atom_ids, default=-1) + 1:
        raise ValueError("Invalid Chemvas file.")

    for bond_state in bonds_state:
        if bond_state is None:
            continue
        if not isinstance(bond_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_bond_state(bond_state, atom_ids)
    return atom_ids


def _validate_atom_state(atom_state: Mapping[str, object]) -> None:
    if set(atom_state) != {"element", "x", "y", "color", "explicit_label"}:
        raise ValueError("Invalid Chemvas file.")
    element = atom_state.get("element")
    if not isinstance(element, str) or not element.strip():
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(atom_state.get("x")) or not _is_number(atom_state.get("y")):
        raise ValueError("Invalid Chemvas file.")
    color = atom_state.get("color")
    if not _is_hex_color(color):
        raise ValueError("Invalid Chemvas file.")
    explicit_label = atom_state.get("explicit_label")
    if type(explicit_label) is not bool:
        raise ValueError("Invalid Chemvas file.")


def _validate_bond_state(bond_state: Mapping[str, object], atom_ids: set[int]) -> None:
    if set(bond_state) != {"a", "b", "order", "style", "color"}:
        raise ValueError("Invalid Chemvas file.")
    a = _validated_id(bond_state.get("a"))
    b = _validated_id(bond_state.get("b"))
    if a not in atom_ids or b not in atom_ids:
        raise ValueError("Invalid Chemvas file.")
    if a == b:
        raise ValueError("Invalid Chemvas file.")
    order = bond_state.get("order")
    if not _is_int(order) or order not in VALID_BOND_ORDERS:
        raise ValueError("Invalid Chemvas file.")
    style = bond_state.get("style")
    if not isinstance(style, str) or style not in VALID_BOND_STYLES:
        raise ValueError("Invalid Chemvas file.")
    color = bond_state.get("color")
    if not _is_hex_color(color):
        raise ValueError("Invalid Chemvas file.")


def _validate_ring_fill_states(states: object, atom_ids: set[int]) -> None:
    for ring_state in _validated_scene_state_list(states):
        if set(ring_state) != {"points", "atom_ids", "color", "alpha"}:
            raise ValueError("Invalid Chemvas file.")
        points = ring_state.get("points")
        if not isinstance(points, (list, tuple)) or any(not _is_point(point) for point in points):
            raise ValueError("Invalid Chemvas file.")
        ring_atom_ids = ring_state.get("atom_ids")
        if ring_atom_ids is not None and not _is_atom_id_sequence(ring_atom_ids, atom_ids):
            raise ValueError("Invalid Chemvas file.")
        color = ring_state.get("color")
        if color is not None and not _is_hex_color(color):
            raise ValueError("Invalid Chemvas file.")
        if not _is_number(ring_state.get("alpha")):
            raise ValueError("Invalid Chemvas file.")


def _validate_note_states(states: object) -> None:
    for note_state in _validated_scene_state_list(states):
        if set(note_state) != {"text", "x", "y"}:
            raise ValueError("Invalid Chemvas file.")
        if not isinstance(note_state.get("text"), str):
            raise ValueError("Invalid Chemvas file.")
        if not _is_number(note_state.get("x")) or not _is_number(note_state.get("y")):
            raise ValueError("Invalid Chemvas file.")


def _validate_mark_states(states: object, atom_ids: set[int]) -> None:
    for mark_state in _validated_scene_state_list(states):
        if set(mark_state) != {"kind", "text", "atom_id", "dx", "dy", "x", "y"}:
            raise ValueError("Invalid Chemvas file.")
        if mark_state.get("kind") not in VALID_MARK_KINDS:
            raise ValueError("Invalid Chemvas file.")
        text = mark_state.get("text")
        if text is not None and not isinstance(text, str):
            raise ValueError("Invalid Chemvas file.")
        if not _is_number(mark_state.get("x")) or not _is_number(mark_state.get("y")):
            raise ValueError("Invalid Chemvas file.")
        atom_id = mark_state.get("atom_id")
        if atom_id is None:
            if mark_state.get("dx") is not None or mark_state.get("dy") is not None:
                raise ValueError("Invalid Chemvas file.")
            continue
        parsed_atom_id = _validated_id(atom_id)
        if parsed_atom_id not in atom_ids:
            raise ValueError("Invalid Chemvas file.")
        dx = mark_state.get("dx")
        dy = mark_state.get("dy")
        if (dx is None and dy is None) or (_is_number(dx) and _is_number(dy)):
            continue
        raise ValueError("Invalid Chemvas file.")


def _validate_arrow_states(states: object) -> None:
    required_keys = {"kind", "start", "end"}
    allowed_keys = required_keys | {"control", "double"}
    for arrow_state in _validated_scene_state_list(states):
        keys = set(arrow_state)
        if not required_keys <= keys or not keys <= allowed_keys:
            raise ValueError("Invalid Chemvas file.")
        if arrow_state.get("kind") not in VALID_ARROW_KINDS:
            raise ValueError("Invalid Chemvas file.")
        if not _is_point(arrow_state.get("start")) or not _is_point(arrow_state.get("end")):
            raise ValueError("Invalid Chemvas file.")
        control = arrow_state.get("control")
        if control is not None and not _is_point(control):
            raise ValueError("Invalid Chemvas file.")
        double = arrow_state.get("double")
        if double is not None and type(double) is not bool:
            raise ValueError("Invalid Chemvas file.")


def _validate_ts_bracket_states(states: object) -> None:
    for ts_bracket_state in _validated_scene_state_list(states):
        keys = set(ts_bracket_state)
        if ts_bracket_state.get("kind") != "ts_bracket":
            raise ValueError("Invalid Chemvas file.")
        bracket_kind = ts_bracket_state.get("bracket_kind")
        if bracket_kind is not None and bracket_kind not in VALID_TS_BRACKET_KINDS:
            raise ValueError("Invalid Chemvas file.")
        if keys in ({"kind", "rect"}, {"kind", "rect", "bracket_kind"}):
            rect = ts_bracket_state.get("rect")
            if not isinstance(rect, (list, tuple)) or len(rect) != 4 or any(not _is_number(value) for value in rect):
                raise ValueError("Invalid Chemvas file.")
            continue
        if keys not in (
            {"kind", "left", "top", "right", "bottom"},
            {"kind", "left", "top", "right", "bottom", "bracket_kind"},
        ):
            raise ValueError("Invalid Chemvas file.")
        for key in ("left", "top", "right", "bottom"):
            if not _is_number(ts_bracket_state.get(key)):
                raise ValueError("Invalid Chemvas file.")


def _validate_orbital_states(states: object) -> None:
    for orbital_state in _validated_scene_state_list(states):
        if set(orbital_state) != {"kind", "center", "scale", "rotation"}:
            raise ValueError("Invalid Chemvas file.")
        if orbital_state.get("kind") not in VALID_ORBITAL_KINDS:
            raise ValueError("Invalid Chemvas file.")
        if not _is_point(orbital_state.get("center")):
            raise ValueError("Invalid Chemvas file.")
        if not _is_number(orbital_state.get("scale")) or not _is_number(orbital_state.get("rotation")):
            raise ValueError("Invalid Chemvas file.")


def _validated_scene_state_list(states: object) -> list[Mapping[str, object]]:
    if not isinstance(states, list):
        raise ValueError("Invalid Chemvas file.")
    validated: list[Mapping[str, object]] = []
    for state in states:
        if not isinstance(state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        validated.append(state)
    return validated


def _validate_settings_state(settings: Mapping[str, object]) -> None:
    keys = set(settings)
    # Required keys must all be present; only known optional keys may be added.
    if not SETTINGS_KEYS <= keys or not keys <= (SETTINGS_KEYS | OPTIONAL_SETTINGS_KEYS):
        raise ValueError("Invalid Chemvas file.")
    style_preset = settings.get("style_preset")
    if style_preset is not None and not isinstance(style_preset, str):
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(settings.get("bond_length_px")):
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(settings.get("arrow_line_width")):
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(settings.get("arrow_head_scale")):
        raise ValueError("Invalid Chemvas file.")
    if type(settings.get("orbital_phase_enabled")) is not bool:
        raise ValueError("Invalid Chemvas file.")
    if not _is_int(settings.get("text_font_size")):
        raise ValueError("Invalid Chemvas file.")
    if not _is_int(settings.get("text_font_weight")):
        raise ValueError("Invalid Chemvas file.")
    if type(settings.get("text_italic")) is not bool:
        raise ValueError("Invalid Chemvas file.")
    if not isinstance(settings.get("sheet_size"), str) or not settings.get("sheet_size"):
        raise ValueError("Invalid Chemvas file.")
    if not isinstance(settings.get("sheet_orientation"), str) or not settings.get("sheet_orientation"):
        raise ValueError("Invalid Chemvas file.")


def validate_clipboard_selection_payload(payload: Mapping[str, object]) -> bool:
    """Whitelist-validate a decoded clipboard selection payload.

    Clipboard MIME data sits outside the application's trust boundary (any other
    app or script can inject it), so paste input is held to the same standard as
    ``.chemvas`` file loading. ``format``/``version`` are checked by the decoder;
    this verifies the structural content. Returns ``True`` only when every
    section is well-formed, otherwise ``False`` so the caller can reject the
    whole paste rather than build invalid scene state.
    """
    try:
        atom_ids = _validate_clipboard_atoms(payload.get("atoms"))
        _validate_clipboard_bonds(payload.get("bonds"), atom_ids)
        for ring_state in _validated_scene_state_list(payload.get("rings", [])):
            _validate_clipboard_ring(ring_state, atom_ids)
        for mark_state in _validated_scene_state_list(payload.get("marks", [])):
            _validate_clipboard_mark(mark_state)
        for item_state in _validated_scene_state_list(payload.get("scene_items", [])):
            _validate_clipboard_scene_item(item_state)
    except ValueError:
        return False
    return True


def _validate_clipboard_atoms(atoms: object) -> set[int]:
    if not isinstance(atoms, list):
        raise ValueError("Invalid clipboard payload.")
    atom_ids: set[int] = set()
    for atom_state in atoms:
        if not isinstance(atom_state, Mapping):
            raise ValueError("Invalid clipboard payload.")
        if set(atom_state) != {"id", "element", "x", "y", "color", "explicit_label"}:
            raise ValueError("Invalid clipboard payload.")
        atom_id = _validated_id(atom_state.get("id"))
        if atom_id in atom_ids:
            raise ValueError("Invalid clipboard payload.")
        element = atom_state.get("element")
        if not isinstance(element, str) or not element.strip():
            raise ValueError("Invalid clipboard payload.")
        if not _is_number(atom_state.get("x")) or not _is_number(atom_state.get("y")):
            raise ValueError("Invalid clipboard payload.")
        if not _is_hex_color(atom_state.get("color")):
            raise ValueError("Invalid clipboard payload.")
        if type(atom_state.get("explicit_label")) is not bool:
            raise ValueError("Invalid clipboard payload.")
        atom_ids.add(atom_id)
    return atom_ids


def _validate_clipboard_bonds(bonds: object, atom_ids: set[int]) -> None:
    if not isinstance(bonds, list):
        raise ValueError("Invalid clipboard payload.")
    for bond_state in bonds:
        if not isinstance(bond_state, Mapping):
            raise ValueError("Invalid clipboard payload.")
        if set(bond_state) != {"a", "b", "order", "style", "color"}:
            raise ValueError("Invalid clipboard payload.")
        a = _validated_id(bond_state.get("a"))
        b = _validated_id(bond_state.get("b"))
        if a == b or a not in atom_ids or b not in atom_ids:
            raise ValueError("Invalid clipboard payload.")
        order = bond_state.get("order")
        if not _is_int(order) or order not in VALID_BOND_ORDERS:
            raise ValueError("Invalid clipboard payload.")
        if bond_state.get("style") not in VALID_BOND_STYLES:
            raise ValueError("Invalid clipboard payload.")
        if not _is_hex_color(bond_state.get("color")):
            raise ValueError("Invalid clipboard payload.")


def _validate_clipboard_ring(ring_state: Mapping[str, object], atom_ids: set[int]) -> None:
    if ring_state.get("kind") != "ring":
        raise ValueError("Invalid clipboard payload.")
    if set(ring_state) != {"kind", "points", "atom_ids", "color", "alpha"}:
        raise ValueError("Invalid clipboard payload.")
    points = ring_state.get("points")
    if not isinstance(points, (list, tuple)) or any(not _is_point(point) for point in points):
        raise ValueError("Invalid clipboard payload.")
    ring_atom_ids = ring_state.get("atom_ids")
    if not isinstance(ring_atom_ids, (list, tuple)) or not ring_atom_ids:
        raise ValueError("Invalid clipboard payload.")
    if not _is_atom_id_sequence(ring_atom_ids, atom_ids):
        raise ValueError("Invalid clipboard payload.")
    color = ring_state.get("color")
    if color is not None and not _is_hex_color(color):
        raise ValueError("Invalid clipboard payload.")
    if not _is_number(ring_state.get("alpha")):
        raise ValueError("Invalid clipboard payload.")


def _validate_clipboard_mark(mark_state: Mapping[str, object]) -> None:
    if mark_state.get("kind") != "mark":
        raise ValueError("Invalid clipboard payload.")
    if set(mark_state) != {"kind", "mark_kind", "text", "atom_id", "dx", "dy", "x", "y"}:
        raise ValueError("Invalid clipboard payload.")
    mark_kind = mark_state.get("mark_kind")
    if mark_kind is not None and mark_kind not in VALID_MARK_KINDS:
        raise ValueError("Invalid clipboard payload.")
    text = mark_state.get("text")
    if text is not None and not isinstance(text, str):
        raise ValueError("Invalid clipboard payload.")
    if not _is_number(mark_state.get("x")) or not _is_number(mark_state.get("y")):
        raise ValueError("Invalid clipboard payload.")
    atom_id = mark_state.get("atom_id")
    if atom_id is not None and type(atom_id) is not int:
        raise ValueError("Invalid clipboard payload.")
    for offset_key in ("dx", "dy"):
        offset = mark_state.get(offset_key)
        if offset is not None and not _is_number(offset):
            raise ValueError("Invalid clipboard payload.")


def _validate_clipboard_scene_item(item_state: Mapping[str, object]) -> None:
    kind = item_state.get("kind")
    if kind == "note":
        if not isinstance(item_state.get("text"), str):
            raise ValueError("Invalid clipboard payload.")
        if not _is_number(item_state.get("x")) or not _is_number(item_state.get("y")):
            raise ValueError("Invalid clipboard payload.")
        return
    if kind in VALID_ARROW_KINDS:
        if not _is_point(item_state.get("start")) or not _is_point(item_state.get("end")):
            raise ValueError("Invalid clipboard payload.")
        control = item_state.get("control")
        if control is not None and not _is_point(control):
            raise ValueError("Invalid clipboard payload.")
        return
    if kind == "ts_bracket":
        bracket_kind = item_state.get("bracket_kind")
        if bracket_kind is not None and bracket_kind not in VALID_TS_BRACKET_KINDS:
            raise ValueError("Invalid clipboard payload.")
        rect = item_state.get("rect")
        if rect is not None:
            if not isinstance(rect, (list, tuple)) or len(rect) != 4 or any(not _is_number(v) for v in rect):
                raise ValueError("Invalid clipboard payload.")
            return
        for edge_key in ("left", "top", "right", "bottom"):
            if not _is_number(item_state.get(edge_key)):
                raise ValueError("Invalid clipboard payload.")
        return
    if kind == "orbital":
        if item_state.get("orbital_kind") not in VALID_ORBITAL_KINDS:
            raise ValueError("Invalid clipboard payload.")
        if not _is_point(item_state.get("center")):
            raise ValueError("Invalid clipboard payload.")
        if not _is_number(item_state.get("scale")) or not _is_number(item_state.get("rotation")):
            raise ValueError("Invalid clipboard payload.")
        return
    raise ValueError("Invalid clipboard payload.")


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


def _is_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _is_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    return math.isfinite(cast(float, value))


def _is_point(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    x, y = value
    return _is_number(x) and _is_number(y)


def _is_atom_id_sequence(value: object, atom_ids: set[int]) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    try:
        parsed_ids = [_validated_id(atom_id) for atom_id in value]
    except ValueError:
        return False
    return all(atom_id in atom_ids for atom_id in parsed_ids)


def _is_hex_color(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("#"):
        return False
    digits = value[1:]
    if len(digits) not in (3, 6):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in digits)
