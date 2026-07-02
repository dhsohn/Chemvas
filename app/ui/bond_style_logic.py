from __future__ import annotations

DOUBLE_STYLE_DEFAULT = "double"
DOUBLE_STYLE_CENTER = "double_center"
DOUBLE_STYLE_OUTER = "double_outer"
DOTTED_DOUBLE_STYLE_DEFAULT = "dotted_double"
DOTTED_DOUBLE_STYLE_OUTER = "dotted_double_outer"

DOUBLE_STYLE_SEQUENCE = (
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_OUTER,
)
DOTTED_DOUBLE_STYLE_SEQUENCE = (
    DOTTED_DOUBLE_STYLE_DEFAULT,
    DOTTED_DOUBLE_STYLE_OUTER,
)

PLAIN_DOUBLE_STYLES = frozenset(DOUBLE_STYLE_SEQUENCE)
DOTTED_DOUBLE_STYLES = frozenset(DOTTED_DOUBLE_STYLE_SEQUENCE)
BOLD_BOND_STYLES = frozenset({"bold", "bold_in", "bold_out"})
STANDARD_BOND_STYLES = frozenset(
    {
        "single",
        "triple",
        *DOUBLE_STYLE_SEQUENCE,
    }
)


def is_plain_double_bond_style(style: str, order: int) -> bool:
    if order != 2:
        return False
    return style in PLAIN_DOUBLE_STYLES or style == "single"


def normalized_plain_double_style(style: str, order: int) -> str:
    if is_plain_double_bond_style(style, order) and style in PLAIN_DOUBLE_STYLES:
        return style
    return DOUBLE_STYLE_DEFAULT


def is_dotted_double_bond_style(style: str, order: int) -> bool:
    return order == 2 and style in DOTTED_DOUBLE_STYLES


def dotted_double_variant_for_style(style: str, order: int) -> str | None:
    if is_dotted_double_bond_style(style, order):
        return style
    if not is_plain_double_bond_style(style, order):
        return None
    variant = normalized_plain_double_style(style, order)
    if variant == DOUBLE_STYLE_DEFAULT:
        return DOTTED_DOUBLE_STYLE_DEFAULT
    if variant == DOUBLE_STYLE_OUTER:
        return DOTTED_DOUBLE_STYLE_OUTER
    return None


def base_plain_double_style_for_dotted_variant(style: str, order: int) -> str:
    variant = dotted_double_variant_for_style(style, order)
    if variant == DOTTED_DOUBLE_STYLE_OUTER:
        return DOUBLE_STYLE_OUTER
    return DOUBLE_STYLE_DEFAULT


def cycle_plain_bond_style(
    style: str,
    order: int,
    *,
    allow_double_variants: bool = True,
) -> tuple[str, int]:
    if style == "single" and order == 1:
        return DOUBLE_STYLE_DEFAULT, 2
    if is_plain_double_bond_style(style, order):
        if not allow_double_variants:
            return "single", 1
        current = normalized_plain_double_style(style, order)
        index = DOUBLE_STYLE_SEQUENCE.index(current)
        if index + 1 < len(DOUBLE_STYLE_SEQUENCE):
            return DOUBLE_STYLE_SEQUENCE[index + 1], 2
        return "single", 1
    if style == "triple" or order == 3:
        return "single", 1
    return "single", 1


def style_for_existing_bond_overlay(
    existing_style: str,
    existing_order: int,
    requested_style: str,
    requested_order: int,
) -> tuple[str, int]:
    if requested_style == "dotted" and requested_order == 1:
        dotted_style = dotted_double_variant_for_style(existing_style, existing_order)
        if dotted_style is not None:
            return dotted_style, 2
        if existing_order == 2:
            return existing_style, existing_order
        return "dotted", 1
    if (
        requested_style == "single"
        and requested_order == 1
        and is_plain_double_bond_style(existing_style, existing_order)
    ):
        return "triple", 3
    return requested_style, requested_order


__all__ = [
    "BOLD_BOND_STYLES",
    "DOTTED_DOUBLE_STYLES",
    "DOTTED_DOUBLE_STYLE_DEFAULT",
    "DOTTED_DOUBLE_STYLE_OUTER",
    "DOTTED_DOUBLE_STYLE_SEQUENCE",
    "DOUBLE_STYLE_CENTER",
    "DOUBLE_STYLE_DEFAULT",
    "DOUBLE_STYLE_OUTER",
    "DOUBLE_STYLE_SEQUENCE",
    "PLAIN_DOUBLE_STYLES",
    "STANDARD_BOND_STYLES",
    "base_plain_double_style_for_dotted_variant",
    "cycle_plain_bond_style",
    "dotted_double_variant_for_style",
    "is_dotted_double_bond_style",
    "is_plain_double_bond_style",
    "normalized_plain_double_style",
    "style_for_existing_bond_overlay",
]
