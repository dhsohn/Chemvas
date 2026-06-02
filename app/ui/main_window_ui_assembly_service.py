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
    load_action: QAction | None = None
    export_xyz_button: QToolButton | None = None
    setup_sheet_button: QToolButton | None = None
    preview_panel_button: QToolButton | None = None
    undo_button: QToolButton | None = None
    redo_button: QToolButton | None = None


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
        painter.setBrush(QColor("#5a5a56"))
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
        painter.setBrush(QColor("#9b9b95"))
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
        status_tip: str | None = None,
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
        resolved_status_tip = status_tip if status_tip is not None else tooltip
        if resolved_status_tip is not None:
            button.setStatusTip(resolved_status_tip)
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
        status_tip: str | None = None,
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
        resolved_status_tip = status_tip if status_tip is not None else tooltip
        if resolved_status_tip is not None:
            button.setStatusTip(resolved_status_tip)
        button.setPopupMode(popup_mode)
        button.setStyleSheet(style_sheet)
        menu = QMenu(button)
        menu_builder(menu)
        button.setMenu(menu)
        return button

    def create_save_menu_button(self, save_action: QAction, save_as_action: QAction) -> CornerMenuButton:
        return self.create_corner_menu_button(
            tooltip=save_action.toolTip(),
            status_tip=save_action.statusTip() or save_action.toolTip(),
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=lambda menu: menu.addAction(save_as_action),
            default_action=save_action,
        )

    def create_file_project_menu_button(
        self,
        save_action: QAction,
        load_action: QAction,
        save_as_action: QAction,
    ) -> CornerMenuButton:
        def build_menu(menu: QMenu) -> None:
            menu.addAction(load_action)
            menu.addAction(save_action)
            menu.addAction(save_as_action)

        return self.create_corner_menu_button(
            tooltip="File",
            status_tip="Save, load, or save as the current file",
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=build_menu,
            default_action=save_action,
        )

    def create_toolbar_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("toolbarSectionLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

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
        left_groups = (
            ("select", "perspective"),
            ("bond", "bond_bold", "bond_wedge", "bond_hash", "bond_dotted"),
            ("text", "mark_plus", "mark_minus", "mark_radical"),
            ("benzene",),
        )
        for group_index, action_keys in enumerate(left_groups):
            if group_index:
                left_bar.addSeparator()
            for action_key in action_keys:
                if action_key in LEFT_TOOLBAR_ACTION_ORDER:
                    left_bar.addAction(tool_actions[action_key])
        left_bar.addSeparator()
        left_bar.addWidget(
            self.create_corner_menu_button(
                icon=window._icon_factory.icon_templates(),
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
        left_bar.addSeparator()
        left_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_factory.icon_flip_h(),
                tooltip="Flip Horizontal (Ctrl+Shift+H)",
                callback=lambda: window.canvas.flip_horizontal(),
            )
        )
        left_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_factory.icon_flip_v(),
                tooltip="Flip Vertical (Ctrl+Shift+V)",
                callback=lambda: window.canvas.flip_vertical(),
            )
        )

        window.addToolBar(Qt.ToolBarArea.LeftToolBarArea, left_bar)
        tool_actions["bond"].setChecked(True)

        panel_bar = QToolBar("Panels", window)
        panel_bar.setObjectName("topRoleToolbar")
        panel_bar.setMovable(False)
        panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        panel_bar.setIconSize(QSize(24, 24))
        panel_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        save_action = QAction("Save", window)
        save_action.setIcon(window._icon_factory.icon_save())
        save_action.setToolTip("Save")
        save_action.setStatusTip("Save the current drawing")
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(window._save_canvas)
        window.addAction(save_action)

        save_as_action = QAction("Save As...", window)
        save_as_action.setToolTip("Save As")
        save_as_action.setStatusTip("Save the current drawing to a new file")
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(window._save_canvas_as)
        window.addAction(save_as_action)

        load_action = QAction("Load", window)
        load_action.setIcon(window._icon_factory.icon_open())
        load_action.setToolTip("Load")
        load_action.setStatusTip("Open a drawing or workbook")
        load_action.setShortcut(QKeySequence.StandardKey.Open)
        load_action.triggered.connect(window._load_canvas)
        window.addAction(load_action)

        save_button = self.create_file_project_menu_button(save_action, load_action, save_as_action)
        export_xyz_btn = self.create_toolbar_button(
            icon=window._icon_factory.icon_export_xyz(),
            tooltip="Export 3D XYZ",
            status_tip="Export the current structure as 3D XYZ",
            callback=window._export_xyz,
            object_name="export_xyz_button",
        )
        preview_panel_btn = self.create_toolbar_button(
            icon=window._icon_factory.icon_preview_panel(),
            tooltip="3D Preview Panel",
            status_tip="Show or hide the right-side 3D preview panel",
            callback=window._toggle_preview_panel,
            object_name="preview_panel_button",
        )
        preview_panel_btn.setCheckable(True)
        preview_panel_btn.setChecked(True)
        setup_sheet_btn = self.create_toolbar_button(
            icon=window._icon_factory.icon_setup_sheet(),
            tooltip="Setup Sheet",
            status_tip="Set the current sheet size and orientation",
            callback=window._setup_sheet,
            object_name="setup_sheet_button",
        )
        undo_btn = self.create_toolbar_button(
            icon=window._icon_factory.icon_undo(),
            tooltip="Undo",
            status_tip="Undo the last edit",
            callback=lambda: window.canvas.undo(),
            shortcut=QKeySequence.StandardKey.Undo,
            object_name="undo_button",
        )
        redo_btn = self.create_toolbar_button(
            icon=window._icon_factory.icon_redo(),
            tooltip="Redo",
            status_tip="Redo the last undone edit",
            callback=lambda: window.canvas.redo(),
            shortcut=QKeySequence.StandardKey.Redo,
            object_name="redo_button",
        )

        smiles_input = QLineEdit()
        smiles_input.setObjectName("smilesInput")
        smiles_input.setPlaceholderText("SMILES...")
        smiles_input.setFixedWidth(180)
        smiles_input.setToolTip("SMILES")
        smiles_input.setStatusTip("Type a SMILES string to insert")
        smiles_button = self.create_toolbar_button(
            text="Insert",
            tooltip="Insert SMILES",
            status_tip="Insert the typed SMILES structure",
            callback=lambda: window.canvas.begin_smiles_insert(smiles_input.text()),
            object_name="smiles_render_button",
            style_sheet=SMILES_RENDER_BUTTON_STYLE,
            auto_raise=False,
            cursor=Qt.CursorShape.PointingHandCursor,
        )
        smiles_input.returnPressed.connect(lambda: window.canvas.begin_smiles_insert(smiles_input.text()))

        panel_bar.addWidget(self.create_toolbar_section_label("File"))
        panel_bar.addWidget(save_button)
        panel_bar.addWidget(export_xyz_btn)
        panel_bar.addWidget(preview_panel_btn)
        panel_bar.addWidget(setup_sheet_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(self.create_toolbar_section_label("History"))
        panel_bar.addWidget(undo_btn)
        panel_bar.addWidget(redo_btn)
        panel_bar.addSeparator()
        panel_bar.addWidget(self.create_toolbar_section_label("SMILES"))
        panel_bar.addWidget(smiles_input)
        panel_bar.addWidget(smiles_button)
        panel_bar.addSeparator()

        atom_input = QLineEdit()
        atom_input.setObjectName("atomInput")
        atom_input.setPlaceholderText("Atom")
        atom_input.setFixedWidth(60)
        atom_input.setMaxLength(4)
        atom_input.setText(window.canvas.get_atom_symbol())
        atom_input.setToolTip("Atom Symbol")
        atom_input.setStatusTip("Set the atom symbol used by atom and bond tools")
        atom_input.textChanged.connect(lambda text: window.canvas.set_atom_symbol(text))
        panel_bar.addWidget(self.create_toolbar_section_label("Style"))
        panel_bar.addWidget(atom_input)
        panel_bar.addWidget(
            self.create_corner_menu_button(
                icon=window._icon_factory.icon_color(),
                tooltip="Color",
                status_tip="Set the drawing color",
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=lambda menu: window._populate_palette_menu(menu, window._apply_color_preset),
            )
        )
        panel_bar.addWidget(
            self.create_corner_menu_button(
                icon=window._icon_factory.icon_ring_fill(),
                tooltip="Ring Fill",
                status_tip="Set the ring fill color",
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=lambda menu: window._populate_palette_menu(menu, window._apply_ring_fill_preset),
            )
        )
        panel_bar.addWidget(
            self.create_toolbar_button(
                icon=window._icon_factory.icon_bond_length(),
                tooltip="Bond Length",
                status_tip="Set the default bond length",
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
            load_action=load_action,
            export_xyz_button=export_xyz_btn,
            setup_sheet_button=setup_sheet_btn,
            preview_panel_button=preview_panel_btn,
            undo_button=undo_btn,
            redo_button=redo_btn,
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
