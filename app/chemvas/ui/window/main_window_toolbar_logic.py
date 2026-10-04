from __future__ import annotations

from chemvas.ui.window.main_window_config import TOOL_HINTS

BOND_STYLE_BY_LABEL: dict[str, tuple[str, int]] = {
    "Single": ("single", 1),
    "Double": ("double", 2),
    "Triple": ("triple", 3),
    "Bold": ("bold_in", 1),
    "Wedge": ("wedge", 1),
    "Hash": ("hash", 1),
    "Dotted": ("dotted", 1),
}

ORBITAL_TYPE_BY_LABEL: dict[str, str] = {
    "s": "s",
    "p": "p",
    "sp": "sp",
    "sp2": "sp2",
    "sp3": "sp3",
    "d": "d",
    "MO bonding": "mo_bonding",
    "MO antibonding": "mo_antibonding",
}

ARROW_PRESET_BY_LABEL: dict[str, tuple[float, float]] = {
    "Default": (1.5, 0.3),
    "ACS": (1.2, 0.3),
    "Bold": (2.2, 0.4),
    "Fine": (0.8, 0.25),
}

TOOL_DISPLAY_NAMES: dict[str, str] = {
    "select": "Select",
    "delete": "Eraser",
    "bond": "Bond",
    "text": "Atom",
    "note": "Text",
    "benzene": "Ring",
    "arrow": "Arrow",
    "line": "Line",
    "ts_bracket": "Brackets",
    "shape": "Shape",
    "orbital": "Orbital",
    "perspective": "Perspective",
    "color": "Color",
    "ring_fill": "Ring Fill",
    "mark": "Mark",
}


def bond_style_from_label(value: str) -> tuple[str, int]:
    return BOND_STYLE_BY_LABEL.get(value, ("single", 1))


def orbital_type_from_label(value: str) -> str:
    return ORBITAL_TYPE_BY_LABEL.get(value, "s")


def arrow_preset_from_label(value: str) -> tuple[float, float]:
    return ARROW_PRESET_BY_LABEL.get(value, ARROW_PRESET_BY_LABEL["Default"])


def tool_display_name(tool: str) -> str:
    return TOOL_DISPLAY_NAMES.get(tool, tool.capitalize())


def tool_hint_text(
    tool: str, *, page: str | None = None, color: str | None = None
) -> str:
    """The status bar hint for the active tool, its page and chosen colour."""
    if page == "ring_fill":
        return TOOL_HINTS["ring_fill"]
    if tool == "color" and color is not None:
        return f"Color: {color} — click an item or choose a swatch"
    return TOOL_HINTS.get(tool, f"{tool_display_name(tool)}: ready")


__all__ = [
    "arrow_preset_from_label",
    "bond_style_from_label",
    "orbital_type_from_label",
    "tool_display_name",
    "tool_hint_text",
]
