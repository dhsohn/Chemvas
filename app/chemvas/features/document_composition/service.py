from __future__ import annotations

from collections.abc import Mapping
from html import escape
from typing import Any, cast

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    SETTINGS_KEYS,
    VALID_ARROW_KINDS,
    VALID_BOND_ORDERS,
    VALID_BOND_STYLES,
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    is_document_number,
    is_hex_color,
    serialize_model_state,
    serialize_settings,
)
from chemvas.domain.document.state import (
    VALID_SHAPE_KINDS,
    VALID_SHAPE_STROKES,
    validate_settings_state,
)
from chemvas.features.annotations import sanitize_note_html
from chemvas.features.calculation_bundle import inspect_components
from chemvas.features.insertion import (
    annotation_mark_direction,
    annotation_mark_kinds,
)

COMPOSITION_FORMAT = "chemvas-document-composition"
COMPOSITION_VERSION = 1
MAX_ATOMS = 4096
MAX_BONDS = 8192
MAX_SCENE_ITEMS = 4096
MAX_ELECTRONIC_MARKS_PER_ATOM = 8
ELECTRONIC_MARK_DISTANCE_BOND_FRACTION = 0.55
_ROOT_REQUIRED = frozenset(("format", "version", "atoms", "bonds"))
_ROOT_ALLOWED = _ROOT_REQUIRED | {
    "notes",
    "arrows",
    "shapes",
    "ring_fills",
    "settings",
}
_ATOM_REQUIRED = frozenset(("id", "element", "x", "y"))
_ATOM_ALLOWED = _ATOM_REQUIRED | {
    "color",
    "explicit_label",
    "formal_charge",
    "radical_electrons",
}
_BOND_REQUIRED = frozenset(("a", "b", "order"))
_BOND_ALLOWED = _BOND_REQUIRED | {"style", "color"}
_NOTE_REQUIRED = frozenset(("text", "x", "y"))
_NOTE_ALLOWED = _NOTE_REQUIRED | {"style"}
_NOTE_STYLE_ALLOWED = frozenset(("font_size", "font_weight", "italic", "color"))
_ARROW_REQUIRED = frozenset(("kind", "start", "end"))
_ARROW_ALLOWED = _ARROW_REQUIRED | {"control", "double"}
_SHAPE_REQUIRED = frozenset(
    ("shape_kind", "left", "top", "right", "bottom", "stroke_style")
)
_SHAPE_ALLOWED = _SHAPE_REQUIRED | {"fill", "fill_alpha"}
_RING_REQUIRED = frozenset(("atom_ids", "color", "alpha"))
_DEFAULT_BOND_STYLE = {1: "single", 2: "double", 3: "triple"}


def compose_document_state(composition: object) -> dict[str, Any]:
    root = _mapping(composition, "composition")
    _keys(root, required=_ROOT_REQUIRED, allowed=_ROOT_ALLOWED, name="composition")
    if root.get("format") != COMPOSITION_FORMAT:
        raise ValueError(f"composition format must be {COMPOSITION_FORMAT!r}")
    if (
        type(root.get("version")) is not int
        or root.get("version") != COMPOSITION_VERSION
    ):
        raise ValueError("composition version must be 1")

    raw_atoms = _list(root.get("atoms"), "atoms", maximum=MAX_ATOMS)
    raw_bonds = _list(root.get("bonds"), "bonds", maximum=MAX_BONDS)
    atoms, annotations = _atoms(raw_atoms)
    bonds = _bonds(raw_bonds, atoms)
    settings = _settings(root.get("settings"))
    notes = _notes(root.get("notes", []))
    arrows = _arrows(root.get("arrows", []))
    shapes = _shapes(root.get("shapes", []))
    ring_fills = _ring_fills(root.get("ring_fills", []), atoms)

    model = MoleculeModel(atoms=atoms, bonds=bonds, atom_annotations=annotations)
    marks = _annotation_marks(
        atoms,
        annotations,
        mark_distance=(
            float(cast(Any, settings["bond_length_px"]))
            * ELECTRONIC_MARK_DISTANCE_BOND_FRACTION
        ),
    )
    state: dict[str, Any] = {
        "model": serialize_model_state(model),
        "ring_fills": ring_fills,
        "notes": notes,
        "marks": marks,
        "arrows": arrows,
        "ts_brackets": [],
        "shapes": shapes,
        "orbitals": [],
        "settings": settings,
        "last_smiles_input": None,
    }
    build_document_payload(state, CANVAS_FILE_VERSION)
    inspect_components(state)
    return state


def _atoms(
    raw_atoms: list[object],
) -> tuple[dict[int, Atom], dict[int, dict[str, int]]]:
    atoms: dict[int, Atom] = {}
    annotations: dict[int, dict[str, int]] = {}
    for index, raw_atom in enumerate(raw_atoms):
        atom = _mapping(raw_atom, f"atom {index}")
        _keys(
            atom, required=_ATOM_REQUIRED, allowed=_ATOM_ALLOWED, name=f"atom {index}"
        )
        atom_id = _id(atom.get("id"), f"atom {index} id")
        if atom_id != index:
            raise ValueError("atom ids must be contiguous and ordered from 0")
        element = atom.get("element")
        if not isinstance(element, str) or not element.strip():
            raise ValueError(f"atom {index} element must be a non-empty string")
        color = _color(atom.get("color", "#000000"), f"atom {index} color")
        explicit_label = atom.get("explicit_label", False)
        if type(explicit_label) is not bool:
            raise ValueError(f"atom {index} explicit_label must be a boolean")
        atoms[atom_id] = Atom(
            element=element,
            x=_number(atom.get("x"), f"atom {index} x"),
            y=_number(atom.get("y"), f"atom {index} y"),
            color=color,
            explicit_label=cast(bool, explicit_label),
        )
        annotation = _atom_annotation(atom, index)
        if annotation:
            annotations[atom_id] = annotation
    return atoms, annotations


def _bonds(raw_bonds: list[object], atoms: Mapping[int, Atom]) -> list[Bond | None]:
    bonds: list[Bond | None] = []
    seen_pairs: set[tuple[int, int]] = set()
    for index, raw_bond in enumerate(raw_bonds):
        bond = _mapping(raw_bond, f"bond {index}")
        _keys(
            bond, required=_BOND_REQUIRED, allowed=_BOND_ALLOWED, name=f"bond {index}"
        )
        a = _id(bond.get("a"), f"bond {index} a")
        b = _id(bond.get("b"), f"bond {index} b")
        if a == b or a not in atoms or b not in atoms:
            raise ValueError(f"bond {index} endpoints must reference distinct atoms")
        pair = (a, b) if a < b else (b, a)
        if pair in seen_pairs:
            raise ValueError(f"bond {index} duplicates an existing atom pair")
        seen_pairs.add(pair)
        order = bond.get("order")
        if type(order) is not int or order not in VALID_BOND_ORDERS:
            raise ValueError(f"bond {index} order must be 1, 2, or 3")
        normalized_order = cast(int, order)
        style = bond.get("style", _DEFAULT_BOND_STYLE[normalized_order])
        if not isinstance(style, str) or style not in VALID_BOND_STYLES:
            raise ValueError(f"bond {index} style is not supported")
        if style in {"wedge", "hash"} and normalized_order != 1:
            raise ValueError(f"bond {index} wedge/hash style requires order 1")
        bonds.append(
            Bond(
                a=a,
                b=b,
                order=normalized_order,
                style=style,
                color=_color(bond.get("color", "#000000"), f"bond {index} color"),
            )
        )
    return bonds


def _settings(value: object) -> dict[str, object]:
    settings = cast(
        dict[str, object],
        serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.3,
            orbital_phase_enabled=False,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="landscape",
        ),
    )
    if value is None:
        return settings
    overrides = _mapping(value, "settings")
    # A composition may override any subset; the document contract itself
    # requires the full key set, which `validate_settings_state` enforces
    # below once the defaults have been filled in.
    if not set(overrides) <= SETTINGS_KEYS:
        raise ValueError("settings has unknown keys")
    settings.update(overrides)
    # Overridden values feed the mark-distance arithmetic before the final
    # document validation runs, so they must be proven valid here first.
    validate_settings_state(settings)
    return settings


def _notes(value: object) -> list[dict[str, object]]:
    notes: list[dict[str, object]] = []
    for index, raw_note in enumerate(_list(value, "notes", maximum=MAX_SCENE_ITEMS)):
        note = _mapping(raw_note, f"note {index}")
        _keys(
            note, required=_NOTE_REQUIRED, allowed=_NOTE_ALLOWED, name=f"note {index}"
        )
        text = note.get("text")
        if not isinstance(text, str):
            raise ValueError(f"note {index} text must be a string")
        state: dict[str, object] = {
            "text": text,
            "x": _number(note.get("x"), f"note {index} x"),
            "y": _number(note.get("y"), f"note {index} y"),
        }
        if "style" in note:
            state["html"] = _styled_note_html(text, note.get("style"), index)
        notes.append(state)
    return notes


def _styled_note_html(text: str, value: object, index: int) -> str:
    style = _mapping(value, f"note {index} style")
    if not style or not set(style) <= _NOTE_STYLE_ALLOWED:
        raise ValueError(f"note {index} style must use supported non-empty keys")
    declarations: list[str] = []
    if "font_size" in style:
        size = style["font_size"]
        if type(size) is not int or not 6 <= cast(int, size) <= 96:
            raise ValueError(f"note {index} font_size must be an integer from 6 to 96")
        declarations.append(f"font-size:{size}pt")
    if "font_weight" in style:
        weight = style["font_weight"]
        if type(weight) is not int or weight not in range(100, 1000, 100):
            raise ValueError(f"note {index} font_weight must be 100 through 900")
        declarations.append(f"font-weight:{weight}")
    if "italic" in style:
        italic = style["italic"]
        if type(italic) is not bool:
            raise ValueError(f"note {index} italic must be a boolean")
        declarations.append("font-style:italic" if italic else "font-style:normal")
    if "color" in style:
        declarations.append(f"color:{_color(style['color'], f'note {index} color')}")
    escaped_text = escape(text, quote=False).replace("\n", "<br>")
    raw_html = f'<span style="{";".join(declarations)}">{escaped_text}</span>'
    sanitized = sanitize_note_html(raw_html)
    if sanitized is None:
        raise ValueError(f"note {index} style could not be represented safely")
    return sanitized


def _arrows(value: object) -> list[dict[str, object]]:
    arrows: list[dict[str, object]] = []
    for index, raw_arrow in enumerate(_list(value, "arrows", maximum=MAX_SCENE_ITEMS)):
        arrow = _mapping(raw_arrow, f"arrow {index}")
        _keys(
            arrow,
            required=_ARROW_REQUIRED,
            allowed=_ARROW_ALLOWED,
            name=f"arrow {index}",
        )
        kind = arrow.get("kind")
        if not isinstance(kind, str) or kind not in VALID_ARROW_KINDS:
            raise ValueError(f"arrow {index} kind is not supported")
        state: dict[str, object] = {
            "kind": kind,
            "start": list(_point(arrow.get("start"), f"arrow {index} start")),
            "end": list(_point(arrow.get("end"), f"arrow {index} end")),
        }
        if "control" in arrow:
            state["control"] = list(_point(arrow["control"], f"arrow {index} control"))
        if "double" in arrow:
            if type(arrow["double"]) is not bool:
                raise ValueError(f"arrow {index} double must be a boolean")
            state["double"] = arrow["double"]
        arrows.append(state)
    return arrows


def _shapes(value: object) -> list[dict[str, object]]:
    shapes: list[dict[str, object]] = []
    for index, raw_shape in enumerate(_list(value, "shapes", maximum=MAX_SCENE_ITEMS)):
        shape = _mapping(raw_shape, f"shape {index}")
        _keys(
            shape,
            required=_SHAPE_REQUIRED,
            allowed=_SHAPE_ALLOWED,
            name=f"shape {index}",
        )
        shape_kind = shape.get("shape_kind")
        stroke_style = shape.get("stroke_style")
        if not isinstance(shape_kind, str) or shape_kind not in VALID_SHAPE_KINDS:
            raise ValueError(f"shape {index} kind is not supported")
        if not isinstance(stroke_style, str) or stroke_style not in VALID_SHAPE_STROKES:
            raise ValueError(f"shape {index} stroke_style is not supported")
        state: dict[str, object] = {
            "kind": "shape",
            "shape_kind": shape_kind,
            "stroke_style": stroke_style,
        }
        for key in ("left", "top", "right", "bottom"):
            state[key] = _number(shape.get(key), f"shape {index} {key}")
        if "fill" in shape:
            state["fill"] = _color(shape["fill"], f"shape {index} fill")
        if "fill_alpha" in shape:
            alpha = _number(shape["fill_alpha"], f"shape {index} fill_alpha")
            if not 0.0 <= alpha <= 1.0:
                raise ValueError(f"shape {index} fill_alpha must be from 0 to 1")
            state["fill_alpha"] = alpha
        shapes.append(state)
    return shapes


def _ring_fills(value: object, atoms: Mapping[int, Atom]) -> list[dict[str, object]]:
    fills: list[dict[str, object]] = []
    for index, raw_fill in enumerate(
        _list(value, "ring_fills", maximum=MAX_SCENE_ITEMS)
    ):
        fill = _mapping(raw_fill, f"ring_fill {index}")
        _keys(
            fill,
            required=_RING_REQUIRED,
            allowed=_RING_REQUIRED,
            name=f"ring_fill {index}",
        )
        raw_ids = _list(
            fill.get("atom_ids"), f"ring_fill {index} atom_ids", maximum=MAX_ATOMS
        )
        atom_ids = [_id(atom_id, f"ring_fill {index} atom_id") for atom_id in raw_ids]
        if len(atom_ids) < 3 or len(set(atom_ids)) != len(atom_ids):
            raise ValueError(
                f"ring_fill {index} must contain at least three unique atoms"
            )
        try:
            points = [[atoms[atom_id].x, atoms[atom_id].y] for atom_id in atom_ids]
        except KeyError as exc:
            raise ValueError(f"ring_fill {index} references an unknown atom") from exc
        alpha = _number(fill.get("alpha"), f"ring_fill {index} alpha")
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"ring_fill {index} alpha must be from 0 to 1")
        fills.append(
            {
                "atom_ids": atom_ids,
                "points": points,
                "color": _color(fill.get("color"), f"ring_fill {index} color"),
                "alpha": alpha,
            }
        )
    return fills


def _annotation_marks(
    atoms: Mapping[int, Atom],
    annotations: Mapping[int, Mapping[str, int]],
    *,
    mark_distance: float,
) -> list[dict[str, object]]:
    marks: list[dict[str, object]] = []
    for atom_id, annotation in sorted(annotations.items()):
        atom = atoms[atom_id]
        for mark_index, kind in enumerate(annotation_mark_kinds(annotation)):
            direction_x, direction_y = annotation_mark_direction(mark_index)
            dx = direction_x * mark_distance
            dy = direction_y * mark_distance
            marks.append(
                {
                    "kind": kind,
                    "text": None,
                    "atom_id": atom_id,
                    "dx": dx,
                    "dy": dy,
                    "x": atom.x + dx,
                    "y": atom.y + dy,
                }
            )
    return marks


def _atom_annotation(atom: Mapping[str, object], index: int) -> dict[str, int]:
    formal_charge = atom.get("formal_charge", 0)
    radical_electrons = atom.get("radical_electrons", 0)
    if type(formal_charge) is not int:
        raise ValueError(f"atom {index} formal_charge must be an integer")
    if type(radical_electrons) is not int or cast(int, radical_electrons) < 0:
        raise ValueError(
            f"atom {index} radical_electrons must be a nonnegative integer"
        )
    if (
        abs(cast(int, formal_charge)) + cast(int, radical_electrons)
        > MAX_ELECTRONIC_MARKS_PER_ATOM
    ):
        raise ValueError(
            f"atom {index} may have at most {MAX_ELECTRONIC_MARKS_PER_ATOM} electronic marks"
        )
    annotation: dict[str, int] = {}
    if formal_charge:
        annotation["formal_charge"] = cast(int, formal_charge)
    if radical_electrons:
        annotation["radical_electrons"] = cast(int, radical_electrons)
    return annotation


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a JSON object")
    return cast(Mapping[str, object], value)


def _list(value: object, name: str, *, maximum: int) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    if len(value) > maximum:
        raise ValueError(f"{name} may contain at most {maximum} entries")
    return cast(list[object], value)


def _keys(
    value: Mapping[str, object],
    *,
    required: frozenset[str],
    allowed: frozenset[str] | set[str],
    name: str,
) -> None:
    if not required <= set(value) or not set(value) <= set(allowed):
        raise ValueError(f"{name} has missing or unknown keys")


def _id(value: object, name: str) -> int:
    if type(value) is not int or cast(int, value) < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return cast(int, value)


def _number(value: object, name: str) -> float:
    if not is_document_number(value):
        raise ValueError(f"{name} must be a finite JSON-safe number")
    return float(cast(Any, value))


def _color(value: object, name: str) -> str:
    if not is_hex_color(value):
        raise ValueError(f"{name} must be hexadecimal")
    return cast(str, value)


def _point(value: object, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be a two-number array")
    return _number(value[0], f"{name} x"), _number(value[1], f"{name} y")


__all__ = [
    "COMPOSITION_FORMAT",
    "COMPOSITION_VERSION",
    "MAX_ATOMS",
    "MAX_BONDS",
    "MAX_SCENE_ITEMS",
    "compose_document_state",
]
