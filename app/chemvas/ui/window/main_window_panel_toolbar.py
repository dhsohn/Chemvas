from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QFont
from PyQt6.QtWidgets import (
    QMenu,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from chemvas.shell.theme import (
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
)
from chemvas.shell.toolbar_buttons import CornerMenuToolButton
from chemvas.ui.window.main_window_config import (
    TEXT_FONT_FAMILY_CHOICES,
    TOOLBAR_TOOL_ACTION_ORDER,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QResizeEvent, QShowEvent

    from chemvas.ui.window.main_window_like import MainWindowLike

_TOOLBAR_ROW_REGULAR_GAP = 2
_TOOLBAR_ROW_GROUP_GAP = 8
_TOOLBAR_ROW_GROUP_GAP_AFTER = frozenset({0, 3, 8, 10})
_TOOLBAR_ROW_MIN_BUTTON_WIDTH = 26
_TOOLBAR_ROW_MAX_BUTTON_WIDTH = 80

_LABELED_TOOLBAR_STYLE = (
    TOOLBAR_BUTTON_STYLE
    + "QToolBar#topRoleToolbar { spacing: 2px; padding: 1px 4px; }"
    + "QToolBar::separator { margin: 7px 3px; }"
    + "QToolButton { padding: 0px 2px; font-size: 11px; font-weight: 400; }"
)

_NOTE_TOOL_MENU_BUTTON_STYLE = (
    _LABELED_TOOLBAR_STYLE
    + "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
)


@dataclass(frozen=True)
class MainWindowPanelToolbarAssembly:
    panel_bar: QToolBar
    tool_actions: dict[str, QAction]


@dataclass(frozen=True, kw_only=True)
class MainWindowPanelToolbarCallbacks:
    save_canvas: Callable[[MainWindowLike], Any]
    save_canvas_as: Callable[[MainWindowLike], Any]
    load_canvas: Callable[[MainWindowLike], Any]
    export_figure: Callable[[MainWindowLike], None]
    export_mol: Callable[[MainWindowLike], None]
    new_canvas: Callable[[MainWindowLike], Any]
    show_rotate_options: Callable[[MainWindowLike], None]
    set_note_font_family: Callable[[MainWindowLike, str], None]
    open_recent_path: Callable[[MainWindowLike, str], Any]


class _ToolButtonRow(QWidget):
    def __init__(self, buttons: list[QToolButton]) -> None:
        super().__init__()
        self._buttons = buttons
        self._natural_widths: list[int] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(
            len(buttons) * _TOOLBAR_ROW_MIN_BUTTON_WIDTH
            + max(0, len(buttons) - 1) * _TOOLBAR_ROW_REGULAR_GAP
        )
        self.setFixedHeight(42)
        for button in buttons:
            button.setParent(self)
        self._refresh_natural_widths()

    def _gap_after_index(self, index: int) -> int:
        if index in _TOOLBAR_ROW_GROUP_GAP_AFTER:
            return _TOOLBAR_ROW_GROUP_GAP
        return _TOOLBAR_ROW_REGULAR_GAP

    def _refresh_natural_widths(self) -> None:
        self._natural_widths = [
            max(_TOOLBAR_ROW_MIN_BUTTON_WIDTH, button.sizeHint().width())
            for button in self._buttons
        ]

    def _layout_widths_and_gaps(self, available: int) -> tuple[list[int], list[int]]:
        count = len(self._buttons)
        if count == 0:
            return [], []

        widths = list(self._natural_widths)
        gaps = [self._gap_after_index(i) for i in range(count - 1)]
        # Keep every label's natural width before spending space on grouping.
        if sum(widths) + sum(gaps) > available:
            gaps = [_TOOLBAR_ROW_REGULAR_GAP] * (count - 1)

        delta = available - sum(gaps) - sum(widths)
        limits = [
            width - _TOOLBAR_ROW_MIN_BUTTON_WIDTH
            if delta < 0
            else max(0, _TOOLBAR_ROW_MAX_BUTTON_WIDTH - width)
            for width in widths
        ]
        total = sum(limits)
        if total:
            amount = min(abs(delta), total)
            cumulative = previous = 0
            for index, limit in enumerate(limits):
                cumulative += limit
                allocated = amount * cumulative // total
                change = allocated - previous
                widths[index] += -change if delta < 0 else change
                previous = allocated
        return widths, gaps

    def _apply_layout(self) -> None:
        if not self._buttons:
            return
        self._refresh_natural_widths()
        available = max(0, self.width())
        widths, gaps = self._layout_widths_and_gaps(available)
        x = 0
        for index, button in enumerate(self._buttons):
            button.setGeometry(x, 0, widths[index], 42)
            if index < len(gaps):
                x += widths[index] + gaps[index]
            else:
                x += widths[index]

    @override
    def sizeHint(self) -> QSize:
        self._refresh_natural_widths()
        gap_total = sum(self._gap_after_index(i) for i in range(len(self._buttons) - 1))
        return QSize(sum(self._natural_widths) + gap_total, 42)

    @override
    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self._apply_layout()

    @override
    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._apply_layout()


def _build_tool_action_button(
    panel_bar: QToolBar,
    action: QAction,
    action_key: str,
) -> QToolButton:
    button = QToolButton()
    button.setDefaultAction(action)
    button.setObjectName(f"toolButton_{action_key}")
    button.setIconSize(panel_bar.iconSize())
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setFixedHeight(42)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    return button


def _build_note_font_menu_button(
    panel_bar: QToolBar,
    window: MainWindowLike,
    action: QAction,
    callbacks: MainWindowPanelToolbarCallbacks,
) -> QToolButton:
    button = CornerMenuToolButton()
    button.setDefaultAction(action)
    menu = QMenu(button)
    for family in TEXT_FONT_FAMILY_CHOICES:
        font_action = menu.addAction(family)
        if font_action is not None:
            preview_font = QFont(family)
            preview_font.setPointSize(13)
            font_action.setFont(preview_font)
            font_action.triggered.connect(
                lambda _checked=False, value=family: callbacks.set_note_font_family(
                    window, value
                )
            )
    button.setMenu(menu)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)
    button.setObjectName("toolButton_note")
    button.setIcon(action.icon())
    button.setIconSize(panel_bar.iconSize())
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setToolTip(action.toolTip())
    button.setStatusTip(action.statusTip() or action.toolTip())
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setStyleSheet(_NOTE_TOOL_MENU_BUTTON_STYLE)
    button.setFixedHeight(42)
    return button


def build_panel_toolbar(
    window: MainWindowLike,
    *,
    build_tool_actions: Callable[[MainWindowLike, QActionGroup], dict[str, QAction]],
    callbacks: MainWindowPanelToolbarCallbacks,
) -> MainWindowPanelToolbarAssembly:
    panel_bar = QToolBar("Panels", window)
    panel_bar.setObjectName("topRoleToolbar")
    panel_bar.setMovable(False)
    panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    panel_bar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
    panel_bar.setStyleSheet(_LABELED_TOOLBAR_STYLE)
    panel_bar.setMinimumHeight(48)
    tool_group = QActionGroup(window)
    tool_group.setExclusive(True)
    tool_actions = build_tool_actions(window, tool_group)
    tool_actions["bond"].setChecked(True)

    buttons = [
        _build_note_font_menu_button(panel_bar, window, tool_actions[key], callbacks)
        if key == "note"
        else _build_tool_action_button(panel_bar, tool_actions[key], key)
        for key in TOOLBAR_TOOL_ACTION_ORDER
    ]
    panel_bar.addWidget(_ToolButtonRow(buttons))

    return MainWindowPanelToolbarAssembly(
        panel_bar=panel_bar,
        tool_actions=tool_actions,
    )


__all__ = [
    "MainWindowPanelToolbarAssembly",
    "MainWindowPanelToolbarCallbacks",
    "build_panel_toolbar",
]
