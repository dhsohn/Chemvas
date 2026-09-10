from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
    TOOLBAR_THICKNESS,
)
from chemvas.shell.toolbar_buttons import CornerMenuToolButton
from chemvas.ui.main_window_config import (
    TEXT_FONT_FAMILY_CHOICES,
    TOOLBAR_PRIMARY_TOOL_GROUP,
    TOOLBAR_TOOL_GROUPS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_NOTE_TOOL_MENU_BUTTON_STYLE = (
    TOOLBAR_BUTTON_STYLE
    + "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
)


@dataclass(frozen=True)
class MainWindowPanelToolbarAssembly:
    panel_bar: QToolBar
    tool_actions: dict[str, QAction]


@dataclass(frozen=True, kw_only=True)
class MainWindowPanelToolbarCallbacks:
    save_canvas: Callable[[object], Any]
    save_canvas_as: Callable[[object], Any]
    load_canvas: Callable[[object], Any]
    export_figure: Callable[[object], None]
    export_mol: Callable[[object], None]
    open_preview_window: Callable[[object], None]
    new_canvas: Callable[[object], Any]
    show_rotate_options: Callable[[object], None]
    set_note_font_family: Callable[[object, str], None]
    open_recent_path: Callable[[object, str], Any]


def _normalize_tool_action_button(
    panel_bar: QToolBar,
    action: QAction,
    action_key: str,
    *,
    primary: bool = False,
) -> None:
    widget = panel_bar.widgetForAction(action)
    if not isinstance(widget, QToolButton):
        return
    widget.setObjectName(f"toolButton_{action_key}")
    widget.setIcon(action.icon())
    widget.setIconSize(panel_bar.iconSize())
    widget.setAutoRaise(True)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    widget.setFixedHeight(TOOLBAR_BUTTON_SIZE)
    if primary:
        widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        widget.setText("")
        widget.setProperty("iconOnly", True)
        widget.setFixedWidth(TOOLBAR_BUTTON_SIZE)
        return
    widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    widget.setProperty("iconOnly", True)
    widget.setFixedWidth(TOOLBAR_BUTTON_SIZE)


def _toolbar_spacer() -> QWidget:
    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return spacer


# The breathing room between button groups; there is no divider line, the
# gap alone says where one group ends and the next begins.
TOOLBAR_GROUP_GAP_PX = 12


def _toolbar_group_gap() -> QWidget:
    gap = QWidget()
    gap.setObjectName("toolbarGroupGap")
    gap.setFixedWidth(TOOLBAR_GROUP_GAP_PX)
    return gap


def _build_note_font_menu_button(
    panel_bar: QToolBar,
    window,
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
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setText("")
    button.setToolTip(action.toolTip())
    button.setStatusTip(action.statusTip() or action.toolTip())
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setStyleSheet(_NOTE_TOOL_MENU_BUTTON_STYLE)
    button.setFixedSize(TOOLBAR_BUTTON_SIZE, TOOLBAR_BUTTON_SIZE)
    button.setProperty("primaryTool", True)
    return button


def build_panel_toolbar(
    window,
    *,
    build_tool_actions: Callable[[object, QActionGroup], dict[str, QAction]],
    callbacks: MainWindowPanelToolbarCallbacks,
) -> MainWindowPanelToolbarAssembly:
    panel_bar = QToolBar("Panels", window)
    panel_bar.setObjectName("topRoleToolbar")
    panel_bar.setMovable(False)
    panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    panel_bar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
    panel_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)
    panel_bar.setFixedHeight(TOOLBAR_THICKNESS)
    tool_group = QActionGroup(window)
    tool_group.setExclusive(True)
    tool_actions = build_tool_actions(window, tool_group)
    tool_actions["bond"].setChecked(True)

    def add_tool(action_key: str, *, primary: bool) -> None:
        action = tool_actions[action_key]
        if action_key == "note":
            panel_bar.addWidget(
                _build_note_font_menu_button(panel_bar, window, action, callbacks)
            )
            return
        panel_bar.addAction(action)
        _normalize_tool_action_button(panel_bar, action, action_key, primary=primary)

    for action_key in TOOLBAR_PRIMARY_TOOL_GROUP:
        add_tool(action_key, primary=True)
    panel_bar.addWidget(_toolbar_group_gap())
    for group_index, action_keys in enumerate(TOOLBAR_TOOL_GROUPS[1:]):
        for action_key in action_keys:
            add_tool(action_key, primary=False)
        if group_index < len(TOOLBAR_TOOL_GROUPS[1:]) - 1:
            panel_bar.addWidget(_toolbar_group_gap())
    panel_bar.addWidget(_toolbar_spacer())

    return MainWindowPanelToolbarAssembly(
        panel_bar=panel_bar,
        tool_actions=tool_actions,
    )


__all__ = [
    "MainWindowPanelToolbarAssembly",
    "MainWindowPanelToolbarCallbacks",
    "build_panel_toolbar",
]
