from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPolygonF
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSlider,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.main_window_config import ARROW_PRESET_SPECS, LEFT_TOOLBAR_ACTION_ORDER
from ui.main_window_theme import (
    MAIN_WINDOW_STYLESHEET,
    SMILES_RENDER_BUTTON_STYLE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_MENU_BUTTON_STYLE,
)


@dataclass(frozen=True)
class MainWindowToolbarAssembly:
    left_bar: QToolBar
    panel_bar: QToolBar
    tool_actions: dict[str, QAction]
    atom_input: QLineEdit
    save_action: QAction
    save_as_action: QAction
    save_button: QToolButton


@dataclass(frozen=True)
class MainWindowPanelAssembly:
    splitter: QSplitter
    dock: QDockWidget


class ArrowButton(QToolButton):
    def __init__(self, direction: str, parent=None) -> None:
        super().__init__(parent)
        self._direction = direction
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3d3229"))
        rect = self.rect().adjusted(6, 4, -6, -4)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        if self._direction == "up":
            points = [
                QPointF(rect.center().x(), rect.top()),
                QPointF(rect.right(), rect.bottom()),
                QPointF(rect.left(), rect.bottom()),
            ]
        else:
            points = [
                QPointF(rect.left(), rect.top()),
                QPointF(rect.right(), rect.top()),
                QPointF(rect.center().x(), rect.bottom()),
            ]
        painter.drawPolygon(QPolygonF(points))


class CornerMenuButton(QToolButton):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8b7d6e"))
        rect = self.rect()
        size = 6
        right = rect.right() - 2
        bottom = rect.bottom() - 2
        left = right - size
        top = bottom - size
        points = [
            QPointF(right, bottom),
            QPointF(left, bottom),
            QPointF(right, top),
        ]
        painter.drawPolygon(QPolygonF(points))


class MainWindowUIAssemblyService:
    def create_toolbar_button(
        self,
        *,
        icon: QIcon | None = None,
        tooltip: str | None = None,
        callback: Callable[[], None] | None = None,
        shortcut=None,
        text: str | None = None,
        object_name: str | None = None,
        style_sheet: str | None = None,
        auto_raise: bool = True,
        cursor=None,
    ) -> QToolButton:
        button = QToolButton()
        if icon is not None:
            button.setIcon(icon)
        if tooltip is not None:
            button.setToolTip(tooltip)
        if shortcut is not None:
            button.setShortcut(shortcut)
        if text is not None:
            button.setText(text)
        if object_name is not None:
            button.setObjectName(object_name)
        if style_sheet is not None:
            button.setStyleSheet(style_sheet)
        button.setAutoRaise(auto_raise)
        if cursor is not None:
            button.setCursor(cursor)
        if callback is not None:
            button.clicked.connect(callback)
        return button

    def create_corner_menu_button(
        self,
        *,
        icon: QIcon | None = None,
        tooltip: str | None = None,
        style_sheet: str,
        popup_mode: QToolButton.ToolButtonPopupMode,
        menu_builder: Callable[[QMenu], None],
        default_action: QAction | None = None,
    ) -> CornerMenuButton:
        button = CornerMenuButton()
        if default_action is not None:
            button.setDefaultAction(default_action)
        elif icon is not None:
            button.setIcon(icon)
        if tooltip is not None:
            button.setToolTip(tooltip)
        button.setPopupMode(popup_mode)
        button.setStyleSheet(style_sheet)
        menu = QMenu(button)
        menu_builder(menu)
        button.setMenu(menu)
        return button

    def create_save_menu_button(self, save_action: QAction, save_as_action: QAction) -> CornerMenuButton:
        return self.create_corner_menu_button(
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=lambda menu: menu.addAction(save_as_action),
            default_action=save_action,
        )

    def init_toolbars(self, window) -> MainWindowToolbarAssembly:
        tool_group = QActionGroup(window)
        tool_group.setExclusive(True)

        left_bar = QToolBar("Tools", window)
        left_bar.setOrientation(Qt.Orientation.Vertical)
        left_bar.setMovable(False)
        left_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        left_bar.setIconSize(QSize(26, 26))
        left_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        tool_actions = window._build_tool_actions(tool_group)
        for action_key in LEFT_TOOLBAR_ACTION_ORDER:
            left_bar.addAction(tool_actions[action_key])
        left_bar.addWidget(
            self.create_corner_menu_button(
                icon=window._icon_templates(),
                tooltip="Templates",
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=window._populate_template_menu,
            )
        )
        left_bar.addWidget(
            self.create_corner_menu_button(
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=window._populate_arrow_menu,
                default_action=tool_actions["arrow"],
            )
        )
        left_bar.addAction(tool_actions["ts_bracket"])
        left_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_bond_length(),
                tooltip="Bond Length",
                callback=window._set_bond_length,
            )
        )
        left_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_flip_h(),
                tooltip="Flip Horizontal (Ctrl+Shift+H)",
                callback=lambda: window.canvas.flip_horizontal(),
            )
        )
        left_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_flip_v(),
                tooltip="Flip Vertical (Ctrl+Shift+V)",
                callback=lambda: window.canvas.flip_vertical(),
            )
        )

        window.addToolBar(Qt.ToolBarArea.LeftToolBarArea, left_bar)
        tool_actions["bond"].setChecked(True)

        panel_bar = QToolBar("Panels", window)
        panel_bar.setMovable(False)
        panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        panel_bar.setIconSize(QSize(24, 24))
        panel_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        save_action = QAction("Save", window)
        save_action.setIcon(window._icon_save())
        save_action.setToolTip("Save")
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(window._save_canvas)
        window.addAction(save_action)

        save_as_action = QAction("Save As...", window)
        save_as_action.setToolTip("Save As")
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(window._save_canvas_as)
        window.addAction(save_as_action)

        save_button = self.create_save_menu_button(save_action, save_as_action)
        load_btn = self.create_toolbar_button(
            icon=window._icon_open(),
            tooltip="Load",
            callback=window._load_canvas,
            shortcut=QKeySequence.StandardKey.Open,
        )
        export_xyz_btn = self.create_toolbar_button(
            icon=window._icon_export_xyz(),
            tooltip="Export 3D XYZ",
            callback=window._export_xyz,
        )
        undo_btn = self.create_toolbar_button(
            icon=window._icon_undo(),
            tooltip="Undo",
            callback=lambda: window.canvas.undo(),
            shortcut=QKeySequence.StandardKey.Undo,
        )
        redo_btn = self.create_toolbar_button(
            icon=window._icon_redo(),
            tooltip="Redo",
            callback=lambda: window.canvas.redo(),
            shortcut=QKeySequence.StandardKey.Redo,
        )

        smiles_input = QLineEdit()
        smiles_input.setPlaceholderText("SMILES...")
        smiles_input.setFixedWidth(180)
        smiles_button = self.create_toolbar_button(
            text="Render",
            callback=lambda: window.canvas.begin_smiles_insert(smiles_input.text()),
            object_name="smiles_render_button",
            style_sheet=SMILES_RENDER_BUTTON_STYLE,
            auto_raise=False,
            cursor=Qt.CursorShape.PointingHandCursor,
        )
        smiles_input.returnPressed.connect(lambda: window.canvas.begin_smiles_insert(smiles_input.text()))

        panel_bar.addWidget(save_button)
        panel_bar.addWidget(load_btn)
        panel_bar.addWidget(export_xyz_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(undo_btn)
        panel_bar.addWidget(redo_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(smiles_input)
        panel_bar.addWidget(smiles_button)
        panel_bar.addSeparator()

        atom_input = QLineEdit()
        atom_input.setPlaceholderText("Atom")
        atom_input.setFixedWidth(60)
        atom_input.setMaxLength(4)
        atom_input.setText(window.canvas.get_atom_symbol())
        atom_input.textChanged.connect(lambda text: window.canvas.set_atom_symbol(text))
        panel_bar.addWidget(atom_input)
        panel_bar.addWidget(
            self.create_corner_menu_button(
                icon=window._icon_color(),
                tooltip="Color",
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=lambda menu: window._populate_palette_menu(menu, window._apply_color_preset),
            )
        )
        panel_bar.addWidget(
            self.create_corner_menu_button(
                icon=window._icon_ring_fill(),
                tooltip="Ring Fill",
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=lambda menu: window._populate_palette_menu(menu, window._apply_ring_fill_preset),
            )
        )
        panel_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_bond_length(),
                tooltip="Bond Length",
                callback=window._set_bond_length,
            )
        )
        panel_bar.addSeparator()

        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, panel_bar)
        return MainWindowToolbarAssembly(
            left_bar=left_bar,
            panel_bar=panel_bar,
            tool_actions=tool_actions,
            atom_input=atom_input,
            save_action=save_action,
            save_as_action=save_as_action,
            save_button=save_button,
        )

    def init_panels(self, window) -> MainWindowPanelAssembly:
        dock = QDockWidget("Panels", window)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setMinimumWidth(320)
        dock.setMaximumWidth(420)
        title_bar = QWidget(dock)
        title_bar.setFixedHeight(0)
        dock.setTitleBarWidget(title_bar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(window.preview_3d)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([1])

        dock.setWidget(splitter)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        return MainWindowPanelAssembly(splitter=splitter, dock=dock)

    def apply_theme(self, window) -> None:
        window.setStyleSheet(MAIN_WINDOW_STYLESHEET)

    def open_arrow_settings(self, window) -> None:
        dialog = QDialog(window)
        dialog.setWindowTitle("Arrow Settings")
        dialog.setStyleSheet(window.styleSheet())
        layout = QVBoxLayout(dialog)

        preset_label = QLabel("Preset")
        preset_combo = QComboBox()
        preset_combo.addItems(ARROW_PRESET_SPECS)
        preset_combo.currentTextChanged.connect(window._set_arrow_preset)

        width_label = QLabel("Width")
        width_slider = QSlider(Qt.Orientation.Horizontal)
        width_slider.setMinimum(1)
        width_slider.setMaximum(6)
        width_slider.setValue(int(window.canvas.get_arrow_line_width()))
        width_slider.valueChanged.connect(lambda value: window.canvas.set_arrow_line_width(value))

        head_label = QLabel("Head")
        head_slider = QSlider(Qt.Orientation.Horizontal)
        head_slider.setMinimum(10)
        head_slider.setMaximum(60)
        head_slider.setValue(int(window.canvas.get_arrow_head_scale() * 100))
        head_slider.valueChanged.connect(lambda value: window.canvas.set_arrow_head_scale(value / 100.0))

        snap_check = QCheckBox("Curve Snap")
        snap_check.setChecked(window.canvas.get_curved_snap())
        snap_check.toggled.connect(window.canvas.set_curved_snap)

        symmetry_check = QCheckBox("Curve Symmetry")
        symmetry_check.setChecked(window.canvas.get_curved_symmetry())
        symmetry_check.toggled.connect(window.canvas.set_curved_symmetry)

        snap_label = QLabel("Snap Step")
        snap_slider = QSlider(Qt.Orientation.Horizontal)
        snap_slider.setMinimum(5)
        snap_slider.setMaximum(40)
        snap_slider.setValue(int(window.canvas.get_curved_snap_step() * 100))
        snap_slider.valueChanged.connect(lambda value: window.canvas.set_curved_snap_step(value / 100.0))

        layout.addWidget(preset_label)
        layout.addWidget(preset_combo)
        layout.addWidget(width_label)
        layout.addWidget(width_slider)
        layout.addWidget(head_label)
        layout.addWidget(head_slider)
        layout.addWidget(snap_check)
        layout.addWidget(symmetry_check)
        layout.addWidget(snap_label)
        layout.addWidget(snap_slider)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        dialog.exec()


__all__ = [
    "ArrowButton",
    "CornerMenuButton",
    "MainWindowPanelAssembly",
    "MainWindowToolbarAssembly",
    "MainWindowUIAssemblyService",
]
