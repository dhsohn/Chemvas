"""Text and scene-annotation layout, validation, and geometry."""

import math

from .arrow_label import (
    LABEL_SYNTAX_HINT,
    arrow_label_html,
    arrow_label_normal,
    arrow_label_position,
    cleaned_arrow_labels,
    parse_arrow_label,
)
from .brackets import (
    BRACKET_MENU_SPECS,
    DEFAULT_BRACKET_KIND,
    normalized_bracket_kind,
)
from .label_layout import (
    ATOM_LABEL_DOCUMENT_MARGIN,
    ATOM_LABEL_HIT_PADDING_RATIO,
    SUB_SCALE,
    LabelLayout,
    LabelRun,
    atom_label_presentation,
    attachment_anchor_token,
    attachment_group_at_end,
    hydride_display_text,
    hydride_hydrogen_text,
    label_bounding_rect,
    mark_dimensions,
    parse_atom_label,
    place_hydride_stack,
    place_runs,
    reversed_display_text,
    split_hydride_label,
    uses_compact_label_hit_shape,
)
from .note_html import MAX_NOTE_HTML_CHARS, sanitize_note_html
from .transforms import flip_annotation, rotate_annotation


def _radial_orbital_lobes(
    angles_and_phases: tuple[tuple[float, bool], ...],
    rx: float,
    ry: float,
) -> tuple[tuple[float, float, float, float, bool], ...]:
    return tuple(
        (
            math.cos(math.radians(angle)) * 1.1,
            math.sin(math.radians(angle)) * 1.1,
            rx,
            ry,
            positive,
        )
        for angle, positive in angles_and_phases
    )


# Ellipse lobes per orbital kind as (dx, dy, rx, ry, positive_phase), all in
# units of the base radius around the placement center. mo_antibonding also
# paints a nodal line between its lobes (materialized by the drawing adapter).
_ORBITAL_LOBE_SPECS: dict[str, tuple[tuple[float, float, float, float, bool], ...]] = {
    "s": ((0.0, 0.0, 1.0, 1.0, True),),
    "p": ((-1.0, 0.0, 1.0, 0.7, True), (1.0, 0.0, 1.0, 0.7, False)),
    "sp": ((-1.2, 0.0, 1.2, 0.7, True), (0.6, 0.0, 0.6, 0.4, False)),
    "sp2": _radial_orbital_lobes(
        ((0.0, True), (120.0, True), (240.0, True)), 0.75, 0.5
    ),
    "sp3": _radial_orbital_lobes(
        ((45.0, True), (135.0, True), (225.0, True), (315.0, True)), 0.7, 0.45
    ),
    "d": _radial_orbital_lobes(
        ((45.0, True), (135.0, False), (225.0, True), (315.0, False)), 0.7, 0.45
    ),
    "mo_bonding": ((-1.0, 0.0, 1.0, 0.7, True), (1.0, 0.0, 1.0, 0.7, True)),
    "mo_antibonding": ((-1.0, 0.0, 1.0, 0.7, True), (1.0, 0.0, 1.0, 0.7, False)),
}


def orbital_geometry(
    center: tuple[float, float], kind: str, bond_length: float
) -> tuple[
    list[tuple[float, float, float, float, bool]],
    tuple[float, float, float, float] | None,
]:
    radius = bond_length * 0.35
    ellipses = []
    for dx, dy, rx_factor, ry_factor, positive in _ORBITAL_LOBE_SPECS.get(kind, ()):
        cx = center[0] + dx * radius
        cy = center[1] + dy * radius
        rx, ry = rx_factor * radius, ry_factor * radius
        ellipses.append((cx - rx, cy - ry, rx * 2, ry * 2, positive))
    node = (
        (center[0], center[1] - radius * 0.8, center[0], center[1] + radius * 0.8)
        if kind == "mo_antibonding"
        else None
    )
    return ellipses, node


__all__ = [
    "ATOM_LABEL_DOCUMENT_MARGIN",
    "ATOM_LABEL_HIT_PADDING_RATIO",
    "BRACKET_MENU_SPECS",
    "DEFAULT_BRACKET_KIND",
    "LABEL_SYNTAX_HINT",
    "MAX_NOTE_HTML_CHARS",
    "SUB_SCALE",
    "LabelLayout",
    "LabelRun",
    "arrow_label_html",
    "arrow_label_normal",
    "arrow_label_position",
    "atom_label_presentation",
    "attachment_anchor_token",
    "attachment_group_at_end",
    "cleaned_arrow_labels",
    "flip_annotation",
    "hydride_display_text",
    "hydride_hydrogen_text",
    "label_bounding_rect",
    "mark_dimensions",
    "normalized_bracket_kind",
    "orbital_geometry",
    "parse_arrow_label",
    "parse_atom_label",
    "place_hydride_stack",
    "place_runs",
    "reversed_display_text",
    "rotate_annotation",
    "sanitize_note_html",
    "split_hydride_label",
    "uses_compact_label_hit_shape",
]
