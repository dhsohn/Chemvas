from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSlider,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from ui.main_window_palette import PALETTE
from ui.main_window_theme import (
    CONTEXT_BAR_BUTTON_HEIGHT,
    CONTEXT_BAR_ICON_SIZE,
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
)

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
    " border-radius: 0px;"
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
    line.setStyleSheet("color: #e0e0dd;")
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
        " border: 1px solid #8a8a84;"
        " border-radius: 5px;"
        " padding: 0px;"
        "}"
        "QToolButton:hover { border: 2px solid #0d9488; }"
        "QToolButton:pressed { border: 2px solid #075f57; }"
    )
    return button


__all__ = [
    "color_swatch_button",
    "divider",
    "hint_label",
    "icon_button",
    "new_context_page",
    "slider_dropdown_button",
]
