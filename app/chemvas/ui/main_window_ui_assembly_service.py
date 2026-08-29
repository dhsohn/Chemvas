from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt

from chemvas.ui.main_window_menu_bar import MainWindowMenuBarAssembly, build_menu_bar
from chemvas.ui.main_window_panel_toolbar import (
    MainWindowPanelToolbarAssembly,
    MainWindowPanelToolbarCallbacks,
    build_panel_toolbar,
)
from chemvas.ui.main_window_theme import (
    MAIN_WINDOW_STYLESHEET,
)
from chemvas.ui.main_window_toolbar_buttons import (
    MainWindowToolbarButtonFactory,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QToolButton


class MainWindowUIAssemblyService:
    def __init__(
        self,
        *,
        scene_transform_controller_for_window,
        insert_controller_for_window,
        build_tool_actions_for_window,
        panel_toolbar_callbacks: MainWindowPanelToolbarCallbacks,
    ) -> None:
        self._scene_transform_controller_for_window = (
            scene_transform_controller_for_window
        )
        self._insert_controller_for_window = insert_controller_for_window
        self._build_tool_actions_for_window = build_tool_actions_for_window
        self._panel_toolbar_callbacks = panel_toolbar_callbacks
        self._buttons = MainWindowToolbarButtonFactory()

    def create_toolbar_button(
        self,
        *,
        icon: QIcon | None = None,
        tooltip: str | None = None,
        status_tip: str | None = None,
        callback: Callable[[], None] | None = None,
        shortcut=None,
        text: str | None = None,
        object_name: str | None = None,
        style_sheet: str | None = None,
        auto_raise: bool = True,
        cursor=None,
    ) -> QToolButton:
        return self._buttons.create_toolbar_button(
            icon=icon,
            tooltip=tooltip,
            status_tip=status_tip,
            callback=callback,
            shortcut=shortcut,
            text=text,
            object_name=object_name,
            style_sheet=style_sheet,
            auto_raise=auto_raise,
            cursor=cursor,
        )

    def init_toolbars(self, window) -> MainWindowPanelToolbarAssembly:
        panel_toolbar = build_panel_toolbar(
            window,
            create_toolbar_button=self.create_toolbar_button,
            build_tool_actions=self._build_tool_actions_for_window,
            scene_transform_controller_for_window=self._scene_transform_controller_for_window,
            insert_controller_for_window=self._insert_controller_for_window,
            callbacks=self._panel_toolbar_callbacks,
        )
        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, panel_toolbar.panel_bar)
        return panel_toolbar

    def init_menu_bar(self, window) -> MainWindowMenuBarAssembly:
        return build_menu_bar(window, callbacks=self._panel_toolbar_callbacks)

    def apply_theme(self, window) -> None:
        window.setStyleSheet(MAIN_WINDOW_STYLESHEET)


__all__ = [
    "MainWindowUIAssemblyService",
]
