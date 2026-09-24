"""Text and scene-annotation layout, validation, and geometry."""

from .arrow_label import arrow_label_html, arrow_label_normal, parse_arrow_label
from .brackets import (
    BRACKET_MENU_SPECS,
    DEFAULT_BRACKET_KIND,
    normalized_bracket_kind,
)
from .label_layout import (
    SUB_SCALE,
    LabelLayout,
    LabelRun,
    attachment_anchor_token,
    attachment_group_at_end,
    hydride_display_text,
    hydride_hydrogen_text,
    parse_atom_label,
    place_hydride_stack,
    place_runs,
    reversed_display_text,
    split_hydride_label,
)
from .note_html import MAX_NOTE_HTML_CHARS, sanitize_note_html

__all__ = [
    "BRACKET_MENU_SPECS",
    "DEFAULT_BRACKET_KIND",
    "MAX_NOTE_HTML_CHARS",
    "SUB_SCALE",
    "LabelLayout",
    "LabelRun",
    "arrow_label_html",
    "arrow_label_normal",
    "attachment_anchor_token",
    "attachment_group_at_end",
    "hydride_display_text",
    "hydride_hydrogen_text",
    "normalized_bracket_kind",
    "parse_arrow_label",
    "parse_atom_label",
    "place_hydride_stack",
    "place_runs",
    "reversed_display_text",
    "sanitize_note_html",
    "split_hydride_label",
]
