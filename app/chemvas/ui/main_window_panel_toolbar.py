from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import (
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from chemvas.ui.main_window_config import (
    TEXT_FONT_FAMILY_CHOICES,
    TOOLBAR_PRIMARY_TOOL_GROUP,
    TOOLBAR_TOOL_GROUPS,
)
from chemvas.ui.main_window_palette import PALETTE
from chemvas.ui.main_window_ports import icon_factory_for_window
from chemvas.ui.main_window_theme import (
    CONTEXT_BAR_BUTTON_HEIGHT,
    SMILES_RENDER_BUTTON_STYLE,
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
    TOOLBAR_THICKNESS,
)
from chemvas.ui.main_window_toolbar_buttons import CornerMenuToolButton

_NOTE_TOOL_MENU_BUTTON_STYLE = (
    TOOLBAR_BUTTON_STYLE
    + "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
)


class _ModeWellToolBar(QToolBar):
    """Top toolbar that paints a subtle inset "well" behind the modal tool
    buttons.

    The pick-one mode tools (select, bond, ring, arrow, ...) then read as one
    grouped set — visually distinct from the loose one-shot command buttons
    beside them (flip, rotate, undo, redo), which sit on the bare bar. The
    buttons and actions are untouched; this is decoration painted behind them,
    so an active tool's checked highlight still draws on top as usual.
    """

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._first_mode_widget: QWidget | None = None
        self._last_mode_widget: QWidget | None = None

    def set_mode_well(self, first_widget: QWidget, last_widget: QWidget) -> None:
        self._first_mode_widget = first_widget
        self._last_mode_widget = last_widget
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        first = self._first_mode_widget
        last = self._last_mode_widget
        if (
            first is None
            or last is None
            or not first.isVisible()
            or not last.isVisible()
        ):
            return
        region = first.geometry().united(last.geometry())
        # A small vertical inset lets the tray float clear of the toolbar's top
        # and bottom edges rather than sitting flush, which reads as breathing
        # room without needing a tall toolbar.
        well = QRectF(region).adjusted(-4.0, -1.0, 4.0, 1.0)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Fill stays lighter than the button hover tint so hovering a tool in
        # the well still darkens visibly; the defined border carries the
        # grouping. The active tool's teal check reads clearly on top.
        painter.setPen(QPen(QColor(PALETTE["border_strong"]), 1.0))
        painter.setBrush(QColor(PALETTE["surface_app"]))
        painter.drawRoundedRect(well, 8.0, 8.0)
        painter.end()


@dataclass(frozen=True)
class MainWindowPanelToolbarAssembly:
    panel_bar: QToolBar
    tool_actions: dict[str, QAction]


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


def _add_smiles_controls(
    panel_bar: QToolBar, window, insert_controller_for_window
) -> None:
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
        lambda _checked=False: insert_controller_for_window(window).begin_smiles_insert(
            smiles_input.text()
        )
    )
    smiles_input.returnPressed.connect(
        lambda: insert_controller_for_window(window).begin_smiles_insert(
            smiles_input.text()
        )
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
    create_toolbar_button: Callable[..., QToolButton],
    build_tool_actions: Callable[[object, QActionGroup], dict[str, QAction]],
    scene_transform_controller_for_window,
    insert_controller_for_window,
    callbacks: MainWindowPanelToolbarCallbacks,
) -> MainWindowPanelToolbarAssembly:
    panel_bar = _ModeWellToolBar("Panels", window)
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

    flip_h_btn = create_toolbar_button(
        icon=icon_factory.icon_flip_h(),
        tooltip="Flip Horizontal (Ctrl+Shift+H)",
        status_tip="Flip the current selection horizontally",
        callback=lambda: scene_transform_controller_for_window(
            window
        ).flip_selected_items(horizontal=True),
        object_name="flip_horizontal_button",
    )
    flip_v_btn = create_toolbar_button(
        icon=icon_factory.icon_flip_v(),
        tooltip="Flip Vertical (Ctrl+Shift+V)",
        status_tip="Flip the current selection vertically",
        callback=lambda: scene_transform_controller_for_window(
            window
        ).flip_selected_items(horizontal=False),
        object_name="flip_vertical_button",
    )
    rotate_btn = create_toolbar_button(
        icon=icon_factory.icon_rotate(),
        tooltip="Rotate",
        status_tip="Enter an angle to rotate the current selection",
        callback=lambda: callbacks.show_rotate_options(window),
        object_name="rotate_button",
    )

    mode_widgets: list[QWidget] = []

    def add_tool(action_key: str, *, primary: bool) -> None:
        action = tool_actions[action_key]
        if action_key == "note":
            note_button = _build_note_font_menu_button(
                panel_bar, window, action, callbacks
            )
            panel_bar.addWidget(note_button)
            mode_widgets.append(note_button)
            return
        panel_bar.addAction(action)
        _normalize_tool_action_button(panel_bar, action, action_key, primary=primary)
        tool_widget = panel_bar.widgetForAction(action)
        if tool_widget is not None:
            mode_widgets.append(tool_widget)

    for action_key in TOOLBAR_PRIMARY_TOOL_GROUP:
        add_tool(action_key, primary=True)
    panel_bar.addSeparator()
    for group_index, action_keys in enumerate(TOOLBAR_TOOL_GROUPS[1:]):
        for action_key in action_keys:
            add_tool(action_key, primary=False)
        if group_index < len(TOOLBAR_TOOL_GROUPS[1:]) - 1:
            panel_bar.addSeparator()
    # The modal tools now sit inside a painted "well" (see _ModeWellToolBar) so
    # they read as one pick-one set, distinct from the loose command buttons.
    if mode_widgets:
        panel_bar.set_mode_well(mode_widgets[0], mode_widgets[-1])
    panel_bar.addSeparator()
    panel_bar.addWidget(flip_h_btn)
    panel_bar.addWidget(flip_v_btn)
    panel_bar.addWidget(rotate_btn)
    panel_bar.addSeparator()
    _add_smiles_controls(panel_bar, window, insert_controller_for_window)
    panel_bar.addWidget(_toolbar_spacer())

    for button in (
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
    )


__all__ = [
    "MainWindowPanelToolbarAssembly",
    "MainWindowPanelToolbarCallbacks",
    "build_panel_toolbar",
]
