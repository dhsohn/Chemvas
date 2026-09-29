from __future__ import annotations

from chemvas.features.annotations import BRACKET_MENU_SPECS
from chemvas.features.rendering import (
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
)

FLIP_ACTION_SPECS = (
    ("flip_horizontal_button", "icon_flip_h", "Flip Horizontal", "Ctrl+Shift+H", True),
    ("flip_vertical_button", "icon_flip_v", "Flip Vertical", "Ctrl+Shift+V", False),
)

# The accent a handle is outlined with, and the fill of one that has taken
# hold of another item's endpoint.
HANDLE_ACCENT_COLOR = "#0d9488"
# Handles are an input affordance, so their size is a distance on screen
# rather than in the document: a corner or endpoint handle is this wide at
# any zoom, and an edge-midpoint resize handle is the smaller one.
HANDLE_SCREEN_PX = 8.0

# View magnification limits and the per-step multiplier shared by the toolbar
# buttons and the Ctrl+= / Ctrl+- shortcuts. Ctrl+wheel uses a finer factor.
ZOOM_MIN = 0.2
ZOOM_MAX = 5.0
ZOOM_STEP = 1.25
WHEEL_ZOOM_BASE = 1.0015
WHEEL_ANGLE_PER_PIXEL = 2.0
# The context bar's bond length field; stepper arrows move one step.
BOND_LENGTH_INPUT_SPEC: dict[str, int | float | str] = {
    "decimals": 1,
    "step": 1.0,
    "tooltip": "Bond length: rescale molecular geometry and attached marks",
    "status_tip": (
        "Set bond length in pixels and rescale molecular geometry and attached marks; "
        "free annotations keep their positions"
    ),
    "up_tooltip": "Increase bond length",
    "down_tooltip": "Decrease bond length",
}
# Fit to Window leaves this fraction of the viewport for the sheet.
FIT_VIEW_MARGIN = 0.92

ORBITAL_PHASE_SPECS = (("Phase Off", False), ("Phase On", True))
ORBITAL_MO_TEXT = {"mo_bonding": "MO+", "mo_antibonding": "MO−"}
ARROW_SLIDER_LABELS = {
    "arrow_line_width": "Arrow line width",
    "arrow_head_scale": "Arrow head size",
}
MOLECULE_INFO_TITLE = "Molecule Info"
REACTION_MAPPING_TITLE = "Reaction Mapping"

# Shift+letter switches to a tool and resets that tool's kind to its default.
SHIFT_TOOL_HOTKEYS = {"T": "ts_bracket", "G": "orbital", "E": "mark"}

TOOL_HOTKEYS = {
    " ": "select",
    "x": "bond",
    "a": "text",
    "t": "note",
    "e": "arrow",
    "j": "benzene",
}

# Right-click positions for a double bond; bold doubles keep their family.
DOUBLE_BOND_CONTEXT_STYLES = (
    ("Inward", DOUBLE_STYLE_DEFAULT),
    ("Centered", DOUBLE_STYLE_CENTER),
    ("Outward", DOUBLE_STYLE_OUTER),
)

# The context bar page each canvas tool shows; both selection tools act on a
# selection (flip, rotate, align, distribute).
TOOL_CONTEXT_PAGE_KEYS = {
    "select": "select",
    "perspective": "select",
    "bond": "bond",
    "arrow": "arrow",
    "line": "line",
    "ts_bracket": "bracket",
    "text": "atom",
    "note": "text",
    "mark": "mark",
    "benzene": "ring",
    "color": "color",
    "orbital": "orbital",
    "shape": "shape",
}

# The Text page: size steps, then format groups separated by dividers.
TEXT_SIZE_ACTION_SPECS = (
    ("icon_text_size_decrease", "Decrease font size", -1),
    ("icon_text_size_increase", "Increase font size", 1),
)
TEXT_FORMAT_ACTION_GROUPS = (
    (
        ("bold", "icon_text_bold", "Bold the selected text"),
        ("italic", "icon_text_italic", "Italicize the selected text"),
    ),
    (
        ("superscript", "icon_text_superscript", "Superscript the selected text"),
        ("subscript", "icon_text_subscript", "Subscript the selected text"),
    ),
    (
        ("left", "icon_align_left", "Align left"),
        ("center", "icon_align_center", "Align center"),
        ("right", "icon_align_right", "Align right"),
    ),
)
# Font size steps keep each run within these point sizes.
TEXT_POINT_SIZE_RANGE = (6.0, 96.0)
TEXT_FORMAT_TARGET_MESSAGE = "Select a note or edit its text to use Text formatting."

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

# Items the Color tool recolors; arrows of every kind join these.
COLOR_TARGET_KINDS = frozenset(
    ("bond", "atom", "ring", "note", "shape", "mark", "ts_bracket")
)
COLOR_TOOL_MESSAGES = {
    "choose": "Color: choose a swatch before painting.",
    "hidden": "Color stored for implicit carbon; hidden carbon vertices stay hidden. "
    "Color the bonds or show an explicit atom label for visible color.",
    "ts_bracket": "TS brackets and daggers use the document bond color; "
    "per-item color is not supported.",
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

# The rotation knob sits this far above its selection frame, on a stem.
ROTATION_HANDLE_STEM_PX = 14.0
ROTATION_HANDLE_TYPE = "selection_rotate"
SELECTION_FRAME_RADIUS = 2.0


ALIGN_SPECS: tuple[tuple[str, str], ...] = (
    ("left", "Align left edges"),
    ("center", "Align horizontal centres"),
    ("right", "Align right edges"),
    ("top", "Align top edges"),
    ("middle", "Align vertical centres"),
    ("bottom", "Align bottom edges"),
)
DISTRIBUTE_SPECS: tuple[tuple[str, str], ...] = (
    ("horizontal", "Distribute horizontally with equal gaps"),
    ("vertical", "Distribute vertically with equal gaps"),
)


ALIGN_MENU_SPECS: tuple[tuple[str, str], ...] = (
    ("Left", "left"),
    ("Center", "center"),
    ("Right", "right"),
    ("Top", "top"),
    ("Middle", "middle"),
    ("Bottom", "bottom"),
)
DISTRIBUTE_MENU_SPECS: tuple[tuple[str, str], ...] = (
    ("Horizontally", "horizontal"),
    ("Vertically", "vertical"),
)


__all__ = [
    "ARROW_MENU_SPECS",
    "ARROW_PRESET_SPECS",
    "ARROW_SLIDER_PAGE_STEP",
    "ARROW_SLIDER_RANGES",
    "BOND_LENGTH_INPUT_SPEC",
    "BOND_MODIFIERS",
    "BOND_ORDER_SEGMENTS",
    "BOND_TOOL_ACTION_SPECS",
    "BRACKET_MENU_SPECS",
    "COLOR_PALETTE_SPECS",
    "COLOR_TARGET_KINDS",
    "DOUBLE_BOND_CONTEXT_STYLES",
    "FIT_VIEW_MARGIN",
    "HANDLE_ACCENT_COLOR",
    "HANDLE_SCREEN_PX",
    "MARK_TOOL_ACTION_SPECS",
    "RING_FILL_TOOL_ACTION_SPEC",
    "ROTATE_ANGLE_DEFAULT",
    "ROTATE_ANGLE_RANGE",
    "ROTATION_HANDLE_STEM_PX",
    "ROTATION_HANDLE_TYPE",
    "SELECTION_FRAME_RADIUS",
    "SHAPE_KIND_SPECS",
    "SHAPE_STROKE_SPECS",
    "TEMPLATE_ENTRY_SPECS",
    "TEXT_FONT_FAMILY_CHOICES",
    "TEXT_FORMAT_ACTION_GROUPS",
    "TEXT_FORMAT_TARGET_MESSAGE",
    "TEXT_POINT_SIZE_RANGE",
    "TEXT_SIZE_ACTION_SPECS",
    "TOOLBAR_PRIMARY_TOOL_GROUP",
    "TOOLBAR_TOOL_ACTION_ORDER",
    "TOOLBAR_TOOL_GROUPS",
    "TOOL_ACTION_SPECS",
    "TOOL_CONTEXT_PAGE_KEYS",
    "TOOL_HINTS",
]
