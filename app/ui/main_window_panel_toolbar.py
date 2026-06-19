from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import QLineEdit, QToolBar, QToolButton

from ui.main_window_config import TOOLBAR_TOOL_GROUPS, TOOLBAR_TRANSFORM_TOOL_GROUP
from ui.main_window_theme import (
    SMILES_RENDER_BUTTON_STYLE,
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
    undo_button: QToolButton | None = None
    redo_button: QToolButton | None = None


@dataclass(frozen=True)
class MainWindowPanelToolbarCallbacks:
    save_canvas: Callable[[object], None]
    save_canvas_as: Callable[[object], None]
    load_canvas: Callable[[object], None]
    export_figure: Callable[[object], None]
    open_preview_window: Callable[[object], None]


def _normalize_tool_action_button(panel_bar: QToolBar, action: QAction, action_key: str) -> None:
    widget = panel_bar.widgetForAction(action)
    if not isinstance(widget, QToolButton):
        return
    widget.setObjectName(f"toolButton_{action_key}")
    widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    widget.setIcon(action.icon())
    widget.setIconSize(panel_bar.iconSize())
    widget.setAutoRaise(True)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    widget.setFixedHeight(TOOLBAR_BUTTON_SIZE)


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
    load_action.setStatusTip("Open a drawing or workbook")
    load_action.setShortcut(QKeySequence.StandardKey.Open)
    load_action.triggered.connect(lambda _checked=False: callbacks.load_canvas(window))
    window.addAction(load_action)

    export_figure_action = QAction("Export Figure...", window)
    export_figure_action.setToolTip("Export Figure")
    export_figure_action.setStatusTip("Export the drawing as SVG, PDF, or high-resolution PNG/TIFF")
    export_figure_action.triggered.connect(lambda _checked=False: callbacks.export_figure(window))
    window.addAction(export_figure_action)

    save_button = create_file_project_menu_button(
        save_action, load_action, save_as_action, export_figure_action
    )
    preview_panel_btn = create_toolbar_button(
        icon=icon_factory.icon_preview_panel(),
        tooltip="Open 3D Preview",
        status_tip="Open the selected molecule in a separate 3D preview window",
        callback=lambda _checked=False: callbacks.open_preview_window(window),
        object_name="preview_panel_button",
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

    smiles_input = QLineEdit()
    smiles_input.setObjectName("smilesInput")
    smiles_input.setPlaceholderText("SMILES...")
    smiles_input.setFixedWidth(180)
    smiles_input.setFixedHeight(TOOLBAR_BUTTON_SIZE)
    smiles_input.setToolTip("SMILES")
    smiles_input.setStatusTip("Type a SMILES string to insert")
    insert_controller = insert_controller_for_window(window)
    smiles_button = create_toolbar_button(
        text="Insert",
        tooltip="Insert SMILES",
        status_tip="Insert the typed SMILES structure",
        callback=lambda: insert_controller.begin_smiles_insert(smiles_input.text()),
        object_name="smiles_render_button",
        style_sheet=SMILES_RENDER_BUTTON_STYLE,
        auto_raise=False,
        cursor=Qt.CursorShape.PointingHandCursor,
    )
    smiles_input.returnPressed.connect(lambda: insert_controller.begin_smiles_insert(smiles_input.text()))

    panel_bar.addWidget(save_button)
    panel_bar.addWidget(undo_btn)
    panel_bar.addWidget(redo_btn)
    panel_bar.addSeparator()
    for action_key in TOOLBAR_TRANSFORM_TOOL_GROUP:
        action = tool_actions[action_key]
        panel_bar.addAction(action)
        _normalize_tool_action_button(panel_bar, action, action_key)
    panel_bar.addWidget(flip_h_btn)
    panel_bar.addWidget(flip_v_btn)
    panel_bar.addSeparator()
    for group_index, action_keys in enumerate(TOOLBAR_TOOL_GROUPS):
        if group_index:
            panel_bar.addSeparator()
        for action_key in action_keys:
            action = tool_actions[action_key]
            panel_bar.addAction(action)
            _normalize_tool_action_button(panel_bar, action, action_key)
    tool_actions["bond"].setChecked(True)
    panel_bar.addSeparator()
    panel_bar.addWidget(smiles_input)
    panel_bar.addWidget(smiles_button)
    panel_bar.addWidget(preview_panel_btn)
    panel_bar.addSeparator()

    for button in (
        save_button,
        preview_panel_btn,
        undo_btn,
        redo_btn,
        smiles_button,
        flip_h_btn,
        flip_v_btn,
    ):
        button.setIconSize(panel_bar.iconSize())
        button.setFixedHeight(TOOLBAR_BUTTON_SIZE)

    return MainWindowPanelToolbarAssembly(
        panel_bar=panel_bar,
        tool_actions=tool_actions,
        save_action=save_action,
        save_as_action=save_as_action,
        save_button=save_button,
        load_action=load_action,
        export_xyz_button=None,
        preview_panel_button=preview_panel_btn,
        undo_button=undo_btn,
        redo_button=redo_btn,
    )


__all__ = [
    "MainWindowPanelToolbarAssembly",
    "MainWindowPanelToolbarCallbacks",
    "build_panel_toolbar",
]
