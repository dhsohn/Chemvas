from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QButtonGroup, QSlider, QToolButton, QWidget

from ui.main_window_config import (
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    COLOR_PALETTE_SPECS,
    MARK_TOOL_ACTION_SPECS,
    TEMPLATE_ENTRY_SPECS,
)
from ui.main_window_context_bar_widgets import (
    color_swatch_button,
    divider,
    hint_label,
    icon_button,
    new_context_page,
    slider_dropdown_button,
)
from ui.main_window_toolbar_logic import BOND_STYLE_BY_LABEL
from ui.main_window_ui_ports import icon_factory_for_window

_BOND_SEGMENTS = [
    ("Single", "icon_bond", "Single bond (1)"),
    ("Double", "icon_bond_double", "Double bond (2)"),
    ("Triple", "icon_bond_triple", "Triple bond (3)"),
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


@dataclass(frozen=True)
class ArrowContextPage:
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


def bond_label_for_state(style: str, order: int) -> str | None:
    return _LABEL_BY_STYLE.get((style, order))


def build_empty_page() -> QWidget:
    page, layout = new_context_page()
    layout.addWidget(hint_label("Select a tool to see its options here"))
    layout.addStretch(1)
    return page


def build_bond_page(window, activate_bond_style_for_window, set_bond_length_for_window) -> BondContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)

    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    for label, icon_method, tip in _BOND_SEGMENTS:
        button = icon_button(getattr(icon_factory, icon_method)(), tip, checkable=True)
        button.clicked.connect(lambda _checked, v=label: activate_bond_style_for_window(window, v))
        group.addButton(button)
        buttons[label] = button
        layout.addWidget(button)

    layout.addWidget(divider())
    length_button = icon_button(icon_factory.icon_bond_length(), "Set the default bond length")
    length_button.clicked.connect(lambda _checked=False: set_bond_length_for_window(window))
    layout.addWidget(length_button)
    layout.addStretch(1)
    return BondContextPage(page=page, group=group, buttons=buttons)


def build_template_page(window, insert_controller) -> TemplateContextPage:
    page, layout = new_context_page()
    icon_factory = icon_factory_for_window(window)
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


def build_atom_page() -> QWidget:
    page, layout = new_context_page()
    layout.addWidget(hint_label("Element hotkeys: c n o s p f h · edit label Enter · charge +/-"))
    layout.addStretch(1)
    return page


def build_color_palette_page(
    *,
    tooltip_prefix: str,
    apply_preset,
) -> QWidget:
    page, layout = new_context_page()
    for label, hex_value in COLOR_PALETTE_SPECS:
        button = color_swatch_button(label, hex_value, tooltip_prefix)
        button.clicked.connect(lambda _checked=False, value=hex_value: apply_preset(value))
        layout.addWidget(button)
    layout.addStretch(1)
    return page


__all__ = [
    "ArrowContextPage",
    "BondContextPage",
    "MarkContextPage",
    "TemplateContextPage",
    "bond_label_for_state",
    "build_arrow_page",
    "build_atom_page",
    "build_bond_page",
    "build_color_palette_page",
    "build_empty_page",
    "build_mark_page",
    "build_template_page",
]
