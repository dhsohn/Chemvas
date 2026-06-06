from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from ui.main_window_theme import TOOLBAR_BUTTON_STYLE

_ICON_SIZE = QSize(22, 22)


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


def icon_button(icon, tooltip: str, *, checkable: bool = False) -> QToolButton:
    button = QToolButton()
    button.setIcon(icon)
    button.setIconSize(_ICON_SIZE)
    button.setToolTip(tooltip)
    button.setAutoRaise(True)
    button.setCheckable(checkable)
    button.setStyleSheet(TOOLBAR_BUTTON_STYLE)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def text_button(text: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.setAutoRaise(True)
    button.setStyleSheet(TOOLBAR_BUTTON_STYLE)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


__all__ = [
    "divider",
    "hint_label",
    "icon_button",
    "new_context_page",
    "text_button",
]
