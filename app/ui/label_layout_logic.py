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

from dataclasses import dataclass
from typing import Callable

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


__all__ = [
    "SUB_SCALE",
    "SUB_DROP_RATIO",
    "SUPER_RISE_RATIO",
    "LabelRun",
    "PlacedRun",
    "LabelLayout",
    "parse_atom_label",
    "place_runs",
]
