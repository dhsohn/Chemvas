from __future__ import annotations

from chemvas.domain.document.schema import VALID_TS_BRACKET_KINDS

DEFAULT_BRACKET_KIND = "square_pair"
# The dagger kinds are glyphs in the document font rather than strokes.
BRACKET_SYMBOLS = {"dagger": "\u2020", "double_dagger": "\u2021"}

BRACKET_MENU_SPECS: list[tuple[str, str]] = [
    ("Square Brackets", "square_pair"),
    ("Parentheses", "parentheses_pair"),
    ("Braces", "braces_pair"),
    ("Double Dagger", "double_dagger"),
    ("Left Square Bracket", "square_left"),
    ("Left Parenthesis", "parenthesis_left"),
    ("Left Brace", "brace_left"),
    ("Dagger", "dagger"),
]


def normalized_bracket_kind(
    value: object, *, default: str = DEFAULT_BRACKET_KIND
) -> str:
    if isinstance(value, str) and value in VALID_TS_BRACKET_KINDS:
        return value
    return default


__all__ = [
    "BRACKET_MENU_SPECS",
    "BRACKET_SYMBOLS",
    "DEFAULT_BRACKET_KIND",
    "bracket_path_commands",
    "bracket_rect_from_points",
    "bracket_stroke_width",
    "bracket_symbol_layout",
    "normalized_bracket_kind",
]


def bracket_path_commands(
    bounds: tuple[float, float, float, float], kind: str, bond_length: float
) -> list[tuple[str, tuple[float, ...]]]:
    """Original bracket strokes; Qt and SVG materialize these same commands."""
    x, top, width, height = bounds
    bottom = top + height
    hook = min(width * 0.18, bond_length * 0.55)
    hook = max(hook, bond_length * 0.28)
    commands: list[tuple[str, tuple[float, ...]]] = []
    if kind not in {
        "square_pair",
        "square_left",
        "parentheses_pair",
        "parenthesis_left",
        "braces_pair",
        "brace_left",
    }:
        return commands
    for left in (True, False) if kind.endswith("_pair") else (True,):
        outer_x = x if left else x + width
        inner_x = outer_x + hook if left else outer_x - hook
        if kind in {"square_pair", "square_left"}:
            commands.extend(
                [
                    ("M", (inner_x, top)),
                    ("L", (outer_x, top)),
                    ("L", (outer_x, bottom)),
                    ("L", (inner_x, bottom)),
                ]
            )
        elif kind in {"parentheses_pair", "parenthesis_left"}:
            middle = top + height / 2
            control = height * 0.22
            commands.extend(
                [
                    ("M", (inner_x, top)),
                    (
                        "C",
                        (
                            outer_x,
                            top + control,
                            outer_x,
                            middle - control,
                            outer_x,
                            middle,
                        ),
                    ),
                    (
                        "C",
                        (
                            outer_x,
                            middle + control,
                            outer_x,
                            bottom - control,
                            inner_x,
                            bottom,
                        ),
                    ),
                ]
            )
        else:
            mid = top + height / 2
            quarter = height / 4.0
            sign = 1.0 if left else -1.0
            waist_x = outer_x + sign * hook * 0.18
            shoulder_x = outer_x + sign * hook * 0.62
            commands.extend(
                [
                    ("M", (inner_x, top)),
                    (
                        "C",
                        (
                            outer_x,
                            top,
                            outer_x,
                            top + quarter * 0.55,
                            waist_x,
                            top + quarter,
                        ),
                    ),
                    (
                        "C",
                        (
                            shoulder_x,
                            top + quarter * 1.32,
                            shoulder_x,
                            mid - quarter * 0.35,
                            outer_x,
                            mid,
                        ),
                    ),
                    (
                        "C",
                        (
                            shoulder_x,
                            mid + quarter * 0.35,
                            shoulder_x,
                            bottom - quarter * 1.32,
                            waist_x,
                            bottom - quarter,
                        ),
                    ),
                    (
                        "C",
                        (
                            outer_x,
                            bottom - quarter * 0.55,
                            outer_x,
                            bottom,
                            inner_x,
                            bottom,
                        ),
                    ),
                ]
            )
    return commands


def bracket_stroke_width(bond_line_width: float) -> float:
    return max(0.8, bond_line_width * 0.58)


def bracket_symbol_layout(
    bounds: tuple[float, float, float, float], bond_length: float
) -> tuple[int, float, float]:
    """Pixel size and baseline anchor of a dagger glyph centred in ``bounds``."""
    x, y, width, height = bounds
    size = min(height * 0.62, bond_length * 1.35)
    # A box 25 tall asks for exactly 15.5 px. Moving a bracket is arithmetic
    # on its edges, which can leave the height one float step short of 25;
    # rounding that noise away first keeps the glyph the size it was.
    pixels = max(10, round(round(size, 6)))
    return pixels, x + width / 2 - pixels * 0.2, y + height / 2 + pixels * 0.36


def bracket_rect_from_points(
    start: tuple[float, float], end: tuple[float, float], bond_length: float
) -> tuple[float, float, float, float]:
    width, height = end[0] - start[0], end[1] - start[1]
    x, y = start
    if width < 0:
        x += width
        width = -width
    if height < 0:
        y += height
        height = -height
    min_width, min_height = bond_length * 1.8, bond_length * 2.4
    if width < 4.0 and height < 4.0:
        return (
            start[0] - min_width / 2,
            start[1] - min_height / 2,
            min_width,
            min_height,
        )
    cx, cy = x + width / 2, y + height / 2
    width, height = max(width, min_width), max(height, min_height)
    return cx - width / 2, cy - height / 2, width, height
