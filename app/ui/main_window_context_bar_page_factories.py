from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QLineEdit,
    QSlider,
    QToolButton,
    QWidget,
)

from ui.main_window_config import (
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    BRACKET_MENU_SPECS,
    COLOR_PALETTE_SPECS,
    MARK_TOOL_ACTION_SPECS,
    TEMPLATE_ENTRY_SPECS,
)
from ui.main_window_context_bar_widgets import (
    BondLengthSpinBox,
    action_button,
    atom_symbol_input,
    bond_length_input,
    color_swatch_button,
    divider,
    hint_label,
    icon_button,
    new_context_page,
    rotate_angle_input,
    slider_dropdown_button,
)
from ui.main_window_toolbar_logic import BOND_STYLE_BY_LABEL
from ui.main_window_ui_ports import icon_factory_for_window

_BOND_ORDER_SEGMENTS = [
    ("Single", "icon_bond", "Single bond (1)"),
    ("Double", "icon_bond_double", "Double bond (2)"),
    ("Triple", "icon_bond_triple", "Triple bond (3)"),
]

_BOND_MODIFIERS = [
    ("Bold", "icon_bond_bold", "Bold bond (B)"),
    ("Wedge", "icon_bond_wedge", "Wedge bond (W)"),
    ("Hash", "icon_bond_hash", "Hash bond (Shift+H)"),
    ("Dotted", "icon_bond_dotted", "Dotted bond"),
]

_LABEL_BY_STYLE = {value: label for label, value in BOND_STYLE_BY_LABEL.items()}


@dataclass(frozen=True)
class BondContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[str, QToolButton]
    length_spin: BondLengthSpinBox


@dataclass(frozen=True)
class ArrowContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[str, QToolButton]


@dataclass(frozen=True)
class BracketContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[str, QToolButton]


@dataclass(frozen=True)
class TemplateContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[tuple[int, str], QToolButton]


@dataclass(frozen=True)
class MarkContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[str, QToolButton]


@dataclass(frozen=True)
class AtomContextPage:
    page: QWidget
    atom_input: QLineEdit


def bond_label_for_state(style: str, order: int) -> str | None:
    return _LABEL_BY_STYLE.get((style, order))


def build_empty_page() -> QWidget:
    page, layout = new_context_page()
    layout.addWidget(hint_label("Select a tool to see its options here"))
    layout.addStretch(1)
    return page


def build_bond_page(
    window,
    activate_bond_style_for_window,
    set_bond_length_value_for_window,
    current_bond_length_px,
) -> BondContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)

    layout.addWidget(hint_label("Bond"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    for label, icon_method, tip in _BOND_ORDER_SEGMENTS:
        button = icon_button(getattr(icon_factory, icon_method)(), tip, checkable=True)
        button.clicked.connect(lambda _checked, v=label: activate_bond_style_for_window(window, v))
        group.addButton(button)
        buttons[label] = button
        layout.addWidget(button)

    layout.addWidget(divider())
    for label, icon_method, tip in _BOND_MODIFIERS:
        button = icon_button(getattr(icon_factory, icon_method)(), tip, checkable=True)
        button.clicked.connect(lambda _checked, v=label: activate_bond_style_for_window(window, v))
        group.addButton(button)
        buttons[label] = button
        layout.addWidget(button)

    layout.addWidget(divider())
    length_widget, length_spin = bond_length_input(
        current_bond_length_px,
        lambda value: set_bond_length_value_for_window(window, value),
    )
    layout.addWidget(length_widget)
    layout.addStretch(1)
    return BondContextPage(page=page, group=group, buttons=buttons, length_spin=length_spin)


def build_template_page(window, insert_controller) -> TemplateContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)
    layout.addWidget(hint_label("Ring"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[tuple[int, str], QToolButton] = {}
    for label, ring_size, style in TEMPLATE_ENTRY_SPECS:
        button = icon_button(icon_factory.icon_template_preview(label), label, checkable=True)
        button.clicked.connect(
            lambda _checked=False, n=ring_size, s=style: insert_controller.begin_ring_template_insert(
                n,
                style=s,
            )
        )
        group.addButton(button)
        buttons[(ring_size, style)] = button
        layout.addWidget(button)
    layout.addStretch(1)
    return TemplateContextPage(page=page, group=group, buttons=buttons)


def build_mark_page(window, tool_state_service) -> MarkContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)

    layout.addWidget(hint_label("Mark"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    for _key, _label, kind, icon_method, tooltip in MARK_TOOL_ACTION_SPECS:
        button = icon_button(getattr(icon_factory, icon_method)(), tooltip, checkable=True)
        button.clicked.connect(lambda _checked=False, value=kind: tool_state_service.set_mark_kind(window, value))
        group.addButton(button)
        buttons[kind] = button
        layout.addWidget(button)

    layout.addStretch(1)
    return MarkContextPage(page=page, group=group, buttons=buttons)


def build_arrow_page(window, tool_mode_controller, tool_state_service) -> ArrowContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)

    layout.addWidget(hint_label("Arrow"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    for label, value in ARROW_MENU_SPECS:
        button = icon_button(icon_factory.icon_arrow_preview(value), label, checkable=True)
        button.clicked.connect(lambda _checked, v=label: tool_state_service.set_arrow_type(window, v))
        group.addButton(button)
        buttons[value] = button
        layout.addWidget(button)

    layout.addWidget(divider())
    for label in ARROW_PRESET_SPECS:
        button = icon_button(icon_factory.icon_arrow_preset(label), f"{label} arrow preset")
        button.clicked.connect(lambda _checked=False, v=label: tool_state_service.set_arrow_preset(window, v))
        layout.addWidget(button)

    layout.addWidget(divider())
    width = QSlider(Qt.Orientation.Horizontal)
    width.setMinimum(1)
    width.setMaximum(6)
    width.setValue(int(tool_mode_controller.get_arrow_line_width()))
    width.valueChanged.connect(lambda v: tool_mode_controller.set_arrow_line_width(v))
    layout.addWidget(slider_dropdown_button(icon_factory.icon_arrow_width(), "Arrow line width", width))

    head = QSlider(Qt.Orientation.Horizontal)
    head.setMinimum(10)
    head.setMaximum(60)
    head.setValue(int(tool_mode_controller.get_arrow_head_scale() * 100))
    head.valueChanged.connect(lambda v: tool_mode_controller.set_arrow_head_scale(v / 100.0))
    layout.addWidget(slider_dropdown_button(icon_factory.icon_arrow_head_scale(), "Arrow head size", head))

    layout.addStretch(1)
    return ArrowContextPage(page=page, group=group, buttons=buttons)


def build_bracket_page(window, tool_state_service) -> BracketContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)

    layout.addWidget(hint_label("Bracket"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    for label, value in BRACKET_MENU_SPECS:
        button = icon_button(icon_factory.icon_bracket_preview(value), label, checkable=True)
        button.clicked.connect(lambda _checked=False, v=value: tool_state_service.set_bracket_type(window, v))
        group.addButton(button)
        buttons[value] = button
        layout.addWidget(button)

    layout.addStretch(1)
    return BracketContextPage(page=page, group=group, buttons=buttons)


def build_atom_page(current_symbol: str, set_atom_symbol) -> AtomContextPage:
    page, layout = new_context_page()
    layout.addWidget(hint_label("Atom"))
    atom_input = atom_symbol_input(
        current_symbol,
        set_atom_symbol,
    )
    layout.addWidget(atom_input)
    layout.addStretch(1)
    return AtomContextPage(page=page, atom_input=atom_input)


def _text_icon_button(icon, tooltip: str, on_click) -> QToolButton:
    button = icon_button(icon, tooltip)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.clicked.connect(lambda _checked=False: on_click())
    return button


def build_text_page(
    window,
    *,
    toggle_bold,
    toggle_italic,
    toggle_superscript,
    toggle_subscript,
    adjust_size,
    set_alignment,
) -> QWidget:
    icons = icon_factory_for_window(window)
    page, layout = new_context_page()
    layout.addWidget(hint_label("Text"))
    layout.addWidget(
        _text_icon_button(icons.icon_text_size_decrease(), "Decrease font size", lambda: adjust_size(-1))
    )
    layout.addWidget(
        _text_icon_button(icons.icon_text_size_increase(), "Increase font size", lambda: adjust_size(1))
    )
    layout.addWidget(divider())
    layout.addWidget(_text_icon_button(icons.icon_text_bold(), "Bold the selected text", toggle_bold))
    layout.addWidget(_text_icon_button(icons.icon_text_italic(), "Italicize the selected text", toggle_italic))
    layout.addWidget(divider())
    layout.addWidget(
        _text_icon_button(icons.icon_text_superscript(), "Superscript the selected text", toggle_superscript)
    )
    layout.addWidget(
        _text_icon_button(icons.icon_text_subscript(), "Subscript the selected text", toggle_subscript)
    )
    layout.addWidget(divider())
    layout.addWidget(_text_icon_button(icons.icon_align_left(), "Align left", lambda: set_alignment("left")))
    layout.addWidget(_text_icon_button(icons.icon_align_center(), "Align center", lambda: set_alignment("center")))
    layout.addWidget(_text_icon_button(icons.icon_align_right(), "Align right", lambda: set_alignment("right")))
    layout.addStretch(1)
    return page


def build_orbital_page(window, tool_state_service) -> QWidget:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)
    layout.addWidget(hint_label("Orbital"))
    for label in ("s", "p", "sp", "sp2", "sp3", "d"):
        button = icon_button(icon_factory.icon_orbital_preview(label), f"Orbital: {label}")
        button.clicked.connect(lambda _checked=False, value=label: tool_state_service.set_orbital_type(window, value))
        layout.addWidget(button)
    layout.addWidget(divider())
    for label, enabled in (("Phase Off", False), ("Phase On", True)):
        button = icon_button(icon_factory.icon_orbital_phase(enabled), label)
        button.clicked.connect(lambda _checked=False, value=label: tool_state_service.set_orbital_phase(window, value))
        layout.addWidget(button)
    layout.addStretch(1)
    return page


_SHAPE_KIND_SPECS = [
    ("circle", "Circle"),
    ("ellipse", "Ellipse"),
    ("rounded_rect", "Rounded rectangle"),
    ("rect", "Rectangle"),
]

_SHAPE_STROKE_SPECS = [
    ("solid", "Solid outline"),
    ("dashed", "Dashed outline"),
    ("dotted", "Dotted outline"),
    ("none", "No outline (select a shape first)"),
]


def build_shape_page(window, tool_state_service) -> QWidget:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)
    layout.addWidget(hint_label("Shape"))

    kind_group = QButtonGroup(page)
    kind_group.setExclusive(True)
    for kind, tip in _SHAPE_KIND_SPECS:
        button = icon_button(icon_factory.icon_shape_kind(kind), tip, checkable=True)
        button.setChecked(kind == "circle")
        button.clicked.connect(lambda _checked=False, value=kind: tool_state_service.set_shape_type(window, value))
        kind_group.addButton(button)
        layout.addWidget(button)

    layout.addWidget(divider())
    stroke_group = QButtonGroup(page)
    stroke_group.setExclusive(True)
    for style, tip in _SHAPE_STROKE_SPECS:
        button = icon_button(icon_factory.icon_shape_stroke(style), tip, checkable=True)
        button.setChecked(style == "solid")
        button.clicked.connect(lambda _checked=False, value=style: tool_state_service.set_shape_stroke(window, value))
        stroke_group.addButton(button)
        layout.addWidget(button)

    layout.addStretch(1)
    return page


def build_rotate_page(window, rotate_selection) -> QWidget:
    page, layout = new_context_page()
    layout.addWidget(hint_label("Rotate"))
    angle_frame, angle_input = rotate_angle_input()
    layout.addWidget(angle_frame)

    def apply_rotation() -> None:
        rotate_selection(window, float(angle_input.value()))

    apply_button = action_button("Apply", "Rotate the selection by the entered angle")
    apply_button.setObjectName("rotateApplyButton")
    apply_button.clicked.connect(lambda _checked=False: apply_rotation())
    line_edit = angle_input.lineEdit()
    if line_edit is not None:
        line_edit.returnPressed.connect(apply_rotation)
    layout.addWidget(apply_button)
    layout.addStretch(1)
    return page


def build_color_palette_page(
    *,
    tooltip_prefix: str,
    apply_preset,
) -> QWidget:
    page, layout = new_context_page()
    layout.addWidget(hint_label(tooltip_prefix))
    for label, hex_value in COLOR_PALETTE_SPECS:
        button = color_swatch_button(label, hex_value, tooltip_prefix)
        button.clicked.connect(lambda _checked=False, value=hex_value: apply_preset(value))
        layout.addWidget(button)
    layout.addStretch(1)
    return page


__all__ = [
    "ArrowContextPage",
    "AtomContextPage",
    "BondContextPage",
    "BracketContextPage",
    "MarkContextPage",
    "TemplateContextPage",
    "bond_label_for_state",
    "build_arrow_page",
    "build_atom_page",
    "build_bond_page",
    "build_bracket_page",
    "build_color_palette_page",
    "build_empty_page",
    "build_mark_page",
    "build_orbital_page",
    "build_rotate_page",
    "build_shape_page",
    "build_template_page",
    "build_text_page",
]
