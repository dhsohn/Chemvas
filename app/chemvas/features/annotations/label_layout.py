"""Pure typographic layout for atom labels.

This module is the single source of truth for how a raw atom-label string is
split into typographic runs (normal / subscript / superscript) and how those
runs are positioned. It is intentionally free of any Qt dependency so the rules
can be unit-tested without a running QApplication, and so that both on-screen
painting and (later) vector export can consume the exact same geometry.

Display-only: callers pass the raw label text that is already stored on the
model (e.g. ``"CH3"``, ``"CO2Me"``, ``"NH4+"``). Parsing never mutates that
stored text; it only decides how to draw it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.features.graph import connected_atom_unit_vectors

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.domain.document import MoleculeModel

# A label like "NH", "OH", "NH2", "CH3": one element symbol followed by an
# optional run of hydrogens. These get directional layout so the element sits on
# the atom and the hydrogens point away from the bonds (H outside a ring).
_HYDRIDE_RE = re.compile(r"^([A-Z][a-z]?)(?:H(\d*))?$")


def uses_compact_label_hit_shape(text: str) -> bool:
    text = text.strip()
    if len(text) == 1:
        return text.isalpha() and text.upper() == text
    if len(text) == 2:
        return (
            text[0].isalpha()
            and text[0].upper() == text[0]
            and text[1].isalpha()
            and text[1].lower() == text[1]
        )
    return False


def split_hydride_label(text: str) -> tuple[str, int] | None:
    """Split ``"NH2"`` -> ``("N", 2)``; return ``None`` if not element+hydrogens.

    A bare element (``"O"``, ``"Cl"``) yields hydrogen count 0. Multi-part
    labels (``"CO2Me"``) return ``None`` and keep their plain centred layout.
    """
    match = _HYDRIDE_RE.match(text or "")
    if match is None:
        return None
    element = match.group(1)
    digits = match.group(2)
    if digits is None:
        h_count = 0
    elif digits == "":
        h_count = 1
    else:
        h_count = int(digits)
    return element, h_count


def hydride_display_text(element: str, h_count: int, *, face_left: bool) -> str:
    """Order the element and its hydrogens so the element is nearest the bonds.

    ``face_left`` puts the hydrogens on the left (``"HN"``/``"H2N"``), used when
    the bonds approach from the right; otherwise they trail the element
    (``"NH"``/``"NH2"``).
    """
    if h_count <= 0:
        return element
    return (
        hydride_hydrogen_text(h_count) + element
        if face_left
        else element + hydride_hydrogen_text(h_count)
    )


def hydride_hydrogen_text(h_count: int) -> str:
    """The hydrogen part of a hydride label: ``"H"``, ``"H2"``, ..."""
    return "H" if h_count == 1 else f"H{h_count}"


# An element-like token at one extreme of a multi-part label: an uppercase
# letter with an optional lowercase one ("C", "Ph", "Me"). Purely typographic —
# no chemical validation is implied.
_LEADING_TOKEN_RE = re.compile(r"^[A-Z][a-z]?")
_TRAILING_TOKEN_RE = re.compile(r"[A-Z][a-z]?$")


def attachment_anchor_token(text: str, *, at_end: bool) -> str | None:
    """The anchorable token at the start or end of a multi-part label.

    ``"CF3"`` -> ``"C"`` from the start, ``"Ph3P"`` -> ``"P"`` from the end.
    Returns ``None`` when that extreme is not an element-like token (``"CF3"``
    from the end stops at the subscript digit) or when the token is the whole
    label (a bare element keeps its centred layout).
    """
    source = text or ""
    match = (_TRAILING_TOKEN_RE if at_end else _LEADING_TOKEN_RE).search(source)
    if match is None:
        return None
    token = match.group(0)
    if token == source:
        return None
    return token


# One typographic atom group of a reversible label: an element-like token plus
# its subscript digits ("F3", "Ph", "O2").
_LABEL_GROUP_RE = re.compile(r"[A-Z][a-z]?\d*")


def _label_groups(text: str) -> list[str] | None:
    """The label as element-like groups, or ``None`` if it has other content."""
    source = text or ""
    groups = _LABEL_GROUP_RE.findall(source)
    if not groups or "".join(groups) != source:
        return None
    return groups


def _is_hydrogen_group(group: str) -> bool:
    return group[0] == "H" and (len(group) == 1 or group[1:].isdigit())


def attachment_group_at_end(text: str) -> bool | None:
    """Which end of a cleanly tokenized label holds its attachment group.

    Two syntactic signals decide: hydrogens are never the attachment when the
    other end is a heavy atom ("HO" and "H3C" attach at the far end), and a
    subscripted terminal group cannot be the attachment while an unsubscripted
    one can ("Ph3P" and "F3C" attach at their trailing atom, "SiMe3" at its
    leading one). Returns ``None`` when neither signal applies ("OMe" vs "MeO"
    are syntactically identical — callers need chemistry knowledge, e.g. the
    alias table, to tell them apart) or when the label does not tokenize
    cleanly into element-like groups (parentheses, charges, hyphens).
    """
    groups = _label_groups(text)
    if groups is None:
        return None
    first, last = groups[0], groups[-1]
    if first == last:
        return None
    if _is_hydrogen_group(first) != _is_hydrogen_group(last):
        return _is_hydrogen_group(first)
    first_subscripted = first[-1].isdigit()
    last_subscripted = last[-1].isdigit()
    if first_subscripted != last_subscripted:
        return first_subscripted
    return None


def reversed_display_text(text: str) -> str | None:
    """The label with its atom groups in reverse order: ``"CF3"`` -> ``"F3C"``.

    Lets a label face bonds arriving from the side its typed order cannot
    serve, ChemDraw-style (``"PPh3"`` on the left of a bond renders
    ``"Ph3P"``). Only labels that tokenize cleanly into element-like groups
    reverse (``"CO2Me"`` -> ``"MeO2C"``); parentheses, charge signs, hyphens or
    a lowercase start return ``None``, as does a label whose reversal would not
    change anything. Display-only: callers never store the reversed text.
    """
    groups = _label_groups(text)
    if groups is None:
        return None
    flipped = "".join(reversed(groups))
    if flipped == (text or ""):
        return None
    return flipped


# A subscript/superscript glyph is drawn at this fraction of the base font size.
SUB_SCALE = 0.72
_SUBSCRIPT_DIGITS = dict(zip("₀₁₂₃₄₅₆₇₈₉", "0123456789", strict=True))
# Vertical offsets, expressed as a fraction of the base em (ascent + descent).
SUB_DROP_RATIO = 0.20
SUPER_RISE_RATIO = 0.34
# Air between the two lines of a stacked hydride ("N" over "H"), as a
# fraction of the capital height. Lines are pitched from glyph ink, not from
# the font's ascent/descent box, so the hydrogen sits close under the element.
STACK_GAP_RATIO = 0.25


@dataclass(frozen=True)
class LabelRun:
    """A contiguous slice of the label with a single typographic role."""

    text: str
    role: str  # "normal" | "sub" | "super"


@dataclass(frozen=True)
class PlacedRun:
    """A run positioned relative to the content box top-left (pre-margin)."""

    text: str
    role: str
    point_size: float
    x: float  # left edge advance from content origin
    baseline: float  # baseline y measured down from content top


@dataclass(frozen=True)
class LabelLayout:
    runs: tuple[PlacedRun, ...]
    width: float
    height: float
    has_typography: bool


def parse_atom_label(text: str) -> list[LabelRun]:
    """Split ``text`` into typographic runs (subscripts only, for this slice).

    Rules:
      * A digit immediately following a letter, ``)`` or ``]`` is a subscript;
        consecutive digits stay in the same subscript run (``C10`` -> ``C`` + ₁₀).
      * A leading digit stays normal (isotope typography is out of scope).
      * Unicode subscript digits use ordinary digit glyphs in a subscript run,
        including at the start of a label. Their built-in size and baseline
        must not be applied again on top of the run's typography.
      * Everything else, including ``+``/``-`` signs, stays normal. Folding a
        formal charge into a superscript is intentionally deferred to the charge
        slice -- inline charge magnitude (``Ca2+`` vs ``H2O``) is ambiguous to
        parse, and charges live as separate mark items today. ``place_runs``
        already supports the ``"super"`` role for when that slice lands.
    """
    source = text or ""
    if not source:
        return []

    runs: list[LabelRun] = []
    buf = ""
    buf_role = "normal"
    prev = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            runs.append(LabelRun(buf, buf_role))
            buf = ""

    for ch in source:
        if ch in _SUBSCRIPT_DIGITS:
            ch = _SUBSCRIPT_DIGITS[ch]
            role = "sub"
        elif ch.isdigit() and prev and (prev.isalpha() or prev in (")", "]")):
            role = "sub"
        elif ch.isdigit() and prev.isdigit() and buf_role == "sub":
            role = "sub"
        else:
            role = "normal"
        if role != buf_role:
            flush()
            buf_role = role
        buf += ch
        prev = ch
    flush()

    return runs


def place_runs(
    runs: list[LabelRun],
    *,
    measure: Callable[[str, float], float],
    ascent: float,
    descent: float,
    base_point_size: float,
    sub_scale: float = SUB_SCALE,
    sub_drop_ratio: float = SUB_DROP_RATIO,
    super_rise_ratio: float = SUPER_RISE_RATIO,
) -> LabelLayout:
    """Position ``runs`` into a content box.

    ``measure(text, point_size)`` returns the advance width of ``text`` at the
    given point size; injecting it keeps this function Qt-free and testable.
    Coordinates are relative to the content box top-left (caller adds any margin).
    """
    if not runs:
        return LabelLayout(runs=(), width=0.0, height=0.0, has_typography=False)

    em = ascent + descent
    sub_drop = em * sub_drop_ratio
    super_rise = em * super_rise_ratio
    sub_ascent = ascent * sub_scale
    sub_descent = descent * sub_scale

    # First pass: advances and vertical extents relative to a baseline at y=0.
    widths: list[float] = []
    tops: list[float] = []
    bottoms: list[float] = []
    sizes: list[float] = []
    offsets: list[float] = []
    for run in runs:
        if run.role == "normal":
            size = base_point_size
            top, bottom, offset = -ascent, descent, 0.0
        elif run.role == "sub":
            size = base_point_size * sub_scale
            top, bottom, offset = (
                sub_drop - sub_ascent,
                sub_drop + sub_descent,
                sub_drop,
            )
        else:  # super
            size = base_point_size * sub_scale
            top = -super_rise - sub_ascent
            bottom = -super_rise + sub_descent
            offset = -super_rise
        sizes.append(size)
        offsets.append(offset)
        widths.append(measure(run.text, size))
        tops.append(top)
        bottoms.append(bottom)

    content_top = min(tops)
    content_bottom = max(bottoms)
    height = content_bottom - content_top
    baseline_from_top = -content_top

    placed: list[PlacedRun] = []
    x = 0.0
    for run, width, size, offset in zip(runs, widths, sizes, offsets, strict=False):
        placed.append(
            PlacedRun(
                text=run.text,
                role=run.role,
                point_size=size,
                x=x,
                baseline=baseline_from_top + offset,
            )
        )
        x += width

    has_typography = any(run.role != "normal" for run in runs)
    return LabelLayout(
        runs=tuple(placed),
        width=x,
        height=height,
        has_typography=has_typography,
    )


def place_hydride_stack(
    element: str,
    h_count: int,
    *,
    hydrogens_below: bool,
    measure: Callable[[str, float], float],
    ascent: float,
    descent: float,
    base_point_size: float,
    cap_height: float | None = None,
    gap_ratio: float = STACK_GAP_RATIO,
) -> tuple[LabelLayout, tuple[float, float, float, float]]:
    """Stack the hydrogens on their own line under (or over) the element.

    Used when the open side around an atom is vertical, matching ChemDraw's
    "N over H" rendering at a two-bond vertex. Each line is centred on the
    other. The lower line's capitals start ``gap_ratio`` capital heights below
    the upper line's lowest ink (its baseline, or a subscript's baseline), so
    the stack is as tight as the glyphs allow rather than one font box per
    line; ``cap_height`` defaults to ``ascent`` when the caller cannot measure
    it. Returns the combined layout plus the element glyph box
    ``(x, y, width, height)`` inside it, so callers can keep anchoring the atom
    and trimming bonds to the element exactly like the horizontal layouts do.
    """
    element_line = place_runs(
        parse_atom_label(element),
        measure=measure,
        ascent=ascent,
        descent=descent,
        base_point_size=base_point_size,
    )
    hydrogen_line = place_runs(
        parse_atom_label(hydride_hydrogen_text(h_count)),
        measure=measure,
        ascent=ascent,
        descent=descent,
        base_point_size=base_point_size,
    )

    width = max(element_line.width, hydrogen_line.width)
    element_x = (width - element_line.width) / 2.0
    hydrogen_x = (width - hydrogen_line.width) / 2.0
    # Qt reports a zero capital height for a few fonts; fall back to the
    # ascent rather than collapsing both lines onto one baseline.
    cap = ascent if cap_height is None or cap_height <= 0.0 else cap_height
    upper, lower = (
        (element_line, hydrogen_line)
        if hydrogens_below
        else (hydrogen_line, element_line)
    )
    pitch = cap + cap * gap_ratio + _ink_below_baseline(upper)
    upper_baseline = _line_baseline(upper)
    lower_y = upper_baseline + pitch - _line_baseline(lower)
    element_y = 0.0 if hydrogens_below else lower_y
    hydrogen_y = lower_y if hydrogens_below else 0.0

    runs: list[PlacedRun] = []
    for line, line_x, line_y in (
        (element_line, element_x, element_y),
        (hydrogen_line, hydrogen_x, hydrogen_y),
    ):
        for run in line.runs:
            runs.append(
                PlacedRun(
                    text=run.text,
                    role=run.role,
                    point_size=run.point_size,
                    x=run.x + line_x,
                    baseline=run.baseline + line_y,
                )
            )
    layout = LabelLayout(
        runs=tuple(runs),
        width=width,
        height=max(element_y + element_line.height, hydrogen_y + hydrogen_line.height),
        # Even a subscript-free stack ("N" over "H") needs custom run painting.
        has_typography=True,
    )
    element_box = (element_x, element_y, element_line.width, element_line.height)
    return layout, element_box


def _line_baseline(line: LabelLayout) -> float:
    """The baseline shared by a line's normal runs, measured from its top."""
    return next(run.baseline for run in line.runs if run.role == "normal")


def _ink_below_baseline(line: LabelLayout) -> float:
    """How far a line's ink reaches below its baseline.

    Capitals and hydrogens sit on the baseline; a subscript digit sits on its
    own dropped baseline, so only that drop counts.
    """
    baseline = _line_baseline(line)
    return max(
        (run.baseline - baseline for run in line.runs if run.role == "sub"),
        default=0.0,
    )


__all__ = [
    "STACK_GAP_RATIO",
    "SUB_DROP_RATIO",
    "SUB_SCALE",
    "SUPER_RISE_RATIO",
    "LabelLayout",
    "LabelRun",
    "PlacedRun",
    "atom_label_presentation",
    "attachment_anchor_token",
    "attachment_group_at_end",
    "hydride_display_text",
    "hydride_hydrogen_text",
    "parse_atom_label",
    "place_hydride_stack",
    "place_runs",
    "reversed_display_text",
    "split_hydride_label",
]


def _open_direction(vectors: list[tuple[float, float]]) -> tuple[float, float]:
    """Direction toward the open side of an atom, for hydride label placement.

    Opposite the vector sum of the bonds (the same negative-sum rule the bond
    sprout uses at a two-bond vertex). When the bonds cancel out (a straight
    C-NH-C), fall back to the perpendicular of the first bond, flipped so its
    dominant component is positive -- a flat chain stacks its H underneath
    regardless of bond insertion order, like ChemDraw.
    """
    sum_x = sum(dx for dx, _ in vectors)
    sum_y = sum(dy for _, dy in vectors)
    if math.hypot(sum_x, sum_y) > 1e-6:
        return -sum_x, -sum_y
    if vectors:
        perp_x, perp_y = vectors[0][1], -vectors[0][0]
        if (perp_y if abs(perp_y) >= abs(perp_x) else perp_x) < 0.0:
            perp_x, perp_y = -perp_x, -perp_y
        return perp_x, perp_y
    return 1.0, 0.0


def atom_label_presentation(
    model: MoleculeModel, atom_id: int, text: str
) -> tuple[str, str | None, bool, bool | None]:
    # Element+hydrogen labels ("NH", "OH", "NH2", "CH3") anchor on the element
    # with the hydrogens pointing away from the bonds; other multi-part
    # labels ("CF3", "Ph3P") anchor on the token facing the bonds. Returns
    # (display_text, anchor_element, anchor_at_end, hydrogens_below);
    # hydrogens_below is None for the horizontal layouts and picks the
    # stacked line side otherwise.
    split = split_hydride_label(text)
    if split is None:
        return _token_anchor_layout(model, atom_id, text)
    element, h_count = split
    if h_count <= 0:
        return _token_anchor_layout(model, atom_id, text)
    atom = model.atoms.get(atom_id)
    if atom is not None and atom.explicit_label:
        return text, None, False, None
    # Put the hydrogens on the open side of the atom, quantised to the
    # dominant axis. A vertical open side (both bonds of a vertex rising,
    # or a flat C-NH-C chain) stacks the H on its own line under/over the
    # element, ChemDraw-style, instead of forcing a horizontal layout.
    vectors = connected_atom_unit_vectors(model, atom_id)
    open_x, open_y = _open_direction(vectors)
    if abs(open_y) > abs(open_x):
        hydrogens_below = open_y > 0.0
        v_direction = 1.0 if hydrogens_below else -1.0
        # Mirror of the horizontal guard below: keep full-box clearance when
        # a bond runs almost straight along the hydrogen direction.
        if any(dy * v_direction > 0.95 for _, dy in vectors):
            return text, None, False, None
        return text, element, False, hydrogens_below
    face_left = open_x < 0.0
    # Only when a bond runs almost straight along that horizontal direction
    # (within ~18 degrees) would the hydrogens sit on top of it; keep the
    # label centred with full-box clearance there. Ordinary diagonal
    # ring/chain neighbours -- a regular hexagon N-H has bonds near
    # (+-0.866, 0.5) -- stay anchored.
    h_direction = -1.0 if face_left else 1.0
    if any(dx * h_direction > 0.95 for dx, _ in vectors):
        return text, None, False, None
    display = hydride_display_text(element, h_count, face_left=face_left)
    return display, element, face_left, None


def _token_anchor_layout(
    model: MoleculeModel, atom_id: int, text: str
) -> tuple[str, str | None, bool, bool | None]:
    # Multi-part labels ("CF3", "Ph3P", "OMe") anchor on their attachment
    # group, so that glyph sits on the atom and bonds trim to it instead of
    # clearing the whole label box. When the attachment group is typed on
    # the side away from the bonds ("CF3" or "OTs" approached from the
    # right), the display text reverses group-wise ("F3C", "TsO"),
    # ChemDraw-style, without touching the stored label. When the
    # attachment end is unknowable, the token facing the bonds anchors
    # as typed. Known reversible labels retain their attachment anchor
    # even on a vertical open side; an exactly vertical bond preserves the
    # typed order. Unknown or unreversible vertical labels, and a bond
    # running along the label body, keep the centred full-clearance layout.
    vectors = connected_atom_unit_vectors(model, atom_id)
    if not vectors:
        # With no attachment direction there is no chemical reason to
        # reverse the user's text or select one end as the bond anchor.
        return text, None, False, None
    open_x, open_y = _open_direction(vectors)
    # Compact alkyl names have no explicit attachment-carbon glyph and
    # cannot reverse as element groups. Keep their conventional spelling,
    # but align the facing terminal glyph rather than the whole word.
    if text in {"tBu", "t-Bu", "i-Pr"} and abs(open_x) >= 1e-6:
        at_end = open_x < 0.0
        body_direction = -1.0 if at_end else 1.0
        if not any(dx * body_direction > 0.95 for dx, _ in vectors):
            return text, text[-1] if at_end else text[0], at_end, None
    attachment_at_end = _attachment_at_end(text)
    if abs(open_y) > abs(open_x) and (
        attachment_at_end is None or reversed_display_text(text) is None
    ):
        return text, None, False, None
    anchor_at_end = (
        attachment_at_end
        if attachment_at_end is not None and abs(open_x) < 1e-6
        else open_x < 0.0
    )
    display = text
    if attachment_at_end is not None and attachment_at_end != anchor_at_end:
        flipped = reversed_display_text(text)
        if flipped is not None:
            display = flipped
    token = attachment_anchor_token(display, at_end=anchor_at_end)
    if token is None:
        return text, None, False, None
    # Same guard as the horizontal hydride layout: a bond running almost
    # straight along the label body would sit under the text.
    body_direction = -1.0 if anchor_at_end else 1.0
    if any(dx * body_direction > 0.95 for dx, _ in vectors):
        return text, None, False, None
    return display, token, anchor_at_end, None


def _attachment_at_end(text: str) -> bool | None:
    # The alias table is the chemistry authority: its keys are typed
    # attachment-first, so a label matching a key attaches at the start and
    # a label whose group-reversal matches a key ("Ph3P" -> "PPh3", "MeO"
    # -> "OMe") attaches at the end. Unknown labels fall back to the
    # syntactic signals; None means the end is genuinely ambiguous.
    # Generic substituent R is not an expandable molecular alias. Its
    # display still has an unambiguous oxygen attachment in OR / RO.
    if text in {"OR", "RO"}:
        return text == "RO"
    if text in ATOM_ALIAS_DEFINITIONS:
        return False
    flipped = reversed_display_text(text)
    if flipped is not None and flipped in ATOM_ALIAS_DEFINITIONS:
        return True
    return attachment_group_at_end(text)
