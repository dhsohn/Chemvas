from __future__ import annotations

from PyQt6.QtCore import Qt

from chemvas.shell.theme import (
    MAIN_WINDOW_STYLESHEET,
)
from chemvas.ui.main_window_menu_bar import MainWindowMenuBarAssembly, build_menu_bar
from chemvas.ui.main_window_panel_toolbar import (
    MainWindowPanelToolbarAssembly,
    MainWindowPanelToolbarCallbacks,
    build_panel_toolbar,
)


class MainWindowUIAssemblyService:
    def __init__(
        self,
        *,
        build_tool_actions_for_window,
        panel_toolbar_callbacks: MainWindowPanelToolbarCallbacks,
    ) -> None:
        self._build_tool_actions_for_window = build_tool_actions_for_window
        self._panel_toolbar_callbacks = panel_toolbar_callbacks

    def init_toolbars(self, window) -> MainWindowPanelToolbarAssembly:
        panel_toolbar = build_panel_toolbar(
            window,
            build_tool_actions=self._build_tool_actions_for_window,
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
