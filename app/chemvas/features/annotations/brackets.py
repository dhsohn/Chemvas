from __future__ import annotations

DEFAULT_BRACKET_KIND = "square_pair"
LEGACY_TS_BRACKET_KIND = "square_pair_double_dagger"

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

BRACKET_KIND_VALUES = frozenset(
    {
        DEFAULT_BRACKET_KIND,
        LEGACY_TS_BRACKET_KIND,
        "parentheses_pair",
        "braces_pair",
        "double_dagger",
        "square_left",
        "parenthesis_left",
        "brace_left",
        "dagger",
    }
)


def normalized_bracket_kind(
    value: object, *, default: str = DEFAULT_BRACKET_KIND
) -> str:
    if isinstance(value, str) and value in BRACKET_KIND_VALUES:
        return value
    return default


def restored_bracket_kind(value: object) -> str:
    return normalized_bracket_kind(value, default=LEGACY_TS_BRACKET_KIND)


__all__ = [
    "BRACKET_KIND_VALUES",
    "BRACKET_MENU_SPECS",
    "DEFAULT_BRACKET_KIND",
    "LEGACY_TS_BRACKET_KIND",
    "normalized_bracket_kind",
    "restored_bracket_kind",
]
