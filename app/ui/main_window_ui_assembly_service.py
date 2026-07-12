from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QMenu,
    QMenuBar,
    QToolBar,
    QToolButton,
)

from ui.main_window_menu_bar import build_menu_bar
from ui.main_window_panel_toolbar import (
    MainWindowPanelToolbarCallbacks,
    build_panel_toolbar,
)
from ui.main_window_theme import (
    MAIN_WINDOW_STYLESHEET,
)
from ui.main_window_toolbar_buttons import (
    CornerMenuButton,
    MainWindowToolbarButtonFactory,
)


@dataclass(frozen=True)
class MainWindowToolbarAssembly:
    panel_bar: QToolBar
    tool_actions: dict[str, QAction]
    save_action: QAction
    save_as_action: QAction
    save_button: QToolButton
    load_action: QAction | None = None
    export_xyz_button: QToolButton | None = None
    preview_panel_button: QToolButton | None = None
    new_canvas_button: QToolButton | None = None
    undo_button: QToolButton | None = None
    redo_button: QToolButton | None = None


class MainWindowUIAssemblyService:
    def __init__(
        self,
        *,
        scene_transform_controller_for_window,
        insert_controller_for_window,
        history_service_for_window,
        build_tool_actions_for_window,
        panel_toolbar_callbacks: MainWindowPanelToolbarCallbacks,
    ) -> None:
        self._scene_transform_controller_for_window = scene_transform_controller_for_window
        self._insert_controller_for_window = insert_controller_for_window
        self._history_service_for_window = history_service_for_window
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

    def create_corner_menu_button(
        self,
        *,
        icon: QIcon | None = None,
        tooltip: str | None = None,
        status_tip: str | None = None,
        style_sheet: str,
        popup_mode: QToolButton.ToolButtonPopupMode,
        menu_builder: Callable[[QMenu], None],
        default_action: QAction | None = None,
    ) -> CornerMenuButton:
        return self._buttons.create_corner_menu_button(
            icon=icon,
            tooltip=tooltip,
            status_tip=status_tip,
            style_sheet=style_sheet,
            popup_mode=popup_mode,
            menu_builder=menu_builder,
            default_action=default_action,
        )

    def create_save_menu_button(self, save_action: QAction, save_as_action: QAction) -> CornerMenuButton:
        return self._buttons.create_save_menu_button(save_action, save_as_action)

    def create_file_project_menu_button(
        self,
        save_action: QAction,
        load_action: QAction,
        save_as_action: QAction,
        *export_actions: QAction,
    ) -> CornerMenuButton:
        return self._buttons.create_file_project_menu_button(
            save_action,
            load_action,
            save_as_action,
            *export_actions,
        )

    def init_toolbars(self, window) -> MainWindowToolbarAssembly:
        panel_toolbar = build_panel_toolbar(
            window,
            create_toolbar_button=self.create_toolbar_button,
            create_file_project_menu_button=self.create_file_project_menu_button,
            create_corner_menu_button=self.create_corner_menu_button,
            build_tool_actions=self._build_tool_actions_for_window,
            scene_transform_controller_for_window=self._scene_transform_controller_for_window,
            insert_controller_for_window=self._insert_controller_for_window,
            history_service_for_window=self._history_service_for_window,
            callbacks=self._panel_toolbar_callbacks,
        )
        panel_bar = panel_toolbar.panel_bar
        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, panel_bar)
        return MainWindowToolbarAssembly(
            panel_bar=panel_bar,
            tool_actions=panel_toolbar.tool_actions,
            save_action=panel_toolbar.save_action,
            save_as_action=panel_toolbar.save_as_action,
            save_button=panel_toolbar.save_button,
            load_action=panel_toolbar.load_action,
            export_xyz_button=panel_toolbar.export_xyz_button,
            preview_panel_button=panel_toolbar.preview_panel_button,
            new_canvas_button=panel_toolbar.new_canvas_button,
            undo_button=panel_toolbar.undo_button,
            redo_button=panel_toolbar.redo_button,
        )

    def init_menu_bar(self, window) -> QMenuBar:
        return build_menu_bar(window)

    def apply_theme(self, window) -> None:
        window.setStyleSheet(MAIN_WINDOW_STYLESHEET)


__all__ = [
    "MainWindowToolbarAssembly",
    "MainWindowUIAssemblyService",
]
