from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from ui.main_window_config import (
    TEXT_FONT_FAMILY_CHOICES,
    TOOLBAR_PRIMARY_TOOL_GROUP,
    TOOLBAR_TOOL_GROUPS,
)
from ui.main_window_ports import icon_factory_for_window
from ui.main_window_theme import (
    CONTEXT_BAR_BUTTON_HEIGHT,
    SMILES_RENDER_BUTTON_STYLE,
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
    TOOLBAR_THICKNESS,
)
from ui.main_window_toolbar_buttons import CornerMenuToolButton

_NOTE_TOOL_MENU_BUTTON_STYLE = (
    TOOLBAR_BUTTON_STYLE + "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
)


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
    show_rotate_options: Callable[[object], None]
    set_note_font_family: Callable[[object, str], None]


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


def _add_smiles_controls(panel_bar: QToolBar, window, insert_controller_for_window) -> None:
    smiles_input = QLineEdit()
    smiles_input.setObjectName("contextSmilesInput")
    smiles_input.setPlaceholderText("CC(=O)Oc1ccccc1C(=O)O")
    # The input stretches toward the file/history cluster so it never forces the
    # top toolbar to overflow (it shrinks to its minimum on narrow windows), but
    # it is capped so it does not sprawl across very wide monitors. A trailing
    # spacer takes up any slack past the cap, keeping the file buttons pinned
    # to the right edge.
    smiles_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    smiles_input.setMinimumWidth(120)
    smiles_input.setMaximumWidth(340)
    smiles_input.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
    smiles_input.setToolTip("SMILES")
    smiles_input.setStatusTip("Type a SMILES string to insert")
    render_button = QToolButton()
    render_button.setObjectName("smiles_render_button")
    render_button.setText("Insert")
    render_button.setToolTip("Insert SMILES")
    render_button.setStatusTip("Insert the typed SMILES structure")
    render_button.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
    render_button.setStyleSheet(SMILES_RENDER_BUTTON_STYLE)
    render_button.setCursor(Qt.CursorShape.PointingHandCursor)
    render_button.clicked.connect(
        lambda _checked=False: insert_controller_for_window(window).begin_smiles_insert(smiles_input.text())
    )
    smiles_input.returnPressed.connect(
        lambda: insert_controller_for_window(window).begin_smiles_insert(smiles_input.text())
    )
    panel_bar.addWidget(smiles_input)
    panel_bar.addWidget(render_button)


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
                lambda _checked=False, value=family: callbacks.set_note_font_family(window, value)
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
    flip_h_btn = create_toolbar_button(
        icon=icon_factory.icon_flip_h(),
        tooltip="Flip Horizontal (Ctrl+Shift+H)",
        status_tip="Flip the current selection horizontally",
        callback=lambda: scene_transform_controller_for_window(window).flip_selected_items(horizontal=True),
        object_name="flip_horizontal_button",
    )
    flip_v_btn = create_toolbar_button(
        icon=icon_factory.icon_flip_v(),
        tooltip="Flip Vertical (Ctrl+Shift+V)",
        status_tip="Flip the current selection vertically",
        callback=lambda: scene_transform_controller_for_window(window).flip_selected_items(horizontal=False),
        object_name="flip_vertical_button",
    )
    rotate_btn = create_toolbar_button(
        icon=icon_factory.icon_rotate(),
        tooltip="Rotate",
        status_tip="Enter an angle to rotate the current selection",
        callback=lambda: callbacks.show_rotate_options(window),
        object_name="rotate_button",
    )

    def add_tool(action_key: str, *, primary: bool) -> None:
        action = tool_actions[action_key]
        if action_key == "note":
            panel_bar.addWidget(_build_note_font_menu_button(panel_bar, window, action, callbacks))
            return
        panel_bar.addAction(action)
        _normalize_tool_action_button(panel_bar, action, action_key, primary=primary)

    for action_key in TOOLBAR_PRIMARY_TOOL_GROUP:
        add_tool(action_key, primary=True)
    panel_bar.addSeparator()
    for group_index, action_keys in enumerate(TOOLBAR_TOOL_GROUPS[1:]):
        for action_key in action_keys:
            add_tool(action_key, primary=False)
        if group_index < len(TOOLBAR_TOOL_GROUPS[1:]) - 1:
            panel_bar.addSeparator()
    panel_bar.addSeparator()
    panel_bar.addWidget(flip_h_btn)
    panel_bar.addWidget(flip_v_btn)
    panel_bar.addWidget(rotate_btn)
    panel_bar.addSeparator()
    _add_smiles_controls(panel_bar, window, insert_controller_for_window)
    panel_bar.addWidget(_toolbar_spacer())
    panel_bar.addSeparator()
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
        rotate_btn,
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
