from __future__ import annotations

from collections.abc import Callable, Mapping
from html import escape
from typing import Any, cast

from chemvas.domain.document import (
    ARROW_LABEL_SIDES,
    CANVAS_FILE_VERSION,
    MAX_ARROW_LABEL_CHARS,
    MAX_DOCUMENT_IMAGE_BYTES,
    MAX_DOCUMENT_IMAGE_PIXELS,
    MAX_DOCUMENT_IMAGES,
    SETTINGS_KEYS,
    VALID_ARROW_KINDS,
    VALID_BOND_ORDERS,
    VALID_BOND_STYLES,
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    image_state_from_bytes,
    is_document_number,
    is_hex_color,
    serialize_model_state,
    serialize_settings,
)
from chemvas.domain.document.state import (
    VALID_SHAPE_KINDS,
    VALID_SHAPE_STROKES,
    VALID_TS_BRACKET_KINDS,
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
MAX_NOTE_RUNS = 256
MAX_ELECTRONIC_MARKS_PER_ATOM = 8
ELECTRONIC_MARK_DISTANCE_BOND_FRACTION = 0.55
_ROOT_REQUIRED = frozenset(("format", "version", "atoms", "bonds"))
_ROOT_ALLOWED = _ROOT_REQUIRED | {
    "notes",
    "arrows",
    "shapes",
    "ring_fills",
    "ts_brackets",
    "settings",
    "images",
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
_NOTE_REQUIRED = frozenset(("x", "y"))
_NOTE_ALLOWED = _NOTE_REQUIRED | {"text", "runs", "style"}
_NOTE_STYLE_ALLOWED = frozenset(
    ("font_size", "font_weight", "italic", "color", "vertical_align")
)
_ARROW_REQUIRED = frozenset(("kind", "start", "end"))
_ARROW_ALLOWED = _ARROW_REQUIRED | {"control", "double", "labels", "color"}
_SHAPE_REQUIRED = frozenset(
    ("shape_kind", "left", "top", "right", "bottom", "stroke_style")
)
_SHAPE_ALLOWED = _SHAPE_REQUIRED | {"fill", "fill_alpha"}
_RING_REQUIRED = frozenset(("atom_ids", "color", "alpha"))
_TS_BRACKET_REQUIRED = frozenset(("bracket_kind", "left", "top", "right", "bottom"))
_DEFAULT_BOND_STYLE = {1: "single", 2: "double", 3: "triple"}
_IMAGE_REQUIRED = frozenset(("source", "x", "y"))
_IMAGE_ALLOWED = _IMAGE_REQUIRED | {"width", "height", "opacity", "lock_aspect"}


def compose_document_state(
    composition: object,
    *,
    image_source_reader: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
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
    ts_brackets = _ts_brackets(root.get("ts_brackets", []))
    images = _images(root.get("images", []), image_source_reader)

    model = MoleculeModel(atoms=atoms, bonds=bonds, atom_annotations=annotations)
    marks = _annotation_marks(
        model,
        annotations,
        mark_distance=(
            float(cast("Any", settings["bond_length_px"]))
            * ELECTRONIC_MARK_DISTANCE_BOND_FRACTION
        ),
    )
    state: dict[str, Any] = {
        "model": serialize_model_state(model),
        "ring_fills": ring_fills,
        "notes": notes,
        "marks": marks,
        "arrows": arrows,
        "ts_brackets": ts_brackets,
        "shapes": shapes,
        "orbitals": [],
        "settings": settings,
        "last_smiles_input": None,
    }
    if images:
        state["images"] = images
    build_document_payload(state, CANVAS_FILE_VERSION)
    inspect_components(state)
    return state


def _images(
    value: object,
    source_reader: Callable[[str], bytes] | None,
) -> list[dict[str, object]]:
    images: list[dict[str, object]] = []
    byte_count = 0
    pixel_count = 0
    for index, raw_image in enumerate(
        _list(value, "images", maximum=MAX_DOCUMENT_IMAGES)
    ):
        name = f"image {index}"
        image = _mapping(raw_image, name)
        _keys(image, required=_IMAGE_REQUIRED, allowed=_IMAGE_ALLOWED, name=name)
        source = image.get("source")
        if not isinstance(source, str) or not source.strip() or "\x00" in source:
            raise ValueError(f"{name} source must be a non-empty file path")
        _text(source, f"{name} source")
        if "://" in source or source.lower().startswith("data:"):
            raise ValueError(f"{name} source must be a local file path, not a URL")
        if source_reader is None:
            raise ValueError("Image compositions require an image_source_reader.")
        x = _number(image.get("x"), f"{name} x")
        y = _number(image.get("y"), f"{name} y")
        width = _number(image["width"], f"{name} width") if "width" in image else None
        height = (
            _number(image["height"], f"{name} height") if "height" in image else None
        )
        opacity = _number(image.get("opacity", 1.0), f"{name} opacity")
        lock_aspect = image.get("lock_aspect", True)
        if type(lock_aspect) is not bool:
            raise ValueError(f"{name} lock_aspect must be a boolean")
        try:
            data = source_reader(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{name} source: {exc}") from exc
        byte_count += len(data)
        if byte_count > MAX_DOCUMENT_IMAGE_BYTES:
            raise ValueError("Combined image bytes exceed the 64 MiB document limit.")
        try:
            image_state = image_state_from_bytes(
                data,
                x=x,
                y=y,
                width=width,
                height=height,
                opacity=opacity,
                lock_aspect=lock_aspect,
            )
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from exc
        pixel_count += cast("int", image_state["pixel_width"]) * cast(
            "int", image_state["pixel_height"]
        )
        if pixel_count > MAX_DOCUMENT_IMAGE_PIXELS:
            raise ValueError(
                "Combined image pixels exceed the 100 million document limit."
            )
        images.append(image_state)
    return images


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
            element=element.strip(),
            x=_number(atom.get("x"), f"atom {index} x"),
            y=_number(atom.get("y"), f"atom {index} y"),
            color=color,
            explicit_label=cast("bool", explicit_label),
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
        normalized_order = cast("int", order)
        style = bond.get("style", _DEFAULT_BOND_STYLE[normalized_order])
        if not isinstance(style, str) or style not in VALID_BOND_STYLES:
            raise ValueError(f"bond {index} style is not supported")
        if style in {"wedge", "hash"} and normalized_order != 1:
            raise ValueError(f"bond {index} wedge/hash style requires order 1")
        if style == "double_either" and normalized_order != 2:
            raise ValueError(f"bond {index} double_either style requires order 2")
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
        "dict[str, object]",
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
        unknown = sorted(str(key) for key in set(overrides) - SETTINGS_KEYS)
        raise ValueError(f"settings has unknown keys: {unknown}")
    # Composition v1 is a bounded authoring API even though persisted v7
    # documents retain their older, unbounded-above compatibility contract.
    overridden_font_size = overrides.get("text_font_size")
    if type(overridden_font_size) is int and overridden_font_size > 96:
        raise ValueError(
            "Invalid Chemvas file. settings.text_font_size must be an integer from 6 to 96 in compositions."
        )
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
        if ("text" in note) == ("runs" in note):
            raise ValueError(f"note {index} requires exactly one of text or runs")
        state: dict[str, object] = {
            "x": _number(note.get("x"), f"note {index} x"),
            "y": _number(note.get("y"), f"note {index} y"),
        }
        if "runs" in note:
            state["text"], state["html"] = _note_runs(note, index)
        else:
            text = _text(note.get("text"), f"note {index} text")
            state["text"] = text
            if "style" in note:
                state["html"] = _styled_note_html(text, note.get("style"), index)
        notes.append(state)
    return notes


def _styled_note_html(text: str, value: object, index: int) -> str:
    declarations = _note_style_css(value, f"note {index}")
    escaped_text = _note_text_html(text)
    return _safe_note_html(
        f'<p><span style="{declarations}">{escaped_text}</span></p>', index
    )


def _note_style_css(value: object, name: str) -> str:
    style = _mapping(value, f"{name} style")
    if not style or not set(style) <= _NOTE_STYLE_ALLOWED:
        raise ValueError(f"{name} style must use supported non-empty keys")
    declarations: list[str] = []
    if "font_size" in style:
        size = style["font_size"]
        if type(size) is not int or not 6 <= cast("int", size) <= 96:
            raise ValueError(f"{name} font_size must be an integer from 6 to 96")
        declarations.append(f"font-size:{size}pt")
    if "font_weight" in style:
        weight = style["font_weight"]
        if type(weight) is not int or weight not in range(100, 1000, 100):
            raise ValueError(f"{name} font_weight must be 100 through 900")
        declarations.append(f"font-weight:{weight}")
    if "italic" in style:
        italic = style["italic"]
        if type(italic) is not bool:
            raise ValueError(f"{name} italic must be a boolean")
        declarations.append("font-style:italic" if italic else "font-style:normal")
    if "color" in style:
        declarations.append(f"color:{_color(style['color'], f'{name} color')}")
    if "vertical_align" in style:
        alignment = style["vertical_align"]
        if not isinstance(alignment, str) or alignment not in {
            "baseline",
            "sub",
            "super",
        }:
            raise ValueError(f"{name} vertical_align must be baseline, sub, or super")
        declarations.append(f"vertical-align:{alignment}")
    return ";".join(declarations)


def _note_runs(note: Mapping[str, object], index: int) -> tuple[str, str]:
    runs = _list(note["runs"], f"note {index} runs", maximum=MAX_NOTE_RUNS)
    if not runs:
        raise ValueError(f"note {index} runs must not be empty")
    texts: list[str] = []
    spans: list[str] = []
    previous_ended_with_cr = False
    for run_index, raw in enumerate(runs):
        name = f"note {index} run {run_index}"
        run = _mapping(raw, name)
        _keys(run, required=frozenset(("text",)), allowed={"text", "style"}, name=name)
        text = _text(run.get("text"), f"{name} text")
        texts.append(text)
        # A CRLF belongs to the concatenated source, even across empty runs.
        html_text = (
            text[1:] if previous_ended_with_cr and text.startswith("\n") else text
        )
        if text:
            previous_ended_with_cr = text.endswith("\r")
        span = _note_text_html(html_text)
        if "style" in run:
            css = _note_style_css(run["style"], name)
            span = f'<span style="{css}">{span}</span>'
        spans.append(span)
    html = "".join(spans)
    if "style" in note:
        css = _note_style_css(note["style"], f"note {index}")
        html = f'<span style="{css}">{html}</span>'
    # The sanitizer supplies Qt's paragraph whitespace policy; preserve spaces
    # across run boundaries rather than letting HTML collapse the source text.
    return "".join(texts), _safe_note_html(f"<p>{html}</p>", index)


def _note_text_html(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return escape(normalized, quote=False).replace("\n", "<br>")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(
            f"{name} must contain valid Unicode (no lone surrogates)"
        ) from exc
    return value


def _safe_note_html(raw_html: str, index: int) -> str:
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
            raise ValueError(
                f"arrow {index} kind is not supported; choose from {sorted(VALID_ARROW_KINDS)}"
            )
        state: dict[str, object] = {
            "kind": kind,
            "start": list(_point(arrow.get("start"), f"arrow {index} start")),
            "end": list(_point(arrow.get("end"), f"arrow {index} end")),
        }
        if "control" in arrow:
            if kind not in {"curved_single", "curved_double"}:
                raise ValueError(
                    f"arrow {index} control is only supported for curved arrows"
                )
            state["control"] = list(_point(arrow["control"], f"arrow {index} control"))
        if "double" in arrow:
            if type(arrow["double"]) is not bool:
                raise ValueError(f"arrow {index} double must be a boolean")
            state["double"] = arrow["double"]
        if kind in {"curved_single", "curved_double"}:
            double = kind == "curved_double"
            if "double" in arrow and arrow["double"] != double:
                raise ValueError(f"arrow {index} double must agree with kind")
            state["double"] = double
        if "color" in arrow:
            state["color"] = _color(arrow["color"], f"arrow {index} color")
        if "labels" in arrow:
            labels = _mapping(arrow["labels"], f"arrow {index} labels")
            if not labels or not set(labels) <= ARROW_LABEL_SIDES:
                raise ValueError(
                    f"arrow {index} labels must contain above and/or below; "
                    "omit labels for an unlabelled arrow"
                )
            for side, text in labels.items():
                if type(text) is not str or not text.strip():
                    raise ValueError(
                        f"arrow {index} labels.{side} must be a non-empty string; "
                        "omit unused sides"
                    )
                if len(text) > MAX_ARROW_LABEL_CHARS:
                    raise ValueError(
                        f"arrow {index} labels.{side} exceeds "
                        f"{MAX_ARROW_LABEL_CHARS} characters"
                    )
            state["labels"] = dict(labels)
        arrows.append(state)
    return arrows


def _ts_brackets(value: object) -> list[dict[str, object]]:
    brackets: list[dict[str, object]] = []
    for index, raw in enumerate(_list(value, "ts_brackets", maximum=MAX_SCENE_ITEMS)):
        name = f"ts_bracket {index}"
        bracket = _mapping(raw, name)
        _keys(
            bracket,
            required=_TS_BRACKET_REQUIRED,
            allowed=_TS_BRACKET_REQUIRED,
            name=name,
        )
        kind = bracket.get("bracket_kind")
        if not isinstance(kind, str) or kind not in VALID_TS_BRACKET_KINDS:
            raise ValueError(f"{name} bracket_kind is not supported")
        state: dict[str, object] = {"kind": "ts_bracket", "bracket_kind": kind}
        for key in ("left", "top", "right", "bottom"):
            state[key] = _number(bracket.get(key), f"{name} {key}")
        brackets.append(state)
    return brackets


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
    model: MoleculeModel,
    annotations: Mapping[int, Mapping[str, int]],
    *,
    mark_distance: float,
) -> list[dict[str, object]]:
    marks: list[dict[str, object]] = []
    for atom_id, annotation in sorted(annotations.items()):
        atom = model.atoms[atom_id]
        for mark_index, kind in enumerate(annotation_mark_kinds(annotation)):
            direction_x, direction_y = annotation_mark_direction(
                mark_index, model=model, atom_id=atom_id
            )
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
    if type(radical_electrons) is not int or cast("int", radical_electrons) < 0:
        raise ValueError(
            f"atom {index} radical_electrons must be a nonnegative integer"
        )
    if (
        abs(cast("int", formal_charge)) + cast("int", radical_electrons)
        > MAX_ELECTRONIC_MARKS_PER_ATOM
    ):
        raise ValueError(
            f"atom {index} may have at most {MAX_ELECTRONIC_MARKS_PER_ATOM} electronic marks"
        )
    annotation: dict[str, int] = {}
    if formal_charge:
        annotation["formal_charge"] = cast("int", formal_charge)
    if radical_electrons:
        annotation["radical_electrons"] = cast("int", radical_electrons)
    return annotation


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a JSON object")
    return cast("Mapping[str, object]", value)


def _list(value: object, name: str, *, maximum: int) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    if len(value) > maximum:
        raise ValueError(f"{name} may contain at most {maximum} entries")
    return cast("list[object]", value)


def _keys(
    value: Mapping[str, object],
    *,
    required: frozenset[str],
    allowed: frozenset[str] | set[str],
    name: str,
) -> None:
    if not required <= set(value) or not set(value) <= set(allowed):
        missing = sorted(required - set(value))
        unknown = sorted(str(key) for key in set(value) - set(allowed))
        raise ValueError(
            f"{name} has missing or unknown keys: missing={missing}, unknown={unknown}"
        )


def _id(value: object, name: str) -> int:
    if type(value) is not int or cast("int", value) < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return cast("int", value)


def _number(value: object, name: str) -> float:
    if not is_document_number(value):
        raise ValueError(f"{name} must be a finite JSON-safe number")
    return float(cast("Any", value))


def _color(value: object, name: str) -> str:
    if not is_hex_color(value):
        raise ValueError(f"{name} must be hexadecimal")
    return cast("str", value)


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
