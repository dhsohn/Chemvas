from __future__ import annotations

from ui.bracket_types import BRACKET_MENU_SPECS

ARROW_MENU_SPECS: list[tuple[str, str]] = [
    ("Reaction", "reaction"),
    ("Equilibrium", "equilibrium"),
    ("Resonance", "resonance"),
    ("Curved Single", "curved_single"),
    ("Curved Double", "curved_double"),
    ("Inhibition", "inhibit"),
    ("Dotted", "dotted"),
]

ARROW_PRESET_SPECS: list[str] = ["Default", "Bold", "Fine"]

COLOR_PALETTE_SPECS: list[tuple[str, str]] = [
    ("Black", "#000000"),
    ("Gray", "#4a4a4a"),
    ("Red", "#c00000"),
    ("Blue", "#1f5eff"),
    ("Green", "#2e8b57"),
    ("Purple", "#6a2ea6"),
    ("Orange", "#c77c00"),
]

TEMPLATE_ENTRY_SPECS: list[tuple[str, int, str]] = [
    ("Benzene", 6, "benzene"),
    ("Cyclopropane", 3, "regular"),
    ("Cyclobutane", 4, "regular"),
    ("Cyclopentane", 5, "regular"),
    ("Cyclohexane (Chair)", 6, "chair"),
    ("Cycloheptane", 7, "regular"),
    ("Cyclooctane", 8, "regular"),
]

TOOL_ACTION_SPECS: list[tuple[str, str, str, str, str]] = [
    ("select", "Select", "select", "icon_select", "Select / Marquee (ChemDraw: Space)"),
    ("bond", "Bond", "bond", "icon_bond", "Bond (ChemDraw: X)"),
    ("text", "Atom", "text", "icon_text", "Atom / Text (ChemDraw: T)"),
    ("mark", "Mark", "mark", "icon_mark", "Charge / Radical"),
    ("benzene", "Ring", "benzene", "icon_ring", "Ring / Benzene (ChemDraw: J)"),
    ("color", "Color", "color", "icon_color", "Color"),
    ("arrow", "Arrow", "arrow", "icon_arrow", "Arrow (ChemDraw: E)"),
    ("ts_bracket", "Brackets", "ts_bracket", "icon_ts_bracket", "Brackets (ChemDraw: Shift+G)"),
    (
        "perspective",
        "Perspective",
        "perspective",
        "icon_perspective",
        "Perspective Rotation (ChemDraw: Alt+D, Shift+drag locks X/Y)",
    ),
]

RING_FILL_TOOL_ACTION_SPEC: tuple[str, str, str, str] = (
    "ring_fill",
    "Ring Fill",
    "icon_ring_fill",
    "Ring Fill",
)

BOND_TOOL_ACTION_SPECS: list[tuple[str, str, str, str, str]] = [
    ("bond_bold", "Bold Bond", "Bold", "icon_bond_bold", "Bold Bond (Bond Hotkey: B)"),
    ("bond_wedge", "Wedge", "Wedge", "icon_bond_wedge", "Wedge Bond (Bond Hotkey: W)"),
    ("bond_hash", "Hash", "Hash", "icon_bond_hash", "Hash Bond (Bond Hotkey: Shift+H)"),
    ("bond_dotted", "Dotted Bond", "Dotted", "icon_bond_dotted", "Dotted Bond"),
]

MARK_TOOL_ACTION_SPECS: list[tuple[str, str, str, str, str]] = [
    ("mark_plus", "Charge +", "plus", "icon_mark_plus", "Charge + (Atom Hotkey: +)"),
    ("mark_minus", "Charge -", "minus", "icon_mark_minus", "Charge - (Atom Hotkey: -)"),
    ("mark_radical", "Radical", "radical", "icon_mark_radical", "Radical"),
]

TOOLBAR_TRANSFORM_TOOL_GROUP: tuple[str, ...] = ("select", "perspective")

TOOLBAR_TOOL_GROUPS: list[tuple[str, ...]] = [
    ("text", "bond", "mark", "benzene", "arrow", "ts_bracket"),
    ("color", "ring_fill"),
]

TOOLBAR_TOOL_ACTION_ORDER: list[str] = [
    *TOOLBAR_TRANSFORM_TOOL_GROUP,
    *(action_key for group in TOOLBAR_TOOL_GROUPS for action_key in group),
]

ARROW_MENU_ITEMS = ARROW_MENU_SPECS
ARROW_PRESET_ITEMS = ARROW_PRESET_SPECS
ACS_COLOR_PALETTE = COLOR_PALETTE_SPECS


__all__ = [
    "ACS_COLOR_PALETTE",
    "BOND_TOOL_ACTION_SPECS",
    "BRACKET_MENU_SPECS",
    "ARROW_MENU_ITEMS",
    "ARROW_PRESET_ITEMS",
    "ARROW_MENU_SPECS",
    "ARROW_PRESET_SPECS",
    "COLOR_PALETTE_SPECS",
    "MARK_TOOL_ACTION_SPECS",
    "RING_FILL_TOOL_ACTION_SPEC",
    "TEMPLATE_ENTRY_SPECS",
    "TOOL_ACTION_SPECS",
    "TOOLBAR_TOOL_ACTION_ORDER",
    "TOOLBAR_TOOL_GROUPS",
    "TOOLBAR_TRANSFORM_TOOL_GROUP",
]
