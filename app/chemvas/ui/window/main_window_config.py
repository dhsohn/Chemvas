from __future__ import annotations

from chemvas.features.annotations import BRACKET_MENU_SPECS

HANDLE_ACCENT_COLOR = "#0d9488"
HANDLE_SCREEN_PX = 8.0

# Magnification policy shared by both UI adapters.
ZOOM_MIN = 0.2
ZOOM_MAX = 5.0
ZOOM_STEP = 1.25
WHEEL_ZOOM_BASE = 1.0015
WHEEL_ANGLE_PER_PIXEL = 2.0

TOOL_HOTKEYS = {
    " ": "select",
    "x": "bond",
    "a": "text",
    "t": "note",
    "e": "arrow",
    "j": "benzene",
}

ARROW_MENU_SPECS: list[tuple[str, str]] = [
    ("Reaction", "reaction"),
    ("Equilibrium", "equilibrium"),
    ("Equilibrium, forward favored", "equilibrium_forward"),
    ("Equilibrium, reverse favored", "equilibrium_reverse"),
    ("Resonance", "resonance"),
    ("Curved Single", "curved_single"),
    ("Curved Double", "curved_double"),
    ("Inhibition", "inhibit"),
    ("Dotted", "dotted"),
    ("Arc 90°", "arc_90_left"),
    ("Arc 180°", "arc_180_left"),
    ("Arc 270°", "arc_270_left"),
]

# Arrow kinds folded into the "More arrows" menu: the equilibrium variants,
# inhibition and the three arcs are drawn far less often than the rest.
MORE_ARROW_KINDS: frozenset[str] = frozenset(
    {
        "equilibrium_forward",
        "equilibrium_reverse",
        "inhibit",
        "arc_90_left",
        "arc_180_left",
        "arc_270_left",
    }
)


LINE_KIND_SPECS = [
    ("line", "Line"),
    ("line_dashed", "Dashed line"),
    ("line_wavy", "Wavy line"),
    ("line_bold", "Bold line"),
]


ARROW_PRESET_SPECS: list[str] = ["Default", "Bold", "Fine"]
ARROW_SLIDER_PAGE_STEP = 10
ARROW_SLIDER_RANGES = {
    "arrow_line_width": (5, 60, 10),
    "arrow_head_scale": (10, 80, 100),
}

RING_FILL_GUIDANCE = "Ring Fill: select a complete ring (all its atoms or bonds) first."

COLOR_TOOL_MESSAGES = {
    "choose": "Color: choose a swatch before painting.",
    "hidden": "Color stored for implicit carbon; hidden carbon vertices stay hidden. "
    "Color the bonds or show an explicit atom label for visible color.",
}

COLOR_PALETTE_SPECS: list[tuple[str, str]] = [
    ("Black", "#000000"),
    ("Gray", "#4a4a4a"),
    ("Yellow", "#f4d06f"),
    ("Blue", "#2f6ed3"),
    ("Red", "#d84a3a"),
    ("Green", "#2e8b57"),
    ("Purple", "#6a2ea6"),
    ("Orange", "#c77c00"),
    ("White", "#ffffff"),
    ("Light Gray", "#bdbdbd"),
    ("Cyan", "#00bcd4"),
    ("Teal", "#008080"),
    ("Navy", "#1b365d"),
    ("Pink", "#e78ac3"),
    ("Magenta", "#c51b7d"),
    ("Brown", "#8c510a"),
]

TEMPLATE_ENTRY_SPECS: list[tuple[str, int, str]] = [
    ("Benzene", 6, "benzene"),
    ("Cyclopropane", 3, "regular"),
    ("Cyclobutane", 4, "regular"),
    ("Cyclopentane", 5, "regular"),
    ("Cyclohexane (Chair)", 6, "chair"),
    ("Cyclohexane (Chair, flipped)", 6, "chair_flip"),
    ("Cycloheptane", 7, "regular"),
    ("Cyclooctane", 8, "regular"),
]

TOOL_ACTION_SPECS: list[tuple[str, str, str, str, str]] = [
    ("select", "Select", "select", "icon_select", "Select / Marquee (Shortcut: Space)"),
    ("bond", "Bond", "bond", "icon_bond", "Bond (Shortcut: X)"),
    ("benzene", "Ring", "benzene", "icon_ring", "Ring / Benzene (Shortcut: J)"),
    ("arrow", "Arrow", "arrow", "icon_arrow", "Arrow (Shortcut: E)"),
    (
        "line",
        "Line",
        "line",
        "icon_line",
        "Line (plain, dashed, wavy, bold; Shift locks the angle)",
    ),
    ("text", "Atom", "text", "icon_text", "Atom (Shortcut: A)"),
    ("note", "Text", "note", "icon_note", "Text / Annotation (Shortcut: T)"),
    ("mark", "Mark", "mark", "icon_mark", "Charge / Radical"),
    (
        "ts_bracket",
        "Brackets",
        "ts_bracket",
        "icon_ts_bracket",
        "Brackets (Shortcut: Shift+T)",
    ),
    (
        "shape",
        "Shape",
        "shape",
        "icon_shape",
        "Shapes / decoration (circle, ellipse, box)",
    ),
    ("orbital", "Orbital", "orbital", "icon_orbital", "Orbital"),
    (
        "delete",
        "Eraser",
        "delete",
        "icon_eraser",
        "Eraser (click or drag to erase)",
    ),
    (
        "perspective",
        "Perspective",
        "perspective",
        "icon_perspective",
        "Perspective Rotation (Shortcut: Alt+D, Shift+drag locks X/Y)",
    ),
    ("color", "Color", "color", "icon_color", "Color"),
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
    (
        "mark_circled_plus",
        "Circled Charge +",
        "circled_plus",
        "icon_mark_circled_plus",
        "Circled charge +",
    ),
    (
        "mark_circled_minus",
        "Circled Charge -",
        "circled_minus",
        "icon_mark_circled_minus",
        "Circled charge -",
    ),
    ("mark_radical", "Radical", "radical", "icon_mark_radical", "Radical"),
]

TOOLBAR_PRIMARY_TOOL_GROUP: tuple[str, ...] = (
    "select",
    "perspective",
)

# "note" is the tool labelled "Text" in the UI; "shape" sits to its right.
TOOLBAR_TOOL_GROUPS: list[tuple[str, ...]] = [
    TOOLBAR_PRIMARY_TOOL_GROUP,
    ("bond", "benzene", "text", "arrow"),
    ("line", "ts_bracket", "mark", "orbital"),
    ("note", "shape", "color", "ring_fill"),
    ("delete",),
]

TOOLBAR_TOOL_ACTION_ORDER: list[str] = [
    *(action_key for group in TOOLBAR_TOOL_GROUPS for action_key in group),
]

TEXT_FONT_FAMILY_CHOICES: tuple[str, ...] = (
    "Arial",
    "Helvetica",
    "Times New Roman",
    "Courier New",
    "Verdana",
)


TOOL_HINTS: dict[str, str] = {
    "select": "Select: double-click arrows/lines for labels",
    "bond": "Bond: click-drag to draw",
    "text": "Atom / Text: click to place label",
    "mark": "Mark: click atom or label",
    "benzene": "Ring: click to place template",
    "arrow": "Arrow: drag to draw; double-click for labels",
    "line": "Line: double-click for labels; Shift locks angle",
    "note": "Text: click to add/edit; Esc to finish",
    "ts_bracket": "Brackets: drag around selection",
    "orbital": "Orbital: click to place",
    "perspective": "Perspective: drag selection to rotate",
    "color": "Color: choose a swatch",
    "ring_fill": "Ring Fill: select a complete ring, then choose a fill color",
}


BOND_ORDER_SEGMENTS = [
    ("Single", "icon_bond", "Single bond (1)"),
    ("Double", "icon_bond_double", "Double bond (2)"),
    ("Triple", "icon_bond_triple", "Triple bond (3)"),
]


BOND_MODIFIERS = [
    ("Bold", "icon_bond_bold", "Bold bond (B)"),
    ("Wedge", "icon_bond_wedge", "Wedge bond (W)"),
    ("Hash", "icon_bond_hash", "Hash bond (Shift+H)"),
    ("Dotted", "icon_bond_dotted", "Dotted bond"),
]


__all__ = [
    "ARROW_MENU_SPECS",
    "ARROW_PRESET_SPECS",
    "ARROW_SLIDER_PAGE_STEP",
    "ARROW_SLIDER_RANGES",
    "BOND_MODIFIERS",
    "BOND_ORDER_SEGMENTS",
    "BOND_TOOL_ACTION_SPECS",
    "BRACKET_MENU_SPECS",
    "COLOR_PALETTE_SPECS",
    "HANDLE_ACCENT_COLOR",
    "HANDLE_SCREEN_PX",
    "MARK_TOOL_ACTION_SPECS",
    "RING_FILL_TOOL_ACTION_SPEC",
    "TEMPLATE_ENTRY_SPECS",
    "TEXT_FONT_FAMILY_CHOICES",
    "TOOLBAR_PRIMARY_TOOL_GROUP",
    "TOOLBAR_TOOL_ACTION_ORDER",
    "TOOLBAR_TOOL_GROUPS",
    "TOOL_ACTION_SPECS",
    "TOOL_HINTS",
]


ATOM_INPUT_SPEC: dict[str, str | int] = {
    "placeholder": "Atom",
    "tooltip": "Atom Symbol",
    "status": "Set the atom symbol used by atom and bond tools",
    "min_width": 60,
    "max_width": 240,
    "max_length": 255,
}

SHAPE_KIND_SPECS = [
    ("circle", "Circle"),
    ("ellipse", "Ellipse"),
    ("rounded_rect", "Rounded rectangle"),
    ("rect", "Rectangle"),
]

SHAPE_STROKE_SPECS = [
    ("solid", "Solid outline"),
    ("dashed", "Dashed outline"),
    ("dotted", "Dotted outline"),
    ("none", "No outline"),
]

ROTATE_ANGLE_RANGE = (-180, 180)
ROTATE_ANGLE_DEFAULT = 15
