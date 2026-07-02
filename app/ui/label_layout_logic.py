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

import re
from collections.abc import Callable
from dataclasses import dataclass

# A label like "NH", "OH", "NH2", "CH3": one element symbol followed by an
# optional run of hydrogens. These get directional layout so the element sits on
# the atom and the hydrogens point away from the bonds (H outside a ring).
_HYDRIDE_RE = re.compile(r"^([A-Z][a-z]?)(?:H(\d*))?$")


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
    return hydride_hydrogen_text(h_count) + element if face_left else element + hydride_hydrogen_text(h_count)


def hydride_hydrogen_text(h_count: int) -> str:
    """The hydrogen part of a hydride label: ``"H"``, ``"H2"``, ..."""
    return "H" if h_count == 1 else f"H{h_count}"

# A subscript/superscript glyph is drawn at this fraction of the base font size.
SUB_SCALE = 0.72
# Vertical offsets, expressed as a fraction of the base em (ascent + descent).
SUB_DROP_RATIO = 0.20
SUPER_RISE_RATIO = 0.34


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
        if ch.isdigit() and prev and (prev.isalpha() or prev in (")", "]")):
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
            top, bottom, offset = sub_drop - sub_ascent, sub_drop + sub_descent, sub_drop
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
) -> tuple[LabelLayout, tuple[float, float, float, float]]:
    """Stack the hydrogens on their own line under (or over) the element.

    Used when the open side around an atom is vertical, matching ChemDraw's
    "N over H" rendering at a two-bond vertex. Each line is centred on the
    other. Returns the combined layout plus the element glyph box
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
    element_y = 0.0 if hydrogens_below else hydrogen_line.height
    hydrogen_y = element_line.height if hydrogens_below else 0.0

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
        height=element_line.height + hydrogen_line.height,
        # Even a subscript-free stack ("N" over "H") needs custom run painting.
        has_typography=True,
    )
    element_box = (element_x, element_y, element_line.width, element_line.height)
    return layout, element_box


__all__ = [
    "SUB_DROP_RATIO",
    "SUB_SCALE",
    "SUPER_RISE_RATIO",
    "LabelLayout",
    "LabelRun",
    "PlacedRun",
    "hydride_display_text",
    "hydride_hydrogen_text",
    "parse_atom_label",
    "place_hydride_stack",
    "place_runs",
    "split_hydride_label",
]
