"""The Chemvas document schema: file versions, state keys, valid kinds and limits."""

from __future__ import annotations

from typing import Any

StateDict = dict[Any, Any]


CHEMVAS_FILE_TYPE = "chemvas"


# New documents use this version. Supported durable readers are independent:
# advancing the writer must not retire v7 (docs/DOCUMENT_COMPATIBILITY.md).
CANVAS_FILE_VERSION = 8


SUPPORTED_FILE_VERSIONS = frozenset((7, 8))


DOCUMENT_SCHEMA_READERS = {(8, 1): "0.18.0"}


DOCUMENT_SCHEMAS = {8: 1}


CANVAS_STATE_KEYS = frozenset(
    (
        "model",
        "ring_fills",
        "notes",
        "marks",
        "arrows",
        "ts_brackets",
        "shapes",
        "orbitals",
        "settings",
        "last_smiles_input",
    )
)


OPTIONAL_CANVAS_STATE_KEYS = frozenset(
    ("perspective", "groups", "calculation_plan", "images")
)


_GROUPABLE_STATE_ITEM_KEYS = frozenset(
    ("notes", "marks", "arrows", "ts_brackets", "shapes", "orbitals", "images")
)


# QFont's integer point-size constructor is exposed through a signed C++ int.
_QT_INT_MAX = 2**31 - 1


# Derived glyph sizes include a 1.35x TS label; leave room in Qt's signed int.
MAX_BOND_LENGTH_PX = _QT_INT_MAX // 2


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


VALID_SHEET_SIZES = frozenset(("A4",))


VALID_SHEET_ORIENTATIONS = frozenset(("landscape", "portrait"))


VALID_BOND_ORDERS = frozenset((1, 2, 3))


VALID_BOND_STYLES = frozenset(
    (
        "single",
        "double",
        "double_center",
        "double_outer",
        "double_either",
        "triple",
        "wedge",
        "hash",
        "dotted",
        "dotted_double",
        "dotted_double_outer",
        "bold_in",
        "bold_center",
        "bold_out",
    )
)


# Lines are headless members of the arrow family: same start/end schema and
# the same ``arrows`` list, so every arrow consumer (move, delete, selection,
# clipboard, groups, export) handles them without a second item kind.
VALID_LINE_KINDS = frozenset(("line", "line_dashed", "line_wavy", "line_bold"))


# Arc arrows are circular arcs through the drag endpoints; the kind carries
# the sweep and the side of the drag direction the arc bulges toward, so a
# mirror flip only has to swap that suffix.
ARC_KIND_SWEEPS: dict[str, tuple[float, bool]] = {
    "arc_90_left": (90.0, True),
    "arc_90_right": (90.0, False),
    "arc_180_left": (180.0, True),
    "arc_180_right": (180.0, False),
    "arc_270_left": (270.0, True),
    "arc_270_right": (270.0, False),
}


VALID_ARC_KINDS = frozenset(ARC_KIND_SWEEPS)


# Curved arrows carry a control point and get a third, control handle; every
# other arrow kind is defined by its two endpoints alone.
VALID_CURVED_ARROW_KINDS = frozenset(("curved_single", "curved_double"))


def mirrored_arc_kind(kind: str) -> str:
    if kind.endswith("_left"):
        return kind[: -len("_left")] + "_right"
    if kind.endswith("_right"):
        return kind[: -len("_right")] + "_left"
    return kind


VALID_ARROW_KINDS = (
    frozenset(
        (
            "arrow",
            "equilibrium",
            "equilibrium_forward",
            "equilibrium_reverse",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
        )
    )
    | VALID_LINE_KINDS
    | VALID_ARC_KINDS
)


VALID_EQUILIBRIUM_KINDS = frozenset(
    kind for kind in VALID_ARROW_KINDS if kind.startswith("equilibrium")
)


# An arrow may carry one short label on each side (rate constants such as
# k_1 above and k_-1 below); the text keeps the label mini-syntax, not HTML.
ARROW_LABEL_SIDES = frozenset(("above", "below"))


MAX_ARROW_LABEL_CHARS = 200


# Marks are short electronic annotations, not paragraphs. Bound glyph-path
# construction before any GUI, render, or layout-check consumer sees the text.
MAX_MARK_TEXT_CHARS = 200


VALID_MARK_KINDS = frozenset(
    ("plus", "minus", "circled_plus", "circled_minus", "radical")
)


VALID_TS_BRACKET_KINDS = frozenset(
    (
        "square_pair",
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


CLIPBOARD_SELECTION_VERSION = 3


SUPPORTED_CLIPBOARD_VERSIONS = frozenset((2, 3))


CLIPBOARD_SELECTION_REQUIRED_KEYS = frozenset(
    (
        "format",
        "version",
        "atoms",
        "bonds",
        "rings",
        "marks",
        "scene_items",
    )
)


CLIPBOARD_SELECTION_PAYLOAD_KEYS = CLIPBOARD_SELECTION_REQUIRED_KEYS | {
    "perspective",
    "groups",
}


_SHAPE_STATE_BASE_KEYS = frozenset(
    ("kind", "left", "top", "right", "bottom", "shape_kind", "stroke_style")
)


__all__ = [
    "ARC_KIND_SWEEPS",
    "ARROW_LABEL_SIDES",
    "CANVAS_FILE_VERSION",
    "CANVAS_STATE_KEYS",
    "CHEMVAS_FILE_TYPE",
    "CLIPBOARD_SELECTION_PAYLOAD_KEYS",
    "CLIPBOARD_SELECTION_REQUIRED_KEYS",
    "CLIPBOARD_SELECTION_VERSION",
    "DOCUMENT_SCHEMAS",
    "DOCUMENT_SCHEMA_READERS",
    "MAX_ARROW_LABEL_CHARS",
    "MAX_BOND_LENGTH_PX",
    "MAX_MARK_TEXT_CHARS",
    "OPTIONAL_CANVAS_STATE_KEYS",
    "SETTINGS_KEYS",
    "SUPPORTED_CLIPBOARD_VERSIONS",
    "SUPPORTED_FILE_VERSIONS",
    "VALID_ARC_KINDS",
    "VALID_ARROW_KINDS",
    "VALID_ATOM_ANNOTATION_KEYS",
    "VALID_BOND_ORDERS",
    "VALID_BOND_STYLES",
    "VALID_CURVED_ARROW_KINDS",
    "VALID_EQUILIBRIUM_KINDS",
    "VALID_LINE_KINDS",
    "VALID_MARK_KINDS",
    "VALID_ORBITAL_KINDS",
    "VALID_SHAPE_KINDS",
    "VALID_SHAPE_STROKES",
    "VALID_SHEET_ORIENTATIONS",
    "VALID_SHEET_SIZES",
    "VALID_TS_BRACKET_KINDS",
    "StateDict",
    "mirrored_arc_kind",
]
