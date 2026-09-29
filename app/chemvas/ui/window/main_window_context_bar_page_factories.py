from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QLineEdit,
    QSlider,
    QToolButton,
    QWidget,
)

from chemvas.ui.window.main_window_config import (
    ALIGN_SPECS,
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    ARROW_SLIDER_LABELS,
    ARROW_SLIDER_PAGE_STEP,
    ARROW_SLIDER_RANGES,
    BRACKET_MENU_SPECS,
    COLOR_PALETTE_SPECS,
    DISTRIBUTE_SPECS,
    FLIP_ACTION_SPECS,
    LINE_KIND_SPECS,
    MARK_TOOL_ACTION_SPECS,
    MORE_ARROW_KINDS,
    ORBITAL_MO_TEXT,
    ORBITAL_PHASE_SPECS,
    SHAPE_KIND_SPECS,
    SHAPE_STROKE_SPECS,
    TEMPLATE_ENTRY_SPECS,
)
from chemvas.ui.window.main_window_config import BOND_MODIFIERS as _BOND_MODIFIERS
from chemvas.ui.window.main_window_config import (
    BOND_ORDER_SEGMENTS as _BOND_ORDER_SEGMENTS,
)
from chemvas.ui.window.main_window_context_bar_widgets import (
    BondLengthSpinBox,
    KindMenuButton,
    SegmentedButtonGroup,
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
from chemvas.ui.window.main_window_toolbar_logic import (
    BOND_STYLE_BY_LABEL,
    ORBITAL_TYPE_BY_LABEL,
)

if TYPE_CHECKING:
    from chemvas.ui.window.main_window_like import MainWindowLike


_LABEL_BY_STYLE = {value: label for label, value in BOND_STYLE_BY_LABEL.items()}


@dataclass(frozen=True)
class BondContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[str, QToolButton]
    length_spin: BondLengthSpinBox


@dataclass(frozen=True)
class ButtonGroupPage:
    """A context page whose options are one exclusive group of icon buttons."""

    page: QWidget
    group: QButtonGroup
    buttons: dict[str, QToolButton]


@dataclass(frozen=True)
class TextContextPage:
    page: QWidget
    buttons: dict[str, QToolButton]


@dataclass(frozen=True)
class AnnotationContextPage:
    page: QWidget
    buttons: dict[str, dict[str | bool, QToolButton]]


@dataclass(frozen=True)
class ArrowContextPage(ButtonGroupPage):
    width_slider: QSlider
    head_slider: QSlider


@dataclass(frozen=True)
class TemplateContextPage:
    page: QWidget
    group: QButtonGroup
    buttons: dict[tuple[int, str], QToolButton]


@dataclass(frozen=True)
class AtomContextPage:
    page: QWidget
    atom_input: QLineEdit


def bond_label_for_state(style: str, order: int) -> str | None:
    return _LABEL_BY_STYLE.get((style, order))


def _add_group_buttons(
    group: QButtonGroup, layout, buttons: dict, entries
) -> SegmentedButtonGroup:
    """Append checkable icon buttons to ``group``/``layout``, keyed into ``buttons``.

    Each entry is ``(key, icon, tooltip, on_click)``.
    """
    segments = SegmentedButtonGroup()
    layout.addWidget(segments)
    for key, icon, tooltip, handler in entries:
        button = icon_button(icon, tooltip, checkable=True)
        button.clicked.connect(handler)
        group.addButton(button)
        buttons[key] = button
        segments.add_button(button)
    return segments


def build_empty_page() -> QWidget:
    # Tools without options (the eraser) leave the bar quiet rather than
    # explaining itself.
    page, layout = new_context_page()
    layout.addStretch(1)
    return page


def build_select_page(
    window: MainWindowLike,
    *,
    flip_selection,
    rotate_selection,
    align_selection,
    distribute_selection,
) -> QWidget:
    """Everything that acts on the current selection: flip, rotate, align, distribute."""
    icons = window.ui_references.require_icon_factory()
    page, layout = new_context_page()
    layout.addWidget(hint_label("Select"))
    for object_name, icon_name, label, shortcut, horizontal in FLIP_ACTION_SPECS:
        icon = getattr(icons, icon_name)()
        tooltip = f"{label} ({QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)})"
        button = icon_button(icon, tooltip)
        button.setObjectName(object_name)
        button.setStatusTip(tooltip)
        button.clicked.connect(
            lambda _checked=False, h=horizontal: flip_selection(window, horizontal=h)
        )
        layout.addWidget(button)

    layout.addWidget(divider())
    angle_frame, angle_input = rotate_angle_input()
    layout.addWidget(angle_frame)

    def apply_rotation() -> None:
        rotate_selection(window, float(angle_input.value()))

    apply_button = action_button("Rotate", "Rotate the selection by the entered angle")
    apply_button.setObjectName("rotateApplyButton")
    apply_button.clicked.connect(lambda _checked=False: apply_rotation())
    line_edit = angle_input.lineEdit()
    if line_edit is not None:
        line_edit.returnPressed.connect(apply_rotation)
    layout.addWidget(apply_button)

    layout.addWidget(divider())
    for mode, tooltip in ALIGN_SPECS:
        button = icon_button(icons.icon_align_objects(mode), tooltip)
        button.setObjectName(f"align_{mode}_button")
        button.setStatusTip(tooltip)
        button.clicked.connect(
            lambda _checked=False, m=mode: align_selection(window, m)
        )
        layout.addWidget(button)

    layout.addWidget(divider())
    for axis, tooltip in DISTRIBUTE_SPECS:
        button = icon_button(icons.icon_distribute(axis), tooltip)
        button.setObjectName(f"distribute_{axis}_button")
        button.setStatusTip(tooltip)
        button.clicked.connect(
            lambda _checked=False, a=axis: distribute_selection(window, a)
        )
        layout.addWidget(button)
    layout.addStretch(1)
    return page


def build_bond_page(
    window: MainWindowLike,
    activate_bond_style_for_window,
    set_bond_length_value_for_window,
    current_bond_length_px,
) -> BondContextPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()

    layout.addWidget(hint_label("Bond"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}

    def bond_entries(specs):
        return [
            (
                label,
                getattr(icon_factory, icon_method)(),
                tip,
                lambda _checked, v=label: activate_bond_style_for_window(window, v),
            )
            for label, icon_method, tip in specs
        ]

    _add_group_buttons(group, layout, buttons, bond_entries(_BOND_ORDER_SEGMENTS))
    layout.addWidget(divider())
    _add_group_buttons(group, layout, buttons, bond_entries(_BOND_MODIFIERS))

    layout.addWidget(divider())
    length_widget, length_spin = bond_length_input(
        current_bond_length_px,
        lambda value: set_bond_length_value_for_window(window, value),
    )
    layout.addWidget(length_widget)
    layout.addStretch(1)
    return BondContextPage(
        page=page, group=group, buttons=buttons, length_spin=length_spin
    )


def build_template_page(
    window: MainWindowLike, begin_ring_template_insert
) -> TemplateContextPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()
    layout.addWidget(hint_label("Ring"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[tuple[int, str], QToolButton] = {}
    _add_group_buttons(
        group,
        layout,
        buttons,
        [
            (
                (ring_size, style),
                icon_factory.icon_template_preview(label),
                label,
                lambda _checked=False, n=ring_size, s=style: begin_ring_template_insert(
                    n,
                    style=s,
                ),
            )
            for label, ring_size, style in TEMPLATE_ENTRY_SPECS
        ],
    )
    layout.addStretch(1)
    return TemplateContextPage(page=page, group=group, buttons=buttons)


def build_mark_page(window: MainWindowLike, tool_state_service) -> ButtonGroupPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()

    layout.addWidget(hint_label("Mark"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    _add_group_buttons(
        group,
        layout,
        buttons,
        [
            (
                kind,
                getattr(icon_factory, icon_method)(),
                tooltip,
                lambda _checked=False, value=kind: tool_state_service.set_mark_kind(
                    window, value
                ),
            )
            for _key, _label, kind, icon_method, tooltip in MARK_TOOL_ACTION_SPECS
        ],
    )
    layout.addStretch(1)
    return ButtonGroupPage(page=page, group=group, buttons=buttons)


def build_arrow_page(
    window: MainWindowLike, tool_mode_controller, tool_state_service
) -> ArrowContextPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()

    layout.addWidget(hint_label("Arrow"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    _add_group_buttons(
        group,
        layout,
        buttons,
        [
            (
                value,
                icon_factory.icon_arrow_preview(value),
                label,
                lambda _checked, v=value: tool_state_service.set_arrow_type(window, v),
            )
            for label, value in ARROW_MENU_SPECS
            if value not in MORE_ARROW_KINDS
        ],
    )
    # The seldom-used kinds share one button whose menu lists them; the
    # button wears whichever was picked last.
    more_entries = [
        (value, icon_factory.icon_arrow_preview(value), label)
        for label, value in ARROW_MENU_SPECS
        if value in MORE_ARROW_KINDS
    ]
    if more_entries:
        more_button = KindMenuButton(
            more_entries,
            lambda value: tool_state_service.set_arrow_type(window, value),
            tooltip="More arrows",
        )
        more_button.setObjectName("more_arrows_button")
        group.addButton(more_button)
        for kind in more_button.kinds():
            buttons[kind] = more_button
        layout.addWidget(more_button)

    layout.addWidget(divider())
    for label in ARROW_PRESET_SPECS:
        button = icon_button(
            icon_factory.icon_arrow_preset(label), f"{label} arrow preset"
        )
        button.clicked.connect(
            lambda _checked=False, v=label: tool_state_service.set_arrow_preset(
                window, v
            )
        )
        layout.addWidget(button)

    layout.addWidget(divider())
    width = QSlider(Qt.Orientation.Horizontal)
    width.setTracking(False)
    width.setPageStep(ARROW_SLIDER_PAGE_STEP)
    width_min, width_max, width_factor = ARROW_SLIDER_RANGES["arrow_line_width"]
    width.setMinimum(width_min)
    width.setMaximum(width_max)
    width.setValue(round(tool_mode_controller.get_arrow_line_width() * width_factor))
    width.valueChanged.connect(
        lambda v: tool_mode_controller.set_arrow_line_width(v / width_factor)
    )
    layout.addWidget(
        slider_dropdown_button(
            icon_factory.icon_arrow_width(),
            ARROW_SLIDER_LABELS["arrow_line_width"],
            width,
        )
    )

    head = QSlider(Qt.Orientation.Horizontal)
    head.setTracking(False)
    head.setPageStep(ARROW_SLIDER_PAGE_STEP)
    head_min, head_max, head_factor = ARROW_SLIDER_RANGES["arrow_head_scale"]
    head.setMinimum(head_min)
    head.setMaximum(head_max)
    head.setValue(round(tool_mode_controller.get_arrow_head_scale() * head_factor))
    head.valueChanged.connect(
        lambda v: tool_mode_controller.set_arrow_head_scale(v / head_factor)
    )
    layout.addWidget(
        slider_dropdown_button(
            icon_factory.icon_arrow_head_scale(),
            ARROW_SLIDER_LABELS["arrow_head_scale"],
            head,
        )
    )

    layout.addStretch(1)
    return ArrowContextPage(
        page=page, group=group, buttons=buttons, width_slider=width, head_slider=head
    )


def build_bracket_page(window: MainWindowLike, tool_state_service) -> ButtonGroupPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()

    layout.addWidget(hint_label("Bracket"))
    group = QButtonGroup(page)
    group.setExclusive(True)
    buttons: dict[str, QToolButton] = {}
    _add_group_buttons(
        group,
        layout,
        buttons,
        [
            (
                value,
                icon_factory.icon_bracket_preview(value),
                label,
                lambda _checked=False, v=value: tool_state_service.set_bracket_type(
                    window, v
                ),
            )
            for label, value in BRACKET_MENU_SPECS
        ],
    )
    layout.addStretch(1)
    return ButtonGroupPage(page=page, group=group, buttons=buttons)


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


def _text_icon_button(icon, tooltip: str, on_click, *, checkable=False) -> QToolButton:
    button = icon_button(icon, tooltip, checkable=checkable)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.clicked.connect(lambda _checked=False: on_click())
    return button


def build_text_page(
    window: MainWindowLike,
    *,
    toggle_bold,
    toggle_italic,
    toggle_superscript,
    toggle_subscript,
    adjust_size,
    set_alignment,
) -> TextContextPage:
    icons = window.ui_references.require_icon_factory()
    page, layout = new_context_page()
    layout.addWidget(hint_label("Text"))
    layout.addWidget(
        _text_icon_button(
            icons.icon_text_size_decrease(),
            "Decrease font size",
            lambda: adjust_size(-1),
        )
    )
    layout.addWidget(
        _text_icon_button(
            icons.icon_text_size_increase(),
            "Increase font size",
            lambda: adjust_size(1),
        )
    )
    buttons = {}
    for key, icon, tip, handler in (
        ("bold", icons.icon_text_bold(), "Bold the selected text", toggle_bold),
        (
            "italic",
            icons.icon_text_italic(),
            "Italicize the selected text",
            toggle_italic,
        ),
        (
            "superscript",
            icons.icon_text_superscript(),
            "Superscript the selected text",
            toggle_superscript,
        ),
        (
            "subscript",
            icons.icon_text_subscript(),
            "Subscript the selected text",
            toggle_subscript,
        ),
        ("left", icons.icon_align_left(), "Align left", lambda: set_alignment("left")),
        (
            "center",
            icons.icon_align_center(),
            "Align center",
            lambda: set_alignment("center"),
        ),
        (
            "right",
            icons.icon_align_right(),
            "Align right",
            lambda: set_alignment("right"),
        ),
    ):
        if key in {"bold", "superscript", "left"}:
            layout.addWidget(divider())
        button = _text_icon_button(icon, tip, handler, checkable=True)
        buttons[key] = button
        layout.addWidget(button)
    layout.addStretch(1)
    return TextContextPage(page, buttons)


def build_orbital_page(
    window: MainWindowLike, tool_state_service
) -> AnnotationContextPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()
    layout.addWidget(hint_label("Orbital"))
    kind_group = QButtonGroup(page)
    kinds: dict[str | bool, QToolButton] = {}
    phases: dict[str | bool, QToolButton] = {}
    phase_group = QButtonGroup(page)
    for label, kind in ORBITAL_TYPE_BY_LABEL.items():
        button = icon_button(
            icon_factory.icon_orbital_preview(kind), f"Orbital: {label}", checkable=True
        )
        kinds[kind] = button
        kind_group.addButton(button)
        if kind in ORBITAL_MO_TEXT:
            button.setText(ORBITAL_MO_TEXT[kind])
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setFixedWidth(40)
        button.clicked.connect(
            lambda _checked=False, value=label: tool_state_service.set_orbital_type(
                window, value
            )
        )
        layout.addWidget(button)
    layout.addWidget(divider())
    for label, enabled in ORBITAL_PHASE_SPECS:
        button = icon_button(
            icon_factory.icon_orbital_phase(enabled), label, checkable=True
        )
        phases[enabled] = button
        phase_group.addButton(button)
        button.clicked.connect(
            lambda _checked=False, value=label: tool_state_service.set_orbital_phase(
                window, value
            )
        )
        layout.addWidget(button)
    layout.addStretch(1)
    return AnnotationContextPage(
        page, {"active_orbital_type": kinds, "orbital_phase_enabled": phases}
    )


def build_shape_page(
    window: MainWindowLike, tool_state_service
) -> AnnotationContextPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()
    layout.addWidget(hint_label("Shape"))

    kinds: dict[str | bool, QToolButton] = {}
    kind_group = QButtonGroup(page)
    kind_group.setExclusive(True)
    for kind, tip in SHAPE_KIND_SPECS:
        button = icon_button(icon_factory.icon_shape_kind(kind), tip, checkable=True)
        kinds[kind] = button
        button.clicked.connect(
            lambda _checked=False, value=kind: tool_state_service.set_shape_type(
                window, value
            )
        )
        kind_group.addButton(button)
        layout.addWidget(button)

    layout.addWidget(divider())
    strokes: dict[str | bool, QToolButton] = {}
    stroke_group = QButtonGroup(page)
    stroke_group.setExclusive(True)
    for style, tip in SHAPE_STROKE_SPECS:
        button = icon_button(icon_factory.icon_shape_stroke(style), tip, checkable=True)
        strokes[style] = button
        button.clicked.connect(
            lambda _checked=False, value=style: tool_state_service.set_shape_stroke(
                window, value
            )
        )
        stroke_group.addButton(button)
        layout.addWidget(button)

    layout.addStretch(1)
    return AnnotationContextPage(
        page, {"active_shape_type": kinds, "active_shape_stroke": strokes}
    )


def build_line_page(
    window: MainWindowLike, tool_state_service
) -> AnnotationContextPage:
    page, layout = new_context_page()
    icon_factory = window.ui_references.require_icon_factory()
    layout.addWidget(hint_label("Line"))

    kinds: dict[str | bool, QToolButton] = {}
    kind_group = QButtonGroup(page)
    kind_group.setExclusive(True)
    for kind, tip in LINE_KIND_SPECS:
        button = icon_button(icon_factory.icon_line_kind(kind), tip, checkable=True)
        kinds[kind] = button
        button.clicked.connect(
            lambda _checked=False, value=kind: tool_state_service.set_line_kind(
                window, value
            )
        )
        kind_group.addButton(button)
        layout.addWidget(button)

    layout.addStretch(1)
    return AnnotationContextPage(page, {"active_line_kind": kinds})


def build_color_palette_page(
    *,
    tooltip_prefix: str,
    apply_preset,
    checkable: bool,
) -> ButtonGroupPage:
    page, layout = new_context_page()
    group = QButtonGroup(page)
    buttons = {}
    selected_color = QColor("#000000")

    def apply_color(value: str) -> None:
        nonlocal selected_color
        selected_color = QColor(value)
        apply_preset(value)

    def choose_color() -> None:
        color = QColorDialog.getColor(selected_color, page, tooltip_prefix)
        if color.isValid():
            apply_color(color.name())

    layout.addWidget(hint_label(tooltip_prefix))
    for label, hex_value in COLOR_PALETTE_SPECS:
        button = color_swatch_button(label, hex_value, tooltip_prefix)
        button.setCheckable(checkable)
        group.addButton(button)
        buttons[hex_value] = button
        button.clicked.connect(
            lambda _checked=False, value=hex_value: apply_color(value)
        )
        layout.addWidget(button)
    custom = action_button("More colors…", f"{tooltip_prefix}: choose a custom color")
    custom.setObjectName(f"{tooltip_prefix.lower().replace(' ', '_')}_more_colors")
    custom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    custom.clicked.connect(lambda _checked=False: choose_color())
    layout.addWidget(custom)
    layout.addStretch(1)
    return ButtonGroupPage(page, group, buttons)


__all__ = [
    "AtomContextPage",
    "BondContextPage",
    "ButtonGroupPage",
    "TemplateContextPage",
    "bond_label_for_state",
    "build_arrow_page",
    "build_atom_page",
    "build_bond_page",
    "build_bracket_page",
    "build_color_palette_page",
    "build_empty_page",
    "build_line_page",
    "build_mark_page",
    "build_orbital_page",
    "build_select_page",
    "build_shape_page",
    "build_template_page",
    "build_text_page",
]
