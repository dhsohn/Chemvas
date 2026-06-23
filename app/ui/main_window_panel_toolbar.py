from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import QSizePolicy, QToolBar, QToolButton, QWidget

from ui.main_window_config import (
    TOOLBAR_PRIMARY_TOOL_GROUP,
    TOOLBAR_TOOL_GROUPS,
)
from ui.main_window_theme import (
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
    TOOLBAR_THICKNESS,
)
from ui.main_window_ui_ports import icon_factory_for_window


@dataclass(frozen=True)
class MainWindowPanelToolbarAssembly:
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


@dataclass(frozen=True)
class MainWindowPanelToolbarCallbacks:
    save_canvas: Callable[[object], Any]
    save_canvas_as: Callable[[object], Any]
    load_canvas: Callable[[object], Any]
    export_figure: Callable[[object], None]
    export_mol: Callable[[object], None]
    open_preview_window: Callable[[object], None]
    new_canvas: Callable[[object], Any]


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


def build_panel_toolbar(
    window,
    *,
    create_toolbar_button: Callable[..., QToolButton],
    create_file_project_menu_button: Callable[..., QToolButton],
    create_corner_menu_button: Callable[..., QToolButton],
    build_tool_actions: Callable[[object, QActionGroup], dict[str, QAction]],
    scene_transform_controller_for_window,
    insert_controller_for_window,
    history_service_for_window,
    callbacks: MainWindowPanelToolbarCallbacks,
) -> MainWindowPanelToolbarAssembly:
    panel_bar = QToolBar("Panels", window)
    panel_bar.setObjectName("topRoleToolbar")
    panel_bar.setMovable(False)
    panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    panel_bar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
    panel_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)
    panel_bar.setFixedHeight(TOOLBAR_THICKNESS)
    icon_factory = icon_factory_for_window(window)
    tool_group = QActionGroup(window)
    tool_group.setExclusive(True)
    tool_actions = build_tool_actions(window, tool_group)
    tool_actions["bond"].setChecked(True)

    save_action = QAction("Save", window)
    save_action.setIcon(icon_factory.icon_save())
    save_action.setToolTip("Save")
    save_action.setStatusTip("Save the current drawing")
    save_action.setShortcut(QKeySequence.StandardKey.Save)
    save_action.triggered.connect(lambda _checked=False: callbacks.save_canvas(window))
    window.addAction(save_action)

    save_as_action = QAction("Save As...", window)
    save_as_action.setToolTip("Save As")
    save_as_action.setStatusTip("Save the current drawing to a new file")
    save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
    save_as_action.triggered.connect(lambda _checked=False: callbacks.save_canvas_as(window))
    window.addAction(save_as_action)

    load_action = QAction("Load", window)
    load_action.setIcon(icon_factory.icon_open())
    load_action.setToolTip("Load")
    load_action.setStatusTip("Open a drawing")
    load_action.setShortcut(QKeySequence.StandardKey.Open)
    load_action.triggered.connect(lambda _checked=False: callbacks.load_canvas(window))
    window.addAction(load_action)

    export_figure_action = QAction("Export Figure...", window)
    export_figure_action.setToolTip("Export Figure")
    export_figure_action.setStatusTip("Export the drawing as SVG, PDF, or high-resolution PNG/TIFF")
    export_figure_action.triggered.connect(lambda _checked=False: callbacks.export_figure(window))
    window.addAction(export_figure_action)

    export_mol_action = QAction("Export MOL...", window)
    export_mol_action.setToolTip("Export MOL")
    export_mol_action.setStatusTip("Export the selected structure as an MDL Molfile (.mol)")
    export_mol_action.triggered.connect(lambda _checked=False: callbacks.export_mol(window))
    window.addAction(export_mol_action)

    save_button = create_file_project_menu_button(
        save_action, load_action, save_as_action, export_figure_action, export_mol_action
    )
    preview_panel_btn = create_toolbar_button(
        icon=icon_factory.icon_preview_panel(),
        tooltip="Molecule Info",
        status_tip="Open the selected molecule in a separate molecule info window",
        callback=lambda _checked=False: callbacks.open_preview_window(window),
        object_name="preview_panel_button",
    )
    load_btn = create_toolbar_button(
        icon=icon_factory.icon_open(),
        tooltip="Open",
        status_tip="Open a drawing",
        callback=lambda _checked=False: callbacks.load_canvas(window),
        object_name="open_button",
    )
    new_canvas_btn = create_toolbar_button(
        icon=icon_factory.icon_add_canvas(),
        tooltip="New Canvas",
        status_tip="Create a new canvas",
        callback=lambda _checked=False: callbacks.new_canvas(window),
        object_name="new_canvas_button",
    )
    undo_btn = create_toolbar_button(
        icon=icon_factory.icon_undo(),
        tooltip="Undo",
        status_tip="Undo the last edit",
        callback=lambda: history_service_for_window(window).undo(),
        shortcut=QKeySequence.StandardKey.Undo,
        object_name="undo_button",
    )
    redo_btn = create_toolbar_button(
        icon=icon_factory.icon_redo(),
        tooltip="Redo",
        status_tip="Redo the last undone edit",
        callback=lambda: history_service_for_window(window).redo(),
        shortcut=QKeySequence.StandardKey.Redo,
        object_name="redo_button",
    )
    scene_transform_controller = scene_transform_controller_for_window(window)
    flip_h_btn = create_toolbar_button(
        icon=icon_factory.icon_flip_h(),
        tooltip="Flip Horizontal (Ctrl+Shift+H)",
        status_tip="Flip the current selection horizontally",
        callback=lambda: scene_transform_controller.flip_selected_items(horizontal=True),
        object_name="flip_horizontal_button",
    )
    flip_v_btn = create_toolbar_button(
        icon=icon_factory.icon_flip_v(),
        tooltip="Flip Vertical (Ctrl+Shift+V)",
        status_tip="Flip the current selection vertically",
        callback=lambda: scene_transform_controller.flip_selected_items(horizontal=False),
        object_name="flip_vertical_button",
    )

    for action_key in TOOLBAR_PRIMARY_TOOL_GROUP:
        action = tool_actions[action_key]
        panel_bar.addAction(action)
        _normalize_tool_action_button(panel_bar, action, action_key, primary=True)
    panel_bar.addSeparator()
    for group_index, action_keys in enumerate(TOOLBAR_TOOL_GROUPS[1:]):
        for action_key in action_keys:
            action = tool_actions[action_key]
            panel_bar.addAction(action)
            _normalize_tool_action_button(panel_bar, action, action_key)
        if group_index < len(TOOLBAR_TOOL_GROUPS[1:]) - 1:
            panel_bar.addSeparator()
    panel_bar.addSeparator()
    panel_bar.addWidget(flip_h_btn)
    panel_bar.addWidget(flip_v_btn)
    panel_bar.addSeparator()
    panel_bar.addWidget(_toolbar_spacer())
    panel_bar.addWidget(undo_btn)
    panel_bar.addWidget(redo_btn)
    panel_bar.addSeparator()
    panel_bar.addWidget(preview_panel_btn)
    panel_bar.addWidget(load_btn)
    panel_bar.addWidget(save_button)
    panel_bar.addWidget(new_canvas_btn)

    for button in (
        save_button,
        preview_panel_btn,
        load_btn,
        new_canvas_btn,
        undo_btn,
        redo_btn,
        flip_h_btn,
        flip_v_btn,
    ):
        button.setIconSize(panel_bar.iconSize())
        button.setFixedHeight(TOOLBAR_BUTTON_SIZE)
        button.setProperty("iconOnly", True)
        if button.text() == "":
            button.setFixedWidth(TOOLBAR_BUTTON_SIZE)

    return MainWindowPanelToolbarAssembly(
        panel_bar=panel_bar,
        tool_actions=tool_actions,
        save_action=save_action,
        save_as_action=save_as_action,
        save_button=save_button,
        load_action=load_action,
        export_xyz_button=None,
        preview_panel_button=preview_panel_btn,
        new_canvas_button=new_canvas_btn,
        undo_button=undo_btn,
        redo_button=redo_btn,
    )


__all__ = [
    "MainWindowPanelToolbarAssembly",
    "MainWindowPanelToolbarCallbacks",
    "build_panel_toolbar",
]
