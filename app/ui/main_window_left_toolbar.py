from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QToolBar, QToolButton

from ui.main_window_config import LEFT_TOOLBAR_GROUPS
from ui.main_window_theme import LEFT_TOOLBAR_BUTTON_STYLE


@dataclass(frozen=True)
class MainWindowLeftToolbarAssembly:
    left_bar: QToolBar
    tool_actions: dict[str, QAction]


def _normalize_left_toolbar_button(left_bar: QToolBar, action: QAction, action_key: str) -> None:
    widget = left_bar.widgetForAction(action)
    if not isinstance(widget, QToolButton):
        return
    widget.setObjectName(f"leftToolButton_{action_key}")
    widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    widget.setIcon(action.icon())
    widget.setIconSize(left_bar.iconSize())
    widget.setAutoRaise(True)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def build_left_toolbar(
    window,
    *,
    build_tool_actions: Callable[[object, QActionGroup], dict[str, QAction]],
) -> MainWindowLeftToolbarAssembly:
    tool_group = QActionGroup(window)
    tool_group.setExclusive(True)

    left_bar = QToolBar("Tools", window)
    left_bar.setOrientation(Qt.Orientation.Vertical)
    left_bar.setMovable(False)
    left_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    left_bar.setIconSize(QSize(20, 20))
    left_bar.setStyleSheet(LEFT_TOOLBAR_BUTTON_STYLE)

    tool_actions = build_tool_actions(window, tool_group)
    for group_index, action_keys in enumerate(LEFT_TOOLBAR_GROUPS):
        if group_index:
            left_bar.addSeparator()
        for action_key in action_keys:
            action = tool_actions[action_key]
            left_bar.addAction(action)
            _normalize_left_toolbar_button(left_bar, action, action_key)

    tool_actions["bond"].setChecked(True)
    return MainWindowLeftToolbarAssembly(left_bar=left_bar, tool_actions=tool_actions)


__all__ = ["MainWindowLeftToolbarAssembly", "build_left_toolbar"]
