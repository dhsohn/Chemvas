"""Validation of saved document, settings and clipboard payloads against the document schema."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from decimal import Decimal
from typing import cast

from chemvas.domain.document.schema import (
    _GROUPABLE_STATE_ITEM_KEYS,
    _QT_INT_MAX,
    _SHAPE_STATE_BASE_KEYS,
    ARROW_LABEL_SIDES,
    CANVAS_STATE_KEYS,
    MAX_ARROW_LABEL_CHARS,
    MAX_BOND_LENGTH_PX,
    MAX_MARK_TEXT_CHARS,
    OPTIONAL_CANVAS_STATE_KEYS,
    SETTINGS_KEYS,
    SUPPORTED_FILE_VERSIONS,
    VALID_ARROW_KINDS,
    VALID_ATOM_ANNOTATION_KEYS,
    VALID_BOND_ORDERS,
    VALID_BOND_STYLES,
    VALID_EQUILIBRIUM_KINDS,
    VALID_MARK_KINDS,
    VALID_ORBITAL_KINDS,
    VALID_SHAPE_KINDS,
    VALID_SHAPE_STROKES,
    VALID_SHEET_ORIENTATIONS,
    VALID_SHEET_SIZES,
    VALID_TS_BRACKET_KINDS,
    StateDict,
)
from chemvas.domain.document.state_values import (
    _bond_pair_key,
    _is_atom_id_cycle,
    _is_hex_color,
    _is_int,
    _is_number,
    _is_point,
    _is_point_3d,
    _ring_points_match_atom_positions,
    _validated_id,
)

from .calculation_plan import calculation_plan_from_state
from .images import validate_image_states


def _validate_document_state(state: Mapping[str, object], version: int) -> None:
    if type(version) is not int or version not in SUPPORTED_FILE_VERSIONS:
        raise ValueError("Invalid Chemvas file.")
    state_kind = _state_kind(state)
    if state_kind != "canvas":
        raise ValueError("Invalid Chemvas file.")
    _validate_canvas_state(state)
    if version == 7:
        for collection, field in (
            ("notes", "rotation"),
            ("images", "z"),
            ("shapes", "z"),
        ):
            if any(
                field in item
                for item in cast("list[StateDict]", state.get(collection, []))
            ):
                raise ValueError(
                    f"Invalid Chemvas v7 file. {collection}.{field} requires v8."
                )


def _state_kind(state: Mapping[str, object]) -> str | None:
    model_state = state.get("model")
    if isinstance(model_state, Mapping):
        return "canvas"
    return None


def _validate_canvas_state(state: Mapping[str, object]) -> None:
    keys = set(state)
    if not CANVAS_STATE_KEYS <= keys or not keys <= (
        CANVAS_STATE_KEYS | OPTIONAL_CANVAS_STATE_KEYS
    ):
        missing = sorted(CANVAS_STATE_KEYS - keys)
        unknown = sorted(
            str(key) for key in keys - CANVAS_STATE_KEYS - OPTIONAL_CANVAS_STATE_KEYS
        )
        raise ValueError(
            f"Invalid Chemvas file. state fields: missing={missing}, unknown={unknown}."
        )
    model_state = state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    atom_ids, bond_pairs, atom_positions = _validate_model_state(model_state)
    _validate_ring_fill_states(
        state.get("ring_fills"), atom_ids, bond_pairs, atom_positions
    )
    _validate_note_states(state.get("notes"))
    _validate_mark_states(state.get("marks"), atom_ids)
    _validate_arrow_states(state.get("arrows"))
    _validate_ts_bracket_states(state.get("ts_brackets"))
    if not isinstance(state.get("shapes"), list):
        raise ValueError("Invalid Chemvas file. state.shapes must be a list.")
    _validate_shape_states(state.get("shapes"))
    _validate_orbital_states(state.get("orbitals"))
    validate_image_states(state.get("images", []))
    _validate_perspective_state(state.get("perspective"), atom_ids)
    _validate_group_states(state, atom_ids)
    calculation_plan = state.get("calculation_plan")
    if calculation_plan is not None:
        try:
            calculation_plan_from_state(
                calculation_plan,
                atom_ids=atom_ids,
                bond_pairs=bond_pairs,
            )
        except ValueError as exc:
            raise ValueError(
                f"Invalid Chemvas file. state.calculation_plan: {exc}"
            ) from exc
    settings = state.get("settings")
    if not isinstance(settings, Mapping):
        raise ValueError("Invalid Chemvas file.")
    validate_settings_state(settings)
    last_smiles_input = state.get("last_smiles_input")
    if last_smiles_input is not None and not isinstance(last_smiles_input, str):
        raise ValueError("Invalid Chemvas file.")


def _validate_model_state(
    model_state: Mapping[str, object],
) -> tuple[
    set[int],
    set[tuple[int, int]],
    dict[int, tuple[int | float | Decimal, int | float | Decimal]],
]:
    atoms_state = model_state.get("atoms")
    bonds_state = model_state.get("bonds")
    required_keys = {"atoms", "bonds", "next_atom_id"}
    if not required_keys <= set(model_state) or not set(
        model_state
    ) <= required_keys | {"atom_annotations"}:
        raise ValueError("Invalid Chemvas file.")
    if not isinstance(atoms_state, Mapping) or not isinstance(bonds_state, list):
        raise ValueError("Invalid Chemvas file.")

    atom_ids: set[int] = set()
    atom_positions: dict[int, tuple[int | float | Decimal, int | float | Decimal]] = {}
    for atom_id_value, atom_state in atoms_state.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id in atom_ids or not isinstance(atom_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        try:
            _validate_atom_state(atom_state)
        except ValueError as exc:
            raise ValueError(f"state.model.atoms[{atom_id}]: {exc}") from exc
        atom_ids.add(atom_id)
        atom_positions[atom_id] = (
            cast("int | float | Decimal", atom_state.get("x")),
            cast("int | float | Decimal", atom_state.get("y")),
        )

    next_atom_id = model_state.get("next_atom_id")
    if not _is_int(next_atom_id) or next_atom_id < max(atom_ids, default=-1) + 1:
        raise ValueError("Invalid Chemvas file.")

    bond_pairs: set[tuple[int, int]] = set()
    for bond_state in bonds_state:
        if bond_state is None:
            raise ValueError("Invalid Chemvas file.")
        if not isinstance(bond_state, Mapping):
            raise ValueError("Invalid Chemvas file.")
        bond_pair = _validate_bond_state(bond_state, atom_ids)
        if bond_pair in bond_pairs:
            raise ValueError("Invalid Chemvas file.")
        bond_pairs.add(bond_pair)
    _validate_atom_annotations_state(model_state.get("atom_annotations", {}), atom_ids)
    return atom_ids, bond_pairs, atom_positions


def _validate_atom_fields(atom_state: Mapping[str, object], *, error: str) -> None:
    element = atom_state.get("element")
    if not isinstance(element, str) or not element.strip():
        raise ValueError(error)
    _validate_utf8(element, error=f"{error} element")
    for coordinate in ("x", "y"):
        if not _is_number(atom_state.get(coordinate)):
            raise ValueError(
                f"{error} {coordinate} must be a finite, safely representable number."
            )
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
    if not _is_valid_choice(style, VALID_BOND_STYLES):
        raise ValueError(error)
    if style in {"wedge", "hash"} and order != 1:
        raise ValueError(error)
    if style == "double_either" and order != 2:
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
    if not required_keys <= keys or not keys <= required_keys | {"html", "rotation"}:
        raise ValueError(error)
    if not isinstance(note_state.get("text"), str):
        raise ValueError(error)
    _validate_utf8(note_state["text"], error=f"{error} text")
    if "html" in note_state and not isinstance(note_state.get("html"), str):
        raise ValueError(error)
    if "html" in note_state:
        _validate_utf8(note_state["html"], error=f"{error} html")
    if "rotation" in note_state and not _is_number(note_state["rotation"]):
        raise ValueError(error)
    if not _is_number(note_state.get("x")) or not _is_number(note_state.get("y")):
        raise ValueError(error)


def _validate_arrow_labels(labels: object, *, error: str) -> None:
    if not isinstance(labels, Mapping) or not labels:
        raise ValueError(error)
    if not set(labels) <= ARROW_LABEL_SIDES:
        raise ValueError(error)
    for text in labels.values():
        if type(text) is not str or not text.strip():
            raise ValueError(error)
        if len(text) > MAX_ARROW_LABEL_CHARS:
            raise ValueError(error)
        _validate_utf8(text, error=f"{error} arrow label text")


def _validate_utf8(text: object, *, error: str) -> None:
    if isinstance(text, str):
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"{error} must contain valid Unicode (no lone surrogates)."
            ) from exc


def _validate_mark_text(text: object, *, error: str) -> None:
    if text is None:
        return
    if not isinstance(text, str) or len(text) > MAX_MARK_TEXT_CHARS:
        raise ValueError(
            f"{error} mark text must be null or at most {MAX_MARK_TEXT_CHARS} characters."
        )
    _validate_utf8(text, error=f"{error} mark text")


def validate_arrow_fields(arrow_state: Mapping[str, object], *, error: str) -> None:
    keys = set(arrow_state)
    required_keys = {"kind", "start", "end"}
    optional_keys = {"control", "double", "labels", "color", "mirrored"}
    if not required_keys <= keys or not keys <= required_keys | optional_keys:
        raise ValueError(error)
    if "color" in keys and not _is_hex_color(arrow_state["color"]):
        raise ValueError(error)
    if "labels" in keys:
        _validate_arrow_labels(arrow_state["labels"], error=error)
    if not _is_valid_choice(arrow_state.get("kind"), VALID_ARROW_KINDS):
        raise ValueError(error)
    if "mirrored" in keys and (
        arrow_state["kind"] not in VALID_EQUILIBRIUM_KINDS
        or type(arrow_state["mirrored"]) is not bool
    ):
        raise ValueError(f"{error} mirrored must be a boolean on an equilibrium arrow.")
    if not _is_point(arrow_state.get("start")) or not _is_point(arrow_state.get("end")):
        raise ValueError(error)
    control = arrow_state.get("control")
    if control is not None and not _is_point(control):
        raise ValueError(error)
    double = arrow_state.get("double")
    if double is not None and type(double) is not bool:
        raise ValueError(error)


def validate_ts_bracket_fields(
    ts_bracket_state: Mapping[str, object], *, error: str
) -> None:
    """The one definition of a valid TS bracket state, for files and the clipboard."""
    keys = set(ts_bracket_state)
    if ts_bracket_state.get("kind") != "ts_bracket":
        raise ValueError(error)
    bracket_kind = ts_bracket_state.get("bracket_kind")
    if not _is_valid_choice(bracket_kind, VALID_TS_BRACKET_KINDS):
        raise ValueError(error)
    if keys != {
        "kind",
        "left",
        "top",
        "right",
        "bottom",
        "bracket_kind",
    }:
        raise ValueError(error)
    for key in ("left", "top", "right", "bottom"):
        if not _is_number(ts_bracket_state.get(key)):
            raise ValueError(error)


def validate_shape_fields(shape_state: Mapping[str, object], *, error: str) -> None:
    """The one definition of a valid shape state, for files and the clipboard."""
    keys = set(shape_state)
    if not _SHAPE_STATE_BASE_KEYS <= keys or not keys <= _SHAPE_STATE_BASE_KEYS | {
        "fill",
        "fill_alpha",
        "z",
    }:
        raise ValueError(error)
    if "z" in keys and (
        not _is_number(shape_state["z"])
        or not -12.0 <= cast("float", shape_state["z"]) <= 10.0
    ):
        raise ValueError(error)
    if shape_state.get("kind") != "shape":
        raise ValueError(error)
    if not _is_valid_choice(shape_state.get("shape_kind"), VALID_SHAPE_KINDS):
        raise ValueError(error)
    if not _is_valid_choice(shape_state.get("stroke_style"), VALID_SHAPE_STROKES):
        raise ValueError(error)
    for key in ("left", "top", "right", "bottom"):
        if not _is_number(shape_state.get(key)):
            raise ValueError(error)
    if "fill" in keys and not _is_hex_color(shape_state.get("fill")):
        raise ValueError(error)
    if "fill_alpha" in keys and (
        not _is_number(shape_state.get("fill_alpha"))
        or not 0.0 <= cast("float", shape_state.get("fill_alpha")) <= 1.0
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
    if not _is_valid_choice(orbital_state.get(kind_key), VALID_ORBITAL_KINDS):
        raise ValueError(error)
    if not _is_point(orbital_state.get("center")):
        raise ValueError(error)
    if not _is_number(orbital_state.get("scale")) or not _is_number(
        orbital_state.get("rotation")
    ):
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
    if (
        not isinstance(points, (list, tuple))
        or len(points) < 3
        or any(not _is_point(point) for point in points)
    ):
        raise ValueError(error)
    ring_atom_ids = ring_state.get("atom_ids")
    if not isinstance(ring_atom_ids, (list, tuple)) or len(ring_atom_ids) != len(
        points
    ):
        raise ValueError(error)
    if any(not _is_int(atom_id) or atom_id < 0 for atom_id in ring_atom_ids):
        raise ValueError(f"{error} atom_ids must contain non-negative integers.")
    if not _is_atom_id_cycle(ring_atom_ids, atom_ids, bond_pairs, clipboard=clipboard):
        raise ValueError(error)
    if not _ring_points_match_atom_positions(
        points, ring_atom_ids, atom_positions, clipboard=clipboard
    ):
        raise ValueError(error)
    color = ring_state.get("color")
    if color is not None and not _is_hex_color(color):
        raise ValueError(error)
    alpha = ring_state.get("alpha")
    if not _is_number(alpha) or not 0.0 <= cast("float", alpha) <= 1.0:
        raise ValueError(error)


def _validate_atom_state(atom_state: Mapping[str, object]) -> None:
    if set(atom_state) != {"element", "x", "y", "color", "explicit_label"}:
        raise ValueError("Invalid Chemvas file.")
    _validate_atom_fields(atom_state, error="Invalid Chemvas file.")


def _validate_bond_state(
    bond_state: Mapping[str, object], atom_ids: set[int]
) -> tuple[int, int]:
    return _validate_bond_fields(
        bond_state,
        atom_ids,
        id_validator=_validated_id,
        error="Invalid Chemvas file.",
    )


def _is_valid_choice(value: object, choices: Collection[str]) -> bool:
    """Safe membership test for untrusted input.

    Malformed payloads can put unhashable values (JSON arrays/objects) where a
    string is expected; testing those with ``in`` against a set raises
    TypeError, which would escape the boundary's ValueError rejection path.
    """
    return isinstance(value, str) and value in choices


def _validate_ring_fill_states(
    states: object,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
    atom_positions: Mapping[int, tuple[int | float | Decimal, int | float | Decimal]],
) -> None:
    for index, ring_state in enumerate(_validated_scene_state_list(states)):
        _validate_ring_fields(
            ring_state,
            atom_ids,
            bond_pairs,
            atom_positions,
            required_keys=frozenset(("points", "atom_ids", "color", "alpha")),
            clipboard=False,
            error=f"Invalid Chemvas file. state.ring_fills[{index}]:",
        )


def _validate_note_states(states: object) -> None:
    for index, note_state in enumerate(_validated_scene_state_list(states)):
        _validate_note_fields(
            note_state,
            required_keys=frozenset(("text", "x", "y")),
            error=f"Invalid Chemvas file. state.notes[{index}]:",
        )


def _validate_mark_states(states: object, atom_ids: set[int]) -> None:
    for index, mark_state in enumerate(_validated_scene_state_list(states)):
        keys = set(mark_state)
        required = {"kind", "text", "atom_id", "dx", "dy", "x", "y"}
        if not required <= keys or keys - required - {"color"}:
            raise ValueError("Invalid Chemvas file.")
        if "color" in keys and not _is_hex_color(mark_state["color"]):
            raise ValueError("Invalid Chemvas file. Mark color must be a hex color.")
        if not _is_valid_choice(mark_state.get("kind"), VALID_MARK_KINDS):
            raise ValueError("Invalid Chemvas file.")
        text = mark_state.get("text")
        _validate_mark_text(text, error="Invalid Chemvas file.")
        if not _is_number(mark_state.get("x")) or not _is_number(mark_state.get("y")):
            raise ValueError("Invalid Chemvas file.")
        atom_id = mark_state.get("atom_id")
        if atom_id is None:
            if mark_state.get("dx") is not None or mark_state.get("dy") is not None:
                raise ValueError("Invalid Chemvas file.")
            continue
        if not _is_int(atom_id) or atom_id < 0 or atom_id not in atom_ids:
            raise ValueError(
                f"Invalid Chemvas file. state.marks[{index}].atom_id must be "
                "an existing non-negative integer atom ID or null."
            )
        dx = mark_state.get("dx")
        dy = mark_state.get("dy")
        if (dx is None and dy is None) or (_is_number(dx) and _is_number(dy)):
            continue
        raise ValueError("Invalid Chemvas file.")


def _validate_arrow_states(states: object) -> None:
    for arrow_state in _validated_scene_state_list(states):
        validate_arrow_fields(arrow_state, error="Invalid Chemvas file.")


def _validate_ts_bracket_states(states: object) -> None:
    for ts_bracket_state in _validated_scene_state_list(states):
        validate_ts_bracket_fields(ts_bracket_state, error="Invalid Chemvas file.")


def _validate_shape_states(states: object) -> None:
    for shape_state in _validated_scene_state_list(states):
        validate_shape_fields(shape_state, error="Invalid Chemvas file.")


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


def _validate_group_states(
    state: Mapping[str, object],
    atom_ids: set[int],
    *,
    item_keys: frozenset[str] = _GROUPABLE_STATE_ITEM_KEYS,
) -> None:
    if "groups" not in state:
        return
    group_states = state["groups"]
    if not isinstance(group_states, list):
        raise ValueError("Invalid Chemvas file. state.groups must be a list.")
    item_counts: dict[str, int] = {}
    for key in item_keys:
        items = state.get(key)
        item_counts[key] = len(items) if isinstance(items, list) else 0
    seen_atom_ids: set[int] = set()
    seen_item_refs: set[tuple[str, int]] = set()
    for group_state in group_states:
        if not isinstance(group_state, Mapping) or set(group_state) != {
            "atoms",
            "items",
        }:
            raise ValueError("Invalid Chemvas file.")
        group_atoms = group_state.get("atoms")
        group_items = group_state.get("items")
        if not isinstance(group_atoms, list) or not isinstance(group_items, list):
            raise ValueError("Invalid Chemvas file.")
        if not group_atoms and not group_items:
            raise ValueError("Invalid Chemvas file.")
        for atom_id in group_atoms:
            if (
                not _is_int(atom_id)
                or atom_id not in atom_ids
                or atom_id in seen_atom_ids
            ):
                raise ValueError("Invalid Chemvas file.")
            seen_atom_ids.add(atom_id)
        for item_ref in group_items:
            if not isinstance(item_ref, (list, tuple)) or len(item_ref) != 2:
                raise ValueError("Invalid Chemvas file.")
            kind, index = item_ref
            if not _is_valid_choice(kind, item_keys) or not _is_int(index):
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


def validate_settings_state(settings: Mapping[str, object]) -> None:
    keys = set(settings)
    if keys != SETTINGS_KEYS:
        missing = sorted(SETTINGS_KEYS - keys)
        unknown = sorted(str(key) for key in keys - SETTINGS_KEYS)
        raise ValueError(
            f"Invalid Chemvas file. settings fields: missing={missing}, unknown={unknown}."
        )
    if (
        not _is_number(settings.get("bond_length_px"))
        or not 0 < cast("float", settings.get("bond_length_px")) <= MAX_BOND_LENGTH_PX
    ):
        raise ValueError(
            f"Invalid Chemvas file. settings.bond_length_px must be finite, positive, and at most {MAX_BOND_LENGTH_PX} (Qt glyph-size limit)."
        )
    if (
        not _is_number(settings.get("arrow_line_width"))
        or cast("float", settings.get("arrow_line_width")) < 0.5
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.arrow_line_width must be finite and at least 0.5."
        )
    if (
        not _is_number(settings.get("arrow_head_scale"))
        # JSON readers retain Decimal values until validation. Compare decimal
        # bounds in the same representation as the document, not binary floats.
        or not Decimal("0.1")
        <= Decimal(str(settings.get("arrow_head_scale")))
        <= Decimal("0.8")
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.arrow_head_scale must be between 0.1 and 0.8."
        )
    if type(settings.get("orbital_phase_enabled")) is not bool:
        raise ValueError(
            "Invalid Chemvas file. settings.orbital_phase_enabled must be boolean."
        )
    text_font_size = settings.get("text_font_size")
    if not _is_int(text_font_size) or not 6 <= text_font_size <= _QT_INT_MAX:
        raise ValueError(
            f"Invalid Chemvas file. settings.text_font_size must be an integer from 6 to {_QT_INT_MAX}."
        )
    if (
        not _is_int(settings.get("text_font_weight"))
        or not 1 <= cast("int", settings.get("text_font_weight")) <= 1000
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.text_font_weight must be an integer from 1 to 1000."
        )
    if type(settings.get("text_italic")) is not bool:
        raise ValueError("Invalid Chemvas file. settings.text_italic must be boolean.")
    if not isinstance(settings.get("text_font_family"), str) or not settings.get(
        "text_font_family"
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.text_font_family must be a nonempty string."
        )
    _validate_utf8(settings["text_font_family"], error="settings.text_font_family")
    if not _is_hex_color(settings.get("text_color")):
        raise ValueError(
            "Invalid Chemvas file. settings.text_color must be a #RRGGBB color."
        )
    if not _is_valid_choice(
        settings.get("text_alignment"), {"left", "center", "right", "justify"}
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.text_alignment must be left, center, right, or justify."
        )
    if not _is_number(settings.get("text_line_spacing")) or Decimal(
        str(settings.get("text_line_spacing"))
    ) < Decimal("0.8"):
        raise ValueError(
            "Invalid Chemvas file. settings.text_line_spacing must be finite and at least 0.8."
        )
    if type(settings.get("note_box_enabled")) is not bool:
        raise ValueError(
            "Invalid Chemvas file. settings.note_box_enabled must be boolean."
        )
    if not _is_hex_color(settings.get("note_box_color")):
        raise ValueError(
            "Invalid Chemvas file. settings.note_box_color must be a #RRGGBB color."
        )
    if (
        not _is_number(settings.get("note_box_alpha"))
        or not 0.0 <= cast("float", settings.get("note_box_alpha")) <= 1.0
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.note_box_alpha must be between 0 and 1."
        )
    if type(settings.get("note_border_enabled")) is not bool:
        raise ValueError(
            "Invalid Chemvas file. settings.note_border_enabled must be boolean."
        )
    if not _is_hex_color(settings.get("note_border_color")):
        raise ValueError(
            "Invalid Chemvas file. settings.note_border_color must be a #RRGGBB color."
        )
    if (
        not _is_number(settings.get("note_border_width"))
        or cast("float", settings.get("note_border_width")) < 0.5
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.note_border_width must be finite and at least 0.5."
        )
    if (
        not _is_number(settings.get("note_padding"))
        or cast("float", settings.get("note_padding")) < 2.0
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.note_padding must be finite and at least 2."
        )
    if not _is_valid_choice(settings.get("sheet_size"), VALID_SHEET_SIZES):
        raise ValueError("Invalid Chemvas file. settings.sheet_size must be A4.")
    if not _is_valid_choice(
        settings.get("sheet_orientation"), VALID_SHEET_ORIENTATIONS
    ):
        raise ValueError(
            "Invalid Chemvas file. settings.sheet_orientation must be landscape or portrait."
        )


def _validate_atom_annotations_state(
    annotations_state: object, atom_ids: set[int]
) -> None:
    if not isinstance(annotations_state, Mapping):
        raise ValueError("Invalid Chemvas file.")
    seen: set[int] = set()
    for atom_id_value, annotation in annotations_state.items():
        atom_id = _validated_id(atom_id_value)
        if atom_id not in atom_ids:
            raise ValueError("Invalid Chemvas file.")
        if atom_id in seen:
            raise ValueError(
                f"Invalid Chemvas file. Duplicate atom annotation ID: {atom_id}."
            )
        seen.add(atom_id)
        try:
            _validate_atom_annotation(annotation)
        except ValueError as exc:
            raise ValueError(f"state.model.atom_annotations[{atom_id}]: {exc}") from exc


def _validate_atom_annotation(annotation: object) -> None:
    if not isinstance(annotation, Mapping):
        raise ValueError("Invalid Chemvas file. Atom annotation must be an object.")
    if not set(annotation) <= VALID_ATOM_ANNOTATION_KEYS:
        raise ValueError("Invalid Chemvas file.")
    formal_charge = annotation.get("formal_charge", 0)
    radical_electrons = annotation.get("radical_electrons", 0)
    if type(formal_charge) is not int:
        raise ValueError("Invalid Chemvas file.")
    if type(radical_electrons) is not int or radical_electrons < 0:
        raise ValueError("Invalid Chemvas file.")


__all__ = [
    "validate_arrow_fields",
    "validate_settings_state",
    "validate_shape_fields",
    "validate_ts_bracket_fields",
]
