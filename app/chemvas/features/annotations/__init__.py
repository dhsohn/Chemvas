"""Text and scene-annotation layout, validation, and geometry."""

from .brackets import (
    BRACKET_KIND_VALUES,
    BRACKET_MENU_SPECS,
    DEFAULT_BRACKET_KIND,
    LEGACY_TS_BRACKET_KIND,
    normalized_bracket_kind,
    restored_bracket_kind,
)
from .label_layout import (
    SUB_SCALE,
    LabelLayout,
    LabelRun,
    hydride_display_text,
    hydride_hydrogen_text,
    parse_atom_label,
    place_hydride_stack,
    place_runs,
    split_hydride_label,
)
from .note_html import MAX_NOTE_HTML_CHARS, sanitize_note_html
from .shape_geometry import (
    DEFAULT_SHAPE_KIND,
    DEFAULT_STROKE_STYLE,
    SHAPE_KINDS,
    STROKE_STYLES,
    normalized_shape_kind,
    normalized_stroke_style,
    pen_style_for_stroke,
    shape_path,
)

__all__ = [
    "BRACKET_KIND_VALUES",
    "BRACKET_MENU_SPECS",
    "DEFAULT_BRACKET_KIND",
    "DEFAULT_SHAPE_KIND",
    "DEFAULT_STROKE_STYLE",
    "LEGACY_TS_BRACKET_KIND",
    "MAX_NOTE_HTML_CHARS",
    "SHAPE_KINDS",
    "STROKE_STYLES",
    "SUB_SCALE",
    "LabelLayout",
    "LabelRun",
    "hydride_display_text",
    "hydride_hydrogen_text",
    "normalized_bracket_kind",
    "normalized_shape_kind",
    "normalized_stroke_style",
    "parse_atom_label",
    "pen_style_for_stroke",
    "place_hydride_stack",
    "place_runs",
    "restored_bracket_kind",
    "sanitize_note_html",
    "shape_path",
    "split_hydride_label",
]
