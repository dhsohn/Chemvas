from __future__ import annotations

import math
from collections.abc import Callable, Collection, Mapping
from decimal import Decimal
from typing import Any, TypeGuard, cast

from core.model import Atom, Bond, MoleculeModel

CHEMVAS_FILE_TYPE = "chemvas"
CANVAS_FILE_VERSION = 3
PERSPECTIVE_CANVAS_FILE_VERSION = 2
LEGACY_CANVAS_FILE_VERSION = 1
SUPPORTED_FILE_VERSIONS = frozenset(
    (
        LEGACY_CANVAS_FILE_VERSION,
        PERSPECTIVE_CANVAS_FILE_VERSION,
        CANVAS_FILE_VERSION,
    )
)
# Optional keys preserve compatibility with v1 files written before each feature
# existed; everything else must be present and no unknown keys are allowed.
_OPTIONAL_CANVAS_STATE_KEYS = frozenset(("shapes",))
_V2_OPTIONAL_CANVAS_STATE_KEYS = frozenset(("perspective",))
_V3_OPTIONAL_CANVAS_STATE_KEYS = frozenset(("groups",))
CANVAS_STATE_KEYS = frozenset(
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
) | _OPTIONAL_CANVAS_STATE_KEYS
CANVAS_STATE_KEYS_BY_VERSION = {
    LEGACY_CANVAS_FILE_VERSION: CANVAS_STATE_KEYS,
    PERSPECTIVE_CANVAS_FILE_VERSION: CANVAS_STATE_KEYS | _V2_OPTIONAL_CANVAS_STATE_KEYS,
    CANVAS_FILE_VERSION: (
        CANVAS_STATE_KEYS | _V2_OPTIONAL_CANVAS_STATE_KEYS | _V3_OPTIONAL_CANVAS_STATE_KEYS
    ),
}
_GROUPABLE_STATE_ITEM_KEYS = frozenset(("notes", "marks", "arrows", "ts_brackets", "shapes", "orbitals"))
POINT_COORDINATE_TOLERANCE = Decimal("0.000001")
MAX_SAFE_NUMBER = float(2**53 - 1)
MAX_SAFE_NUMBER_DECIMAL = Decimal(2**53 - 1)
REQUIRED_SETTINGS_KEYS = frozenset(
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
OPTIONAL_SETTINGS_KEYS = frozenset(
    (
        "text_font_family",
        "text_color",
        "text_alignment",
        "text_line_spacing",
        "note_box_enabled",
        "note_box_color",
        "note_box_alpha",
        "note_border_enabled",
        "note_border_color",
        "note_border_width",
        "note_padding",
    )
)
SETTINGS_KEYS = REQUIRED_SETTINGS_KEYS | OPTIONAL_SETTINGS_KEYS
VALID_SHEET_SIZES = frozenset(("A4",))
VALID_SHEET_ORIENTATIONS = frozenset(("landscape", "portrait"))
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
VALID_SHAPE_KINDS = frozenset(("circle", "ellipse", "rounded_rect", "rect"))
VALID_SHAPE_STROKES = frozenset(("solid", "dashed", "dotted", "none"))
VALID_ATOM_ANNOTATION_KEYS = frozenset(("formal_charge", "radical_electrons"))
LEGACY_CLIPBOARD_SELECTION_VERSION = 1
CLIPBOARD_SELECTION_PERSPECTIVE_VERSION = 2
CLIPBOARD_SELECTION_PAYLOAD_KEYS = frozenset(
    ("format", "version", "atoms", "bonds", "rings", "marks", "scene_items", "perspective")
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
    """Serialize ``model`` into a canvas-state model dict.

    The output is normalized to satisfy document validation even when the
    in-memory model has drifted (duplicate bonds, dangling endpoints, invalid
    styles, non-finite coordinates). Saving must never fail because of an
    editing bug — the serializer heals what it can instead of letting
    ``build_document_payload`` reject the user's work.
    """
    explicit_ids = set(explicit_label_atom_ids)
    atoms = {
        atom_id: _normalized_atom_state(
            atom_to_state(
                atom,
                explicit_label=(atom.element.upper() == "C" and atom_id in explicit_ids),
            )
        )
        for atom_id, atom in model.atoms.items()
    }
    bonds: list[dict | None] = []
    seen_bond_pairs: set[tuple[int, int]] = set()
    for bond in model.bonds:
        bond_state = bond_to_state(bond)
        if bond_state is not None:
            a = cast(int, bond_state["a"])
            b = cast(int, bond_state["b"])
            if a == b or a not in atoms or b not in atoms or _bond_pair_key(a, b) in seen_bond_pairs:
                bond_state = None
            else:
                seen_bond_pairs.add(_bond_pair_key(a, b))
                bond_state = _normalized_bond_state(bond_state)
        bonds.append(bond_state)
    state = {
        "atoms": atoms,
        "bonds": bonds,
        "next_atom_id": max(int(model.next_atom_id), max(atoms, default=-1) + 1),
    }
    atom_annotations = _serialized_atom_annotations(getattr(model, "atom_annotations", {}), atoms.keys())
    if atom_annotations:
        state["atom_annotations"] = atom_annotations
    return state


def _normalized_atom_state(atom_state: dict) -> dict:
    element = atom_state.get("element")
    if not isinstance(element, str) or not element.strip():
        atom_state["element"] = "C"
    for key in ("x", "y"):
        value = atom_state.get(key)
        atom_state[key] = float(cast(Any, value)) if _is_number(value) else 0.0
    if not _is_hex_color(atom_state.get("color")):
        atom_state["color"] = "#000000"
    atom_state["explicit_label"] = bool(atom_state.get("explicit_label"))
    return atom_state


def _normalized_bond_state(bond_state: dict) -> dict:
    if bond_state.get("order") not in VALID_BOND_ORDERS:
        bond_state["order"] = 1
    if bond_state.get("style") not in VALID_BOND_STYLES:
        bond_state["style"] = "single"
    if bond_state["style"] in {"wedge", "hash"} and bond_state["order"] != 1:
        bond_state["order"] = 1
    if not _is_hex_color(bond_state.get("color")):
        bond_state["color"] = "#000000"
    return bond_state


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
    annotations_state = cast(Mapping[object, Mapping[str, object]], model_state.get("atom_annotations", {}))
    model.atom_annotations = {
        int(cast(Any, atom_id)): {
            cast(str, key): int(cast(Any, value))
            for key, value in annotation.items()
        }
        for atom_id, annotation in annotations_state.items()
    }
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
    text_font_family: str = "Arial",
    text_color: str = "#222222",
    text_alignment: str = "left",
    text_line_spacing: float = 1.0,
    note_box_enabled: bool = False,
    note_box_color: str = "#ffffff",
    note_box_alpha: float = 1.0,
    note_border_enabled: bool = False,
    note_border_color: str = "#333333",
    note_border_width: float = 1.0,
    note_padding: float = 6.0,
) -> dict:
    return {
        "bond_length_px": bond_length_px,
        "arrow_line_width": arrow_line_width,
        "arrow_head_scale": arrow_head_scale,
        "orbital_phase_enabled": orbital_phase_enabled,
        "text_font_family": text_font_family,
        "text_font_size": text_font_size,
        "text_font_weight": text_font_weight,
        "text_italic": text_italic,
        "text_color": text_color,
        "text_alignment": text_alignment,
        "text_line_spacing": text_line_spacing,
        "note_box_enabled": note_box_enabled,
        "note_box_color": note_box_color,
        "note_box_alpha": note_box_alpha,
        "note_border_enabled": note_border_enabled,
        "note_border_color": note_border_color,
        "note_border_width": note_border_width,
        "note_padding": note_padding,
        "sheet_size": sheet_size,
        "sheet_orientation": sheet_orientation,
    }


def selection_payload_to_canvas_state(
    selection_payload: Mapping[str, object],
    template_settings: Mapping[str, object],
) -> dict:
    """Convert a validated clipboard-style selection payload into a canvas state."""
    if not validate_clipboard_selection_payload(selection_payload):
        raise ValueError("Invalid clipboard payload.")

    atoms = cast(list[Mapping[str, object]], selection_payload.get("atoms", []))
    bonds = cast(list[Mapping[str, object]], selection_payload.get("bonds", []))
    rings = cast(list[Mapping[str, object]], selection_payload.get("rings", []))
    marks = cast(list[Mapping[str, object]], selection_payload.get("marks", []))
    scene_items = cast(list[Mapping[str, object]], selection_payload.get("scene_items", []))

    atom_states: dict[int, dict] = {}
    atom_annotations: dict[int, dict[str, int]] = {}
    for atom_state in atoms:
        atom_id = _validated_clipboard_id(atom_state.get("id"))
        atom_states[atom_id] = {
            "element": atom_state["element"],
            "x": atom_state["x"],
            "y": atom_state["y"],
            "color": atom_state["color"],
            "explicit_label": atom_state["explicit_label"],
        }
        annotation = _normalized_atom_annotation(cast(Mapping[str, object] | None, atom_state.get("annotation")))
        if annotation:
            atom_annotations[atom_id] = annotation

    ring_fills: list[dict] = []
    note_states: list[dict] = []
    arrow_states: list[dict] = []
    ts_bracket_states: list[dict] = []
    shape_states: list[dict] = []
    orbital_states: list[dict] = []

    for ring_state in rings:
        ring_fills.append(
            {
                "points": ring_state["points"],
                "atom_ids": ring_state["atom_ids"],
                "color": ring_state["color"],
                "alpha": ring_state["alpha"],
            }
        )

    mark_states = [
        {
            "kind": mark_state["mark_kind"] if isinstance(mark_state["mark_kind"], str) else "plus",
            "text": mark_state["text"],
            "atom_id": mark_state["atom_id"],
            "dx": mark_state["dx"],
            "dy": mark_state["dy"],
            "x": mark_state["x"],
            "y": mark_state["y"],
        }
        for mark_state in marks
    ]

    for item_state in scene_items:
        kind = item_state.get("kind")
        if kind == "note":
            note_state = {
                "text": item_state["text"],
                "x": item_state["x"],
                "y": item_state["y"],
            }
            html = item_state.get("html")
            if isinstance(html, str):
                note_state["html"] = html
            note_states.append(note_state)
        elif kind in VALID_ARROW_KINDS:
            arrow_states.append(dict(item_state))
        elif kind == "ts_bracket":
            ts_bracket_states.append(dict(item_state))
        elif kind == "shape":
            shape_states.append(dict(item_state))
        elif kind == "orbital":
            orbital_states.append(
                {
                    "kind": item_state["orbital_kind"],
                    "center": item_state["center"],
                    "scale": item_state["scale"],
                    "rotation": item_state["rotation"],
                }
            )

    model_state = {
        "atoms": atom_states,
        "bonds": [dict(bond_state) for bond_state in bonds],
        "next_atom_id": max(atom_states, default=-1) + 1,
    }
    if atom_annotations:
        model_state["atom_annotations"] = atom_annotations

    state = {
        "model": model_state,
        "ring_fills": ring_fills,
        "notes": note_states,
        "marks": mark_states,
        "arrows": arrow_states,
        "ts_brackets": ts_bracket_states,
        "shapes": shape_states,
        "orbitals": orbital_states,
        "settings": dict(template_settings),
        "last_smiles_input": None,
    }
    perspective_state = _clipboard_perspective_to_canvas_state(selection_payload.get("perspective"))
    if perspective_state is not None:
        state["perspective"] = perspective_state
    _validate_canvas_state(state, version=CANVAS_FILE_VERSION)
    return state


def _clipboard_perspective_to_canvas_state(perspective_state: object) -> dict | None:
    if not isinstance(perspective_state, Mapping):
        return None
    coords_entries = cast(list[Mapping[str, object]], perspective_state["atom_coords_3d"])
    coords_3d = {
        _validated_clipboard_id(entry["atom_id"]): (
            float(cast(Any, entry["coords"])[0]),
            float(cast(Any, entry["coords"])[1]),
            float(cast(Any, entry["coords"])[2]),
        )
        for entry in coords_entries
    }
    if not coords_3d:
        return None
    center = perspective_state.get("projection_center_3d")
    anchor = perspective_state.get("projection_anchor_2d")
    return {
        "atom_coords_3d": coords_3d,
        "projection_center_3d": tuple(float(value) for value in cast(Any, center)) if center is not None else None,
        "projection_anchor_2d": tuple(float(value) for value in cast(Any, anchor)) if anchor is not None else None,
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
    if state_kind != "canvas":
        raise ValueError("Invalid Chemvas file.")
    _validate_canvas_state(state, version=version)


def _state_kind(state: Mapping[str, object]) -> str | None:
    model_state = state.get("model")
    if isinstance(model_state, Mapping):
        return "canvas"
    return None


def _validate_canvas_state(state: Mapping[str, object], *, version: int) -> None:
    keys = set(state)
    allowed_keys = CANVAS_STATE_KEYS_BY_VERSION.get(version)
    if allowed_keys is None:
        raise ValueError("Invalid Chemvas file.")
    required = CANVAS_STATE_KEYS - _OPTIONAL_CANVAS_STATE_KEYS
    if not required <= keys or not keys <= allowed_keys:
        raise ValueError("Invalid Chemvas file.")
    model_state = state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    atom_ids, bond_pairs, atom_positions = _validate_model_state(model_state)
    _validate_ring_fill_states(state.get("ring_fills"), atom_ids, bond_pairs, atom_positions)
    _validate_note_states(state.get("notes"))
    _validate_mark_states(state.get("marks"), atom_ids)
    _validate_arrow_states(state.get("arrows"))
    _validate_ts_bracket_states(state.get("ts_brackets"))
    _validate_shape_states(state.get("shapes"))
    _validate_orbital_states(state.get("orbitals"))
    _validate_perspective_state(state.get("perspective"), atom_ids)
    _validate_group_states(state, atom_ids)
    settings = state.get("settings")
    if not isinstance(settings, Mapping):
        raise ValueError("Invalid Chemvas file.")
    _validate_settings_state(settings)
    last_smiles_input = state.get("last_smiles_input")
    if last_smiles_input is not None and not isinstance(last_smiles_input, str):
        raise ValueError("Invalid Chemvas file.")


def _validate_model_state(
    model_state: Mapping[str, object],
) -> tuple[set[int], set[tuple[int, int]], dict[int, tuple[int | float | Decimal, int | float | Decimal]]]:
    atoms_state = model_state.get("atoms")
    bonds_state = model_state.get("bonds")
    required_keys = {"atoms", "bonds", "next_atom_id"}
    if not required_keys <= set(model_state) or not set(model_state) <= required_keys | {"atom_annotations"}:
        raise ValueError("Invalid Chemvas file.")
    if not isinstance(atoms_state, Mapping) or not isinstance(bonds_state, list):
        raise ValueError("Invalid Chemvas file.")

    atom_ids: set[int] = set()
    atom_positions: dict[int, tuple[int | float | Decimal, int | float | Decimal]] = {}
    for atom_id_value, atom_state in atoms_state.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id in atom_ids or not isinstance(atom_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        _validate_atom_state(atom_state)
        atom_ids.add(atom_id)
        atom_positions[atom_id] = (
            cast(int | float | Decimal, atom_state.get("x")),
            cast(int | float | Decimal, atom_state.get("y")),
        )

    next_atom_id = model_state.get("next_atom_id")
    if not _is_int(next_atom_id) or next_atom_id < max(atom_ids, default=-1) + 1:
        raise ValueError("Invalid Chemvas file.")

    bond_pairs: set[tuple[int, int]] = set()
    for bond_state in bonds_state:
        if bond_state is None:
            continue
        if not isinstance(bond_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        bond_pair = _validate_bond_state(bond_state, atom_ids)
        if bond_pair in bond_pairs:
            raise ValueError("Invalid Chemvas file.")
        bond_pairs.add(bond_pair)
    _validate_atom_annotations_state(model_state.get("atom_annotations", {}), atom_ids)
    return atom_ids, bond_pairs, atom_positions


# --- Shared field validators -------------------------------------------------
# The .chemvas file loader and the clipboard-paste loader enforce the same
# structural rules. Each rule lives exactly once below, parameterized by the
# per-boundary error message (and id validator, where the encodings differ),
# so the two trust boundaries cannot silently drift apart.


def _validate_atom_fields(atom_state: Mapping[str, object], *, error: str) -> None:
    element = atom_state.get("element")
    if not isinstance(element, str) or not element.strip():
        raise ValueError(error)
    if not _is_number(atom_state.get("x")) or not _is_number(atom_state.get("y")):
        raise ValueError(error)
    if not _is_hex_color(atom_state.get("color")):
        raise ValueError(error)
    if type(atom_state.get("explicit_label")) is not bool:
        raise ValueError(error)


def _validate_bond_fields(
    bond_state: Mapping[str, object],
    atom_ids: set[int],
    *,
    id_validator: Callable[[object], int],
    error: str,
) -> tuple[int, int]:
    if set(bond_state) != {"a", "b", "order", "style", "color"}:
        raise ValueError(error)
    a = id_validator(bond_state.get("a"))
    b = id_validator(bond_state.get("b"))
    if a == b or a not in atom_ids or b not in atom_ids:
        raise ValueError(error)
    order = bond_state.get("order")
    if not _is_int(order) or order not in VALID_BOND_ORDERS:
        raise ValueError(error)
    style = bond_state.get("style")
    if style not in VALID_BOND_STYLES:
        raise ValueError(error)
    if style in {"wedge", "hash"} and order != 1:
        raise ValueError(error)
    if not _is_hex_color(bond_state.get("color")):
        raise ValueError(error)
    return _bond_pair_key(a, b)


def _validate_note_fields(
    note_state: Mapping[str, object],
    *,
    required_keys: frozenset[str],
    error: str,
) -> None:
    keys = set(note_state)
    if not required_keys <= keys or not keys <= required_keys | {"html"}:
        raise ValueError(error)
    if not isinstance(note_state.get("text"), str):
        raise ValueError(error)
    if "html" in note_state and not isinstance(note_state.get("html"), str):
        raise ValueError(error)
    if not _is_number(note_state.get("x")) or not _is_number(note_state.get("y")):
        raise ValueError(error)


def _validate_arrow_fields(arrow_state: Mapping[str, object], *, error: str) -> None:
    keys = set(arrow_state)
    required_keys = {"kind", "start", "end"}
    if not required_keys <= keys or not keys <= required_keys | {"control", "double"}:
        raise ValueError(error)
    if arrow_state.get("kind") not in VALID_ARROW_KINDS:
        raise ValueError(error)
    if not _is_point(arrow_state.get("start")) or not _is_point(arrow_state.get("end")):
        raise ValueError(error)
    control = arrow_state.get("control")
    if control is not None and not _is_point(control):
        raise ValueError(error)
    double = arrow_state.get("double")
    if double is not None and type(double) is not bool:
        raise ValueError(error)


def _validate_ts_bracket_fields(ts_bracket_state: Mapping[str, object], *, error: str) -> None:
    keys = set(ts_bracket_state)
    if ts_bracket_state.get("kind") != "ts_bracket":
        raise ValueError(error)
    bracket_kind = ts_bracket_state.get("bracket_kind")
    if bracket_kind is not None and bracket_kind not in VALID_TS_BRACKET_KINDS:
        raise ValueError(error)
    if keys in ({"kind", "rect"}, {"kind", "rect", "bracket_kind"}):
        rect = ts_bracket_state.get("rect")
        if not isinstance(rect, (list, tuple)) or len(rect) != 4 or any(not _is_number(value) for value in rect):
            raise ValueError(error)
        return
    if keys not in (
        {"kind", "left", "top", "right", "bottom"},
        {"kind", "left", "top", "right", "bottom", "bracket_kind"},
    ):
        raise ValueError(error)
    for key in ("left", "top", "right", "bottom"):
        if not _is_number(ts_bracket_state.get(key)):
            raise ValueError(error)


def _validate_shape_fields(shape_state: Mapping[str, object], *, error: str) -> None:
    keys = set(shape_state)
    if not _SHAPE_STATE_BASE_KEYS <= keys or not keys <= _SHAPE_STATE_BASE_KEYS | {"fill", "fill_alpha"}:
        raise ValueError(error)
    if shape_state.get("kind") != "shape":
        raise ValueError(error)
    if shape_state.get("shape_kind") not in VALID_SHAPE_KINDS:
        raise ValueError(error)
    if shape_state.get("stroke_style") not in VALID_SHAPE_STROKES:
        raise ValueError(error)
    for key in ("left", "top", "right", "bottom"):
        if not _is_number(shape_state.get(key)):
            raise ValueError(error)
    if "fill" in keys and not _is_hex_color(shape_state.get("fill")):
        raise ValueError(error)
    if "fill_alpha" in keys and (
        not _is_number(shape_state.get("fill_alpha"))
        or not 0.0 <= cast(float, shape_state.get("fill_alpha")) <= 1.0
    ):
        raise ValueError(error)


def _validate_orbital_fields(
    orbital_state: Mapping[str, object],
    *,
    kind_key: str,
    required_keys: frozenset[str],
    error: str,
) -> None:
    if set(orbital_state) != required_keys:
        raise ValueError(error)
    if orbital_state.get(kind_key) not in VALID_ORBITAL_KINDS:
        raise ValueError(error)
    if not _is_point(orbital_state.get("center")):
        raise ValueError(error)
    if not _is_number(orbital_state.get("scale")) or not _is_number(orbital_state.get("rotation")):
        raise ValueError(error)


def _validate_ring_fields(
    ring_state: Mapping[str, object],
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
    atom_positions: Mapping[int, tuple[int | float | Decimal, int | float | Decimal]],
    *,
    required_keys: frozenset[str],
    clipboard: bool,
    error: str,
) -> None:
    if set(ring_state) != required_keys:
        raise ValueError(error)
    points = ring_state.get("points")
    if not isinstance(points, (list, tuple)) or len(points) < 3 or any(not _is_point(point) for point in points):
        raise ValueError(error)
    ring_atom_ids = ring_state.get("atom_ids")
    if not isinstance(ring_atom_ids, (list, tuple)) or len(ring_atom_ids) != len(points):
        raise ValueError(error)
    if not _is_atom_id_cycle(ring_atom_ids, atom_ids, bond_pairs, clipboard=clipboard):
        raise ValueError(error)
    if not _ring_points_match_atom_positions(points, ring_atom_ids, atom_positions, clipboard=clipboard):
        raise ValueError(error)
    color = ring_state.get("color")
    if color is not None and not _is_hex_color(color):
        raise ValueError(error)
    alpha = ring_state.get("alpha")
    if not _is_number(alpha) or not 0.0 <= cast(float, alpha) <= 1.0:
        raise ValueError(error)


# --- .chemvas file validation -------------------------------------------------


def _validate_atom_state(atom_state: Mapping[str, object]) -> None:
    if set(atom_state) != {"element", "x", "y", "color", "explicit_label"}:
        raise ValueError("Invalid Chemvas file.")
    _validate_atom_fields(atom_state, error="Invalid Chemvas file.")


def _validate_bond_state(bond_state: Mapping[str, object], atom_ids: set[int]) -> tuple[int, int]:
    return _validate_bond_fields(
        bond_state,
        atom_ids,
        id_validator=_validated_id,
        error="Invalid Chemvas file.",
    )


def _bond_pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def model_bond_pairs(model: MoleculeModel) -> set[tuple[int, int]]:
    """Normalized (low, high) atom-id pairs of the model's live bonds."""
    return {
        _bond_pair_key(bond.a, bond.b)
        for bond in model.bonds
        if bond is not None and bond.a != bond.b
    }


def ring_atom_ids_form_cycle(
    ring_atom_ids: Collection[int],
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
) -> bool:
    """Public wrapper of the ring-cycle rule used by document validation.

    Snapshot code uses this to drop ring fills that no longer describe a real
    bonded cycle, so a stale ring can never make saving fail validation.
    """
    return _is_atom_id_cycle(list(ring_atom_ids), atom_ids, bond_pairs)


def _validate_ring_fill_states(
    states: object,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
    atom_positions: Mapping[int, tuple[int | float | Decimal, int | float | Decimal]],
) -> None:
    for ring_state in _validated_scene_state_list(states):
        _validate_ring_fields(
            ring_state,
            atom_ids,
            bond_pairs,
            atom_positions,
            required_keys=frozenset(("points", "atom_ids", "color", "alpha")),
            clipboard=False,
            error="Invalid Chemvas file.",
        )


def _validate_note_states(states: object) -> None:
    for note_state in _validated_scene_state_list(states):
        _validate_note_fields(
            note_state,
            required_keys=frozenset(("text", "x", "y")),
            error="Invalid Chemvas file.",
        )


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
    for arrow_state in _validated_scene_state_list(states):
        _validate_arrow_fields(arrow_state, error="Invalid Chemvas file.")


def _validate_ts_bracket_states(states: object) -> None:
    for ts_bracket_state in _validated_scene_state_list(states):
        _validate_ts_bracket_fields(ts_bracket_state, error="Invalid Chemvas file.")


_SHAPE_STATE_BASE_KEYS = frozenset(
    ("kind", "left", "top", "right", "bottom", "shape_kind", "stroke_style")
)


def _validate_shape_states(states: object) -> None:
    if states is None:
        return
    for shape_state in _validated_scene_state_list(states):
        _validate_shape_fields(shape_state, error="Invalid Chemvas file.")


def _validate_orbital_states(states: object) -> None:
    for orbital_state in _validated_scene_state_list(states):
        _validate_orbital_fields(
            orbital_state,
            kind_key="kind",
            required_keys=frozenset(("kind", "center", "scale", "rotation")),
            error="Invalid Chemvas file.",
        )


def _validate_perspective_state(state: object, atom_ids: set[int]) -> None:
    if state is None:
        return
    if not isinstance(state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    if set(state) != {"atom_coords_3d", "projection_center_3d", "projection_anchor_2d"}:
        raise ValueError("Invalid Chemvas file.")
    atom_coords_3d = state.get("atom_coords_3d")
    if not isinstance(atom_coords_3d, Mapping):
        raise ValueError("Invalid Chemvas file.")
    for atom_id_value, coords in atom_coords_3d.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id not in atom_ids or not _is_point_3d(coords):
            raise ValueError("Invalid Chemvas file.")
    _validate_optional_point_3d(state.get("projection_center_3d"))
    _validate_optional_point_2d(state.get("projection_anchor_2d"))


def _validate_group_states(state: Mapping[str, object], atom_ids: set[int]) -> None:
    group_states = state.get("groups")
    if group_states is None:
        return
    if not isinstance(group_states, list):
        raise ValueError("Invalid Chemvas file.")
    item_counts: dict[str, int] = {}
    for key in _GROUPABLE_STATE_ITEM_KEYS:
        items = state.get(key)
        item_counts[key] = len(items) if isinstance(items, list) else 0
    seen_atom_ids: set[int] = set()
    seen_item_refs: set[tuple[str, int]] = set()
    for group_state in group_states:
        if not isinstance(group_state, Mapping) or set(group_state) != {"atoms", "items"}:
            raise ValueError("Invalid Chemvas file.")
        group_atoms = group_state.get("atoms")
        group_items = group_state.get("items")
        if not isinstance(group_atoms, list) or not isinstance(group_items, list):
            raise ValueError("Invalid Chemvas file.")
        if not group_atoms and not group_items:
            raise ValueError("Invalid Chemvas file.")
        for atom_id in group_atoms:
            if not _is_int(atom_id) or atom_id not in atom_ids or atom_id in seen_atom_ids:
                raise ValueError("Invalid Chemvas file.")
            seen_atom_ids.add(atom_id)
        for item_ref in group_items:
            if not isinstance(item_ref, (list, tuple)) or len(item_ref) != 2:
                raise ValueError("Invalid Chemvas file.")
            kind, index = item_ref
            if kind not in _GROUPABLE_STATE_ITEM_KEYS or not _is_int(index):
                raise ValueError("Invalid Chemvas file.")
            if not 0 <= index < item_counts[kind] or (kind, index) in seen_item_refs:
                raise ValueError("Invalid Chemvas file.")
            seen_item_refs.add((kind, index))


def _validate_optional_point_3d(value: object) -> None:
    if value is not None and not _is_point_3d(value):
        raise ValueError("Invalid Chemvas file.")


def _validate_optional_point_2d(value: object) -> None:
    if value is not None and not _is_point(value):
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
    if not REQUIRED_SETTINGS_KEYS <= keys or not keys <= SETTINGS_KEYS:
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(settings.get("bond_length_px")) or cast(float, settings.get("bond_length_px")) <= 0:
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(settings.get("arrow_line_width")) or cast(float, settings.get("arrow_line_width")) < 0.5:
        raise ValueError("Invalid Chemvas file.")
    if not _is_number(settings.get("arrow_head_scale")) or not 0.1 <= cast(float, settings.get("arrow_head_scale")) <= 0.8:
        raise ValueError("Invalid Chemvas file.")
    if type(settings.get("orbital_phase_enabled")) is not bool:
        raise ValueError("Invalid Chemvas file.")
    text_font_size = settings.get("text_font_size")
    if not _is_int(text_font_size) or text_font_size < 6:
        raise ValueError("Invalid Chemvas file.")
    if not _is_int(settings.get("text_font_weight")) or not 1 <= cast(int, settings.get("text_font_weight")) <= 1000:
        raise ValueError("Invalid Chemvas file.")
    if type(settings.get("text_italic")) is not bool:
        raise ValueError("Invalid Chemvas file.")
    if "text_font_family" in settings and (
        not isinstance(settings.get("text_font_family"), str) or not settings.get("text_font_family")
    ):
        raise ValueError("Invalid Chemvas file.")
    if "text_color" in settings and not _is_hex_color(settings.get("text_color")):
        raise ValueError("Invalid Chemvas file.")
    if "text_alignment" in settings and settings.get("text_alignment") not in {"left", "center", "right", "justify"}:
        raise ValueError("Invalid Chemvas file.")
    if "text_line_spacing" in settings and (
        not _is_number(settings.get("text_line_spacing")) or cast(float, settings.get("text_line_spacing")) < 0.8
    ):
        raise ValueError("Invalid Chemvas file.")
    if "note_box_enabled" in settings and type(settings.get("note_box_enabled")) is not bool:
        raise ValueError("Invalid Chemvas file.")
    if "note_box_color" in settings and not _is_hex_color(settings.get("note_box_color")):
        raise ValueError("Invalid Chemvas file.")
    if "note_box_alpha" in settings and (
        not _is_number(settings.get("note_box_alpha")) or not 0.0 <= cast(float, settings.get("note_box_alpha")) <= 1.0
    ):
        raise ValueError("Invalid Chemvas file.")
    if "note_border_enabled" in settings and type(settings.get("note_border_enabled")) is not bool:
        raise ValueError("Invalid Chemvas file.")
    if "note_border_color" in settings and not _is_hex_color(settings.get("note_border_color")):
        raise ValueError("Invalid Chemvas file.")
    if "note_border_width" in settings and (
        not _is_number(settings.get("note_border_width")) or cast(float, settings.get("note_border_width")) < 0.5
    ):
        raise ValueError("Invalid Chemvas file.")
    if "note_padding" in settings and (
        not _is_number(settings.get("note_padding")) or cast(float, settings.get("note_padding")) < 2.0
    ):
        raise ValueError("Invalid Chemvas file.")
    if settings.get("sheet_size") not in VALID_SHEET_SIZES:
        raise ValueError("Invalid Chemvas file.")
    if settings.get("sheet_orientation") not in VALID_SHEET_ORIENTATIONS:
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
        if not isinstance(payload, Mapping) or not set(payload) <= CLIPBOARD_SELECTION_PAYLOAD_KEYS:
            raise ValueError("Invalid clipboard payload.")
        atom_ids, atom_positions = _validate_clipboard_atoms(payload.get("atoms"))
        bond_pairs = _validate_clipboard_bonds(payload.get("bonds"), atom_ids)
        for ring_state in _validated_scene_state_list(payload.get("rings", [])):
            _validate_clipboard_ring(ring_state, atom_ids, bond_pairs, atom_positions)
        for mark_state in _validated_scene_state_list(payload.get("marks", [])):
            _validate_clipboard_mark(mark_state, atom_ids)
        for item_state in _validated_scene_state_list(payload.get("scene_items", [])):
            _validate_clipboard_scene_item(item_state)
        _validate_clipboard_perspective(payload, atom_ids)
    except ValueError:
        return False
    return True


def _validate_clipboard_atoms(atoms: object) -> tuple[set[int], dict[int, tuple[int | float | Decimal, int | float | Decimal]]]:
    if not isinstance(atoms, list):
        raise ValueError("Invalid clipboard payload.")
    atom_ids: set[int] = set()
    atom_positions: dict[int, tuple[int | float | Decimal, int | float | Decimal]] = {}
    for atom_state in atoms:
        if not isinstance(atom_state, Mapping):
            raise ValueError("Invalid clipboard payload.")
        required_keys = {"id", "element", "x", "y", "color", "explicit_label"}
        if not required_keys <= set(atom_state) or not set(atom_state) <= required_keys | {"annotation"}:
            raise ValueError("Invalid clipboard payload.")
        atom_id = _validated_clipboard_id(atom_state.get("id"))
        if atom_id in atom_ids:
            raise ValueError("Invalid clipboard payload.")
        _validate_atom_fields(atom_state, error="Invalid clipboard payload.")
        _validate_atom_annotation(atom_state.get("annotation", {}))
        atom_ids.add(atom_id)
        atom_positions[atom_id] = (
            cast(int | float | Decimal, atom_state.get("x")),
            cast(int | float | Decimal, atom_state.get("y")),
        )
    return atom_ids, atom_positions


def _validate_clipboard_perspective(payload: Mapping[str, object], atom_ids: set[int]) -> None:
    perspective_state = payload.get("perspective")
    if perspective_state is None:
        return
    version = payload.get("version")
    if version != CLIPBOARD_SELECTION_PERSPECTIVE_VERSION:
        raise ValueError("Invalid clipboard payload.")
    if not isinstance(perspective_state, Mapping):
        raise ValueError("Invalid clipboard payload.")
    if set(perspective_state) != {"atom_coords_3d", "projection_center_3d", "projection_anchor_2d"}:
        raise ValueError("Invalid clipboard payload.")
    atom_coords_3d = perspective_state.get("atom_coords_3d")
    if not isinstance(atom_coords_3d, list):
        raise ValueError("Invalid clipboard payload.")
    seen_atom_ids: set[int] = set()
    for entry in atom_coords_3d:
        if not isinstance(entry, Mapping) or set(entry) != {"atom_id", "coords"}:
            raise ValueError("Invalid clipboard payload.")
        atom_id = _validated_clipboard_id(entry.get("atom_id"))
        if atom_id in seen_atom_ids or atom_id not in atom_ids or not _is_point_3d(entry.get("coords")):
            raise ValueError("Invalid clipboard payload.")
        seen_atom_ids.add(atom_id)
    _validate_optional_point_3d(perspective_state.get("projection_center_3d"))
    _validate_optional_point_2d(perspective_state.get("projection_anchor_2d"))


def _serialized_atom_annotations(
    atom_annotations: Mapping[int, Mapping[str, int]],
    atom_ids: Collection[int],
) -> dict[int, dict[str, int]]:
    serialized: dict[int, dict[str, int]] = {}
    atom_id_set = set(atom_ids)
    for atom_id, annotation in atom_annotations.items():
        if atom_id not in atom_id_set:
            continue
        normalized = _normalized_atom_annotation(annotation)
        if normalized:
            serialized[atom_id] = normalized
    return serialized


def _normalized_atom_annotation(annotation: Mapping[str, object] | None) -> dict[str, int]:
    if not isinstance(annotation, Mapping):
        return {}
    normalized: dict[str, int] = {}
    formal_charge = annotation.get("formal_charge")
    if type(formal_charge) is int and formal_charge:
        normalized["formal_charge"] = formal_charge
    radical_electrons = annotation.get("radical_electrons")
    if type(radical_electrons) is int and radical_electrons > 0:
        normalized["radical_electrons"] = radical_electrons
    return normalized


def _validate_atom_annotations_state(annotations_state: object, atom_ids: set[int]) -> None:
    if not isinstance(annotations_state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    for atom_id_value, annotation in annotations_state.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id not in atom_ids:
            raise ValueError("Invalid Chemvas file.")
        _validate_atom_annotation(annotation)


def _validate_atom_annotation(annotation: object) -> None:
    if annotation is None:
        return
    if not isinstance(annotation, Mapping):
        raise ValueError("Invalid Chemvas file.")
    if not set(annotation) <= VALID_ATOM_ANNOTATION_KEYS:
        raise ValueError("Invalid Chemvas file.")
    formal_charge = annotation.get("formal_charge", 0)
    radical_electrons = annotation.get("radical_electrons", 0)
    if type(formal_charge) is not int:
        raise ValueError("Invalid Chemvas file.")
    if type(radical_electrons) is not int or radical_electrons < 0:
        raise ValueError("Invalid Chemvas file.")


def _validate_clipboard_bonds(bonds: object, atom_ids: set[int]) -> set[tuple[int, int]]:
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


def _validate_clipboard_mark(mark_state: Mapping[str, object], atom_ids: set[int]) -> None:
    # Deliberately looser than _validate_mark_states: legacy clipboard payloads
    # may carry mark_kind=None, which selection_payload_to_canvas_state maps to
    # "plus" before the state reaches the (strict) file validator.
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
    if kind == "note":
        _validate_note_fields(
            item_state,
            required_keys=frozenset(("kind", "text", "x", "y")),
            error="Invalid clipboard payload.",
        )
        return
    if kind in VALID_ARROW_KINDS:
        _validate_arrow_fields(item_state, error="Invalid clipboard payload.")
        return
    if kind == "ts_bracket":
        _validate_ts_bracket_fields(item_state, error="Invalid clipboard payload.")
        return
    if kind == "shape":
        _validate_shape_fields(item_state, error="Invalid clipboard payload.")
        return
    if kind == "orbital":
        _validate_orbital_fields(
            item_state,
            kind_key="orbital_kind",
            required_keys=frozenset(("kind", "orbital_kind", "center", "scale", "rotation")),
            error="Invalid clipboard payload.",
        )
        return
    raise ValueError("Invalid clipboard payload.")


def _validated_id(value: object) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError("Invalid Chemvas file.") from exc
    else:
        raise ValueError("Invalid Chemvas file.")
    if parsed < 0:
        raise ValueError("Invalid Chemvas file.")
    return parsed


def _validated_clipboard_id(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid clipboard payload.")
    return value


def _is_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _is_number(value: object) -> bool:
    if type(value) not in (int, float, Decimal):
        return False
    try:
        if type(value) is Decimal:
            decimal_value = cast(Decimal, value)
            if not decimal_value.is_finite() or abs(decimal_value) > MAX_SAFE_NUMBER_DECIMAL:
                return False
            return Decimal(str(float(decimal_value))) == decimal_value
        float_value = float(cast(Any, value))
        if not math.isfinite(float_value) or abs(float_value) > MAX_SAFE_NUMBER:
            return False
        if type(value) is int:
            return int(float_value) == value
        return True
    except OverflowError:
        return False


def normalize_json_numbers(value: object) -> object:
    if type(value) is Decimal:
        return float(value)
    if isinstance(value, list):
        normalized_list = [normalize_json_numbers(item) for item in value]
        if all(normalized is original for normalized, original in zip(normalized_list, value, strict=True)):
            return value
        return normalized_list
    if isinstance(value, dict):
        normalized_dict = {key: normalize_json_numbers(item) for key, item in value.items()}
        if all(normalized_dict[key] is item for key, item in value.items()):
            return value
        return normalized_dict
    return value


def _is_point(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    x, y = value
    return _is_number(x) and _is_number(y)


def _is_point_3d(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    x, y, z = value
    return _is_number(x) and _is_number(y) and _is_number(z)


def _is_atom_id_cycle(
    value: object,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
    *,
    clipboard: bool = False,
) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    try:
        validate_id = _validated_clipboard_id if clipboard else _validated_id
        parsed_ids = [validate_id(atom_id) for atom_id in value]
    except ValueError:
        return False
    if len(parsed_ids) < 3 or len(set(parsed_ids)) != len(parsed_ids):
        return False
    if any(atom_id not in atom_ids for atom_id in parsed_ids):
        return False
    return all(
        _bond_pair_key(atom_id, parsed_ids[(index + 1) % len(parsed_ids)]) in bond_pairs
        for index, atom_id in enumerate(parsed_ids)
    )


def _ring_points_match_atom_positions(
    points: object,
    ring_atom_ids: object,
    atom_positions: Mapping[int, tuple[int | float | Decimal, int | float | Decimal]],
    *,
    clipboard: bool = False,
) -> bool:
    if not isinstance(points, (list, tuple)) or not isinstance(ring_atom_ids, (list, tuple)):
        return False
    validate_id = _validated_clipboard_id if clipboard else _validated_id
    try:
        parsed_ids = [validate_id(atom_id) for atom_id in ring_atom_ids]
    except ValueError:
        return False
    if len(points) != len(parsed_ids):
        return False
    for point, atom_id in zip(points, parsed_ids, strict=True):
        if not _is_point(point):
            return False
        expected = atom_positions.get(atom_id)
        if expected is None:
            return False
        x, y = point
        if not _coordinate_matches(x, expected[0]):
            return False
        if not _coordinate_matches(y, expected[1]):
            return False
    return True


def _coordinate_matches(value: object, expected: int | float | Decimal) -> bool:
    if not _is_number(value):
        return False
    return abs(Decimal(str(value)) - Decimal(str(expected))) <= POINT_COORDINATE_TOLERANCE


def is_hex_color(value: object) -> bool:
    """Public form of the document hex-color rule (``#rgb`` / ``#rrggbb``)."""
    return _is_hex_color(value)


def _is_hex_color(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("#"):
        return False
    digits = value[1:]
    if len(digits) not in (3, 6):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in digits)
