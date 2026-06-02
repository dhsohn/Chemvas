from __future__ import annotations


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
    ("benzene", "Ring", "benzene", "icon_ring", "Ring / Benzene (ChemDraw: J)"),
    ("arrow", "Arrow", "arrow", "icon_arrow", "Arrow (ChemDraw: E)"),
    ("ts_bracket", "TS Bracket", "ts_bracket", "icon_ts_bracket", "TS Bracket (ChemDraw: Shift+G)"),
    (
        "perspective",
        "Perspective",
        "perspective",
        "icon_perspective",
        "Perspective Rotation (ChemDraw: Alt+D, Shift+drag locks X/Y)",
    ),
]

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

LEFT_TOOLBAR_ACTION_ORDER: list[str] = [
    "select",
    "perspective",
    "bond",
    "bond_bold",
    "bond_wedge",
    "bond_hash",
    "bond_dotted",
    "text",
    "mark_plus",
    "mark_minus",
    "mark_radical",
    "benzene",
]

ARROW_MENU_ITEMS = ARROW_MENU_SPECS
ARROW_PRESET_ITEMS = ARROW_PRESET_SPECS
ACS_COLOR_PALETTE = COLOR_PALETTE_SPECS


__all__ = [
    "ACS_COLOR_PALETTE",
    "BOND_TOOL_ACTION_SPECS",
    "ARROW_MENU_ITEMS",
    "ARROW_PRESET_ITEMS",
    "ARROW_MENU_SPECS",
    "ARROW_PRESET_SPECS",
    "COLOR_PALETTE_SPECS",
    "LEFT_TOOLBAR_ACTION_ORDER",
    "MARK_TOOL_ACTION_SPECS",
    "TEMPLATE_ENTRY_SPECS",
    "TOOL_ACTION_SPECS",
]
