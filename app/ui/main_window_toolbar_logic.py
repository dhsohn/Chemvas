from __future__ import annotations

from collections.abc import Callable

from ui.main_window_config import TEMPLATE_ENTRY_SPECS


BOND_STYLE_BY_LABEL: dict[str, tuple[str, int]] = {
    "Single": ("single", 1),
    "Double": ("double", 2),
    "Triple": ("triple", 3),
    "Bold": ("bold_in", 1),
    "Wedge": ("wedge", 1),
    "Hash": ("hash", 1),
    "Dotted": ("dotted", 1),
}

ARROW_TYPE_BY_LABEL: dict[str, str] = {
    "Reaction": "reaction",
    "Equilibrium": "equilibrium",
    "Resonance": "resonance",
    "Curved Single": "curved_single",
    "Curved Double": "curved_double",
    "Inhibition": "inhibit",
    "Dotted": "dotted",
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
    "Default": (1.2, 0.3),
    "ACS": (1.2, 0.3),
    "Bold": (2.2, 0.4),
    "Fine": (0.8, 0.25),
}

TOOL_DISPLAY_NAMES: dict[str, str] = {
    "select": "Select",
    "bond": "Bond",
    "text": "Atom / Text",
    "benzene": "Ring",
    "arrow": "Arrow",
    "ts_bracket": "TS Bracket",
    "template": "Template",
    "orbital": "Orbital",
    "perspective": "Perspective",
    "color": "Color",
    "mark": "Mark",
}


def build_template_entries(
    begin_ring_template_insert: Callable[[int], None],
) -> list[tuple[str, Callable[[], None]]]:
    return [
        (
            label,
            lambda ring_size=ring_size, style=style: begin_ring_template_insert(
                ring_size,
                style=style,
            ),
        )
        for label, ring_size, style in TEMPLATE_ENTRY_SPECS
    ]


def bond_style_from_label(value: str) -> tuple[str, int]:
    return BOND_STYLE_BY_LABEL.get(value, ("single", 1))


def arrow_type_from_label(value: str) -> str:
    return ARROW_TYPE_BY_LABEL.get(value, "reaction")


def orbital_type_from_label(value: str) -> str:
    return ORBITAL_TYPE_BY_LABEL.get(value, "s")


def arrow_preset_from_label(value: str) -> tuple[float, float]:
    return ARROW_PRESET_BY_LABEL.get(value, (1.2, 0.3))


def tool_display_name(tool: str) -> str:
    return TOOL_DISPLAY_NAMES.get(tool, tool.capitalize())


def tool_action_key_for_canvas_state(
    active_tool: str | None,
    *,
    active_bond_style: str,
    mark_kind: str,
) -> str | None:
    if active_tool == "bond":
        return "bond"
    if active_tool == "mark":
        return f"mark_{mark_kind}"
    return active_tool


__all__ = [
    "arrow_preset_from_label",
    "arrow_type_from_label",
    "bond_style_from_label",
    "build_template_entries",
    "orbital_type_from_label",
    "tool_action_key_for_canvas_state",
    "tool_display_name",
]
