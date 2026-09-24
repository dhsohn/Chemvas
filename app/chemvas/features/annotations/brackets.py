from __future__ import annotations

from chemvas.domain.document.schema import VALID_TS_BRACKET_KINDS

DEFAULT_BRACKET_KIND = "square_pair"

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
    "DEFAULT_BRACKET_KIND",
    "normalized_bracket_kind",
]
