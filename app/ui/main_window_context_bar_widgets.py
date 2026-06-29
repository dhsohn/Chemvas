from __future__ import annotations

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPolygonF
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ui.main_window_palette import PALETTE
from ui.main_window_theme import (
    CONTEXT_ACTION_BUTTON_STYLE,
    CONTEXT_BAR_BUTTON_HEIGHT,
    CONTEXT_BAR_ICON_SIZE,
    CONTEXT_SEGMENT_STYLE,
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
)
from ui.main_window_toolbar_buttons import CornerMenuButton


class _StepArrowButton(QToolButton):
    """A flat button that paints a small triangle centered in its rect."""

    def __init__(self, direction: str) -> None:
        super().__init__()
        self._direction = direction
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["text_muted"]))
        half_w = 3.5
        half_h = 2.0
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        if self._direction == "up":
            points = [
                QPointF(cx, cy - half_h),
                QPointF(cx + half_w, cy + half_h),
                QPointF(cx - half_w, cy + half_h),
            ]
        else:
            points = [
                QPointF(cx - half_w, cy - half_h),
                QPointF(cx + half_w, cy - half_h),
                QPointF(cx, cy + half_h),
            ]
        painter.drawPolygon(QPolygonF(points))

_ICON_SIZE = QSize(CONTEXT_BAR_ICON_SIZE, CONTEXT_BAR_ICON_SIZE)
_ICON_BUTTON_STYLE = (
    TOOLBAR_BUTTON_STYLE
    + "QToolButton { padding: 0px; }"
    "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
    "QToolButton::menu-arrow { image: none; width: 0px; height: 0px;"
    " border: none; background: transparent; }"
)
_P = PALETTE
_ARROW_COMPACT_SLIDER_STYLE = (
    "QSlider#arrowCompactSlider {"
    f" min-height: {CONTEXT_BAR_BUTTON_HEIGHT}px;"
    f" max-height: {CONTEXT_BAR_BUTTON_HEIGHT}px;"
    "}"
    "QSlider#arrowCompactSlider::groove:horizontal {"
    " height: 4px;"
    f" background: {_P['border_strong']};"
    " border-radius: 2px;"
    " margin: 0px 0px;"
    "}"
    "QSlider#arrowCompactSlider::handle:horizontal {"
    " width: 12px;"
    " height: 12px;"
    f" background: {_P['accent']};"
    " border: none;"
    " border-radius: 6px;"
    " margin: -4px 0px;"
    "}"
    "QSlider#arrowCompactSlider::handle:horizontal:hover {"
    f" background: {_P['checked_text']};"
    "}"
)
_ARROW_SLIDER_MENU_STYLE = (
    "QMenu {"
    f" background: {_P['surface_input']};"
    f" border: 1px solid {_P['border']};"
    " border-radius: 6px;"
    " padding: 6px 8px;"
    "}"
)


def new_context_page() -> tuple[QWidget, QHBoxLayout]:
    page = QWidget()
    layout = QHBoxLayout(page)
    layout.setContentsMargins(2, 0, 2, 0)
    layout.setSpacing(3)
    return page, layout


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("toolbarSectionLabel")
    return label


def divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedHeight(18)
    line.setStyleSheet(f"color: {_P['border_soft']};")
    return line


def icon_button(
    icon,
    tooltip: str,
    *,
    checkable: bool = False,
) -> QToolButton:
    button = QToolButton()
    button.setIcon(icon)
    button.setIconSize(_ICON_SIZE)
    button.setFixedSize(CONTEXT_BAR_BUTTON_HEIGHT, CONTEXT_BAR_BUTTON_HEIGHT)
    button.setToolTip(tooltip)
    button.setAutoRaise(True)
    button.setCheckable(checkable)
    button.setStyleSheet(_ICON_BUTTON_STYLE)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def icon_menu_button(icon, tooltip: str) -> CornerMenuButton:
    """An icon button that drops down a menu, matching the File button's form
    (a small chevron painted in the bottom-right corner)."""
    button = CornerMenuButton()
    button.setIcon(icon)
    button.setIconSize(_ICON_SIZE)
    button.setFixedSize(CONTEXT_BAR_BUTTON_HEIGHT, CONTEXT_BAR_BUTTON_HEIGHT)
    button.setToolTip(tooltip)
    button.setStatusTip(tooltip)
    button.setAutoRaise(True)
    button.setStyleSheet(_ICON_BUTTON_STYLE)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    return button


def segment_button(
    text: str,
    tooltip: str,
    *,
    checkable: bool = False,
) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.setStatusTip(tooltip)
    button.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
    button.setCheckable(checkable)
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(CONTEXT_SEGMENT_STYLE)
    return button


def action_button(text: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.setStatusTip(tooltip)
    button.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(CONTEXT_ACTION_BUTTON_STYLE)
    return button


def length_field_button(text: str, tooltip: str) -> QToolButton:
    button = segment_button(text, tooltip)
    button.setObjectName("bondLengthField")
    button.setStyleSheet(
        CONTEXT_SEGMENT_STYLE
        + "QToolButton#bondLengthField {"
        f" background: {_P['surface_input']};"
        f" border-color: {_P['border_strong']};"
        " font-family: Menlo, Monaco, Consolas, monospace;"
        " padding: 0px 7px;"
        "}"
    )
    return button


def _configure_arrow_compact_slider(slider: QSlider) -> QSlider:
    slider.setObjectName("arrowCompactSlider")
    slider.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
    slider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    slider.setStyleSheet(_ARROW_COMPACT_SLIDER_STYLE)
    return slider


def slider_dropdown_button(icon, tooltip: str, slider: QSlider) -> QToolButton:
    button = icon_button(icon, tooltip)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(button)
    menu.setStyleSheet(_ARROW_SLIDER_MENU_STYLE)
    slider.setFixedWidth(120)
    _configure_arrow_compact_slider(slider)

    container = QWidget(menu)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(slider)

    action = QWidgetAction(menu)
    action.setDefaultWidget(container)
    menu.addAction(action)
    button.setMenu(menu)
    return button


def atom_symbol_input(current_symbol: str, set_symbol) -> QLineEdit:
    input_box = QLineEdit()
    input_box.setObjectName("atomInput")
    input_box.setPlaceholderText("Atom")
    input_box.setMinimumWidth(60)
    input_box.setMaximumWidth(240)
    input_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    input_box.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
    input_box.setMaxLength(255)
    input_box.setText(current_symbol)
    input_box.setToolTip("Atom Symbol")
    input_box.setStatusTip("Set the atom symbol used by atom and bond tools")
    input_box.textChanged.connect(set_symbol)
    return input_box


def rotate_angle_input() -> tuple[QWidget, QSpinBox]:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    spin = QSpinBox()
    spin.setObjectName("rotateAngleInput")
    spin.setRange(-180, 180)
    spin.setValue(15)
    spin.setSuffix("°")
    spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    spin.setFixedWidth(56)
    spin.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT + 4)
    spin.setToolTip("Rotation angle")
    spin.setStatusTip("Enter a rotation angle from -180 to 180 degrees")
    layout.addWidget(spin)

    stepper = QFrame()
    stepper.setObjectName("rotateStepper")
    stepper.setFixedSize(22, CONTEXT_BAR_BUTTON_HEIGHT + 4)
    stepper.setStyleSheet(
        "QFrame#rotateStepper {"
        f" background: {_P['surface_input']};"
        f" border: 1px solid {_P['border_strong']};"
        " border-radius: 6px;"
        "}"
        "QFrame#rotateStepper QToolButton { background: transparent; border: none; }"
        f"QFrame#rotateStepper QToolButton:hover {{ background: {_P['hover']}; border-radius: 4px; }}"
    )
    stepper_col = QVBoxLayout(stepper)
    stepper_col.setContentsMargins(0, 1, 0, 1)
    stepper_col.setSpacing(0)
    up_btn = _StepArrowButton("up")
    up_btn.setFixedSize(20, 13)
    up_btn.setToolTip("Increase angle")
    up_btn.clicked.connect(spin.stepUp)
    down_btn = _StepArrowButton("down")
    down_btn.setFixedSize(20, 13)
    down_btn.setToolTip("Decrease angle")
    down_btn.clicked.connect(spin.stepDown)
    stepper_col.addWidget(up_btn)
    stepper_col.addWidget(down_btn)
    layout.addWidget(stepper)
    return container, spin


def bond_length_input(current_px: float, on_commit) -> tuple[QWidget, QSpinBox]:
    """Inline bond-length editor: a px spin box plus a compact stepper.

    Replaces the modal "Set bond length" dialog. The new value is committed
    (``on_commit(value)``) when editing finishes or a stepper arrow is clicked,
    not on every intermediate keystroke, so each change is a single history
    entry rather than a flood of partial rescales.
    """
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    spin = QSpinBox()
    spin.setObjectName("bondLengthInput")
    spin.setRange(10, 200)
    spin.setValue(max(10, min(200, int(round(current_px)))))
    spin.setSuffix(" px")
    spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    spin.setFixedWidth(64)
    spin.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT + 4)
    spin.setToolTip("Default bond length")
    spin.setStatusTip("Set the default bond length in pixels")

    def commit() -> None:
        on_commit(spin.value())

    spin.editingFinished.connect(commit)

    def step(delta: int) -> None:
        spin.setValue(spin.value() + delta)
        commit()

    layout.addWidget(spin)

    stepper = QFrame()
    stepper.setObjectName("bondLengthStepper")
    stepper.setFixedSize(22, CONTEXT_BAR_BUTTON_HEIGHT + 4)
    stepper.setStyleSheet(
        "QFrame#bondLengthStepper {"
        f" background: {_P['surface_input']};"
        f" border: 1px solid {_P['border_strong']};"
        " border-radius: 6px;"
        "}"
        "QFrame#bondLengthStepper QToolButton { background: transparent; border: none; }"
        f"QFrame#bondLengthStepper QToolButton:hover {{ background: {_P['hover']}; border-radius: 4px; }}"
    )
    stepper_col = QVBoxLayout(stepper)
    stepper_col.setContentsMargins(0, 1, 0, 1)
    stepper_col.setSpacing(0)
    up_btn = _StepArrowButton("up")
    up_btn.setFixedSize(20, 13)
    up_btn.setToolTip("Increase bond length")
    up_btn.clicked.connect(lambda _checked=False: step(spin.singleStep()))
    down_btn = _StepArrowButton("down")
    down_btn.setFixedSize(20, 13)
    down_btn.setToolTip("Decrease bond length")
    down_btn.clicked.connect(lambda _checked=False: step(-spin.singleStep()))
    stepper_col.addWidget(up_btn)
    stepper_col.addWidget(down_btn)
    layout.addWidget(stepper)
    return container, spin


def color_swatch_button(label: str, hex_value: str, tooltip_prefix: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName(f"{tooltip_prefix.lower().replace(' ', '_')}_swatch_{label.lower()}")
    button.setFixedSize(TOOLBAR_BUTTON_SIZE, TOOLBAR_BUTTON_SIZE)
    button.setToolTip(f"{tooltip_prefix}: {label}")
    button.setStatusTip(f"{tooltip_prefix}: {label}")
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        "QToolButton {"
        f" background-color: {hex_value};"
        f" border: 1px solid {_P['icon_muted']};"
        " border-radius: 5px;"
        " padding: 0px;"
        "}"
        f"QToolButton:hover {{ border: 2px solid {_P['accent']}; }}"
        f"QToolButton:pressed {{ border: 2px solid {_P['accent_pressed']}; }}"
    )
    return button


__all__ = [
    "action_button",
    "atom_symbol_input",
    "bond_length_input",
    "color_swatch_button",
    "divider",
    "hint_label",
    "icon_button",
    "icon_menu_button",
    "length_field_button",
    "new_context_page",
    "rotate_angle_input",
    "segment_button",
    "slider_dropdown_button",
]
