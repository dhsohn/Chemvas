import math
from pathlib import Path
from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
    QSlider,
    QTabBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDoubleSpinBox,
)

from core.document_io import read_document, write_document
from core.model import Atom
from ui.canvas_view import CanvasView
from ui.main_window_config import (
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    BOND_TOOL_ACTION_SPECS,
    COLOR_PALETTE_SPECS,
    LEFT_TOOLBAR_ACTION_ORDER,
    MARK_TOOL_ACTION_SPECS,
    TEMPLATE_ENTRY_SPECS,
    TOOL_ACTION_SPECS,
)
from ui.main_window_path_logic import resolve_load_path, resolve_save_as_path, resolve_save_path
from ui.main_window_theme import (
    MAIN_WINDOW_STYLESHEET,
    SMILES_RENDER_BUTTON_STYLE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_MENU_BUTTON_STYLE,
)
from ui.preview_3d import Preview3D


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


class SheetTabBar(QTabBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self._add_tab_index = -1

    def set_add_tab_index(self, index: int) -> None:
        self._add_tab_index = index
        self.updateGeometry()
        self.update()

    def tabSizeHint(self, index: int) -> QSize:
        hint = super().tabSizeHint(index)
        if index == self._add_tab_index:
            return QSize(28, hint.height())
        return hint


class MainWindow(QMainWindow):
    WORKBOOK_FILE_VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LightDraw")
        self.resize(1100, 760)

        self._atom_input = None
        self._canvas_name_counter = 0
        self._result_sheet_counter = 0
        self._last_canvas_tab_index = 0
        self._suspend_canvas_tab_reactions = False
        self._repositioning_add_tab = False
        self._sheet_add_tab = QWidget()
        self.canvas_tabs = QTabWidget()
        self.canvas_tabs.setObjectName("canvasTabs")
        self._sheet_tab_bar = SheetTabBar(self.canvas_tabs)
        self.canvas_tabs.setTabBar(self._sheet_tab_bar)
        self.canvas_tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.canvas_tabs.setDocumentMode(False)
        self.canvas_tabs.setMovable(True)
        self.canvas_tabs.setTabsClosable(False)
        self._sheet_tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sheet_tab_bar.customContextMenuRequested.connect(self._show_canvas_tab_context_menu)
        self._sheet_tab_bar.tabMoved.connect(self._on_canvas_tab_moved)
        self.canvas_tabs.currentChanged.connect(self._on_canvas_tab_changed)
        self.setCentralWidget(self.canvas_tabs)
        self.panel_splitter = None
        self.panel_dock = None
        self.preview_3d = Preview3D()
        self._current_file_path = None

        self._add_canvas_sheet(name=self._next_canvas_sheet_name(), select=True)
        self._ensure_add_sheet_tab()
        self._init_toolbars()
        self._init_panels()
        self._apply_theme()
        self._bind_active_canvas()
        self.preview_3d.refresh_from_canvas(self.canvas)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(50)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addPermanentWidget(self._zoom_label)
        self._update_zoom_label(self._current_zoom_percent())
        self.statusBar().showMessage("Ready")

    @property
    def canvas(self) -> CanvasView:
        canvas = self._active_canvas_or_none()
        if canvas is not None:
            return canvas
        raise RuntimeError("No active canvas sheet.")

    def _active_canvas_or_none(self) -> CanvasView | None:
        widget = self.canvas_tabs.currentWidget()
        if isinstance(widget, CanvasView):
            return widget
        if 0 <= self._last_canvas_tab_index < self.canvas_tabs.count():
            fallback = self.canvas_tabs.widget(self._last_canvas_tab_index)
            if isinstance(fallback, CanvasView):
                return fallback
        canvases = self._all_canvases()
        if canvases:
            return canvases[0]
        return None

    def _canvas_tab_entries(self) -> list[tuple[int, CanvasView]]:
        entries: list[tuple[int, CanvasView]] = []
        for index in range(self.canvas_tabs.count()):
            widget = self.canvas_tabs.widget(index)
            if isinstance(widget, CanvasView):
                entries.append((index, widget))
        return entries

    def _all_canvases(self) -> list[CanvasView]:
        return [canvas for _, canvas in self._canvas_tab_entries()]

    def _active_canvas_tab_index(self) -> int:
        active_canvas = self._active_canvas_or_none()
        if active_canvas is None:
            return -1
        return self.canvas_tabs.indexOf(active_canvas)

    def _active_canvas_sheet_index(self) -> int:
        active_canvas = self._active_canvas_or_none()
        if active_canvas is None:
            return 0
        for sheet_index, (_, canvas) in enumerate(self._canvas_tab_entries()):
            if canvas is active_canvas:
                return sheet_index
        return 0

    def _next_canvas_sheet_name(self, prefix: str = "Sheet") -> str:
        self._canvas_name_counter += 1
        return f"{prefix} {self._canvas_name_counter}"

    def _next_result_canvas_name(self, prefix: str) -> str:
        self._result_sheet_counter += 1
        return f"{prefix} {self._result_sheet_counter}"

    def _plus_tab_index(self) -> int:
        return self.canvas_tabs.indexOf(self._sheet_add_tab)

    def _canvas_sheet_count(self) -> int:
        return len(self._all_canvases())

    def _active_canvas_sheet_name(self) -> str:
        index = self._active_canvas_tab_index()
        if index < 0:
            return ""
        return self.canvas_tabs.tabText(index)

    def _ensure_add_sheet_tab(self) -> None:
        plus_index = self._plus_tab_index()
        if plus_index < 0:
            self._sheet_add_tab = QWidget()
            plus_index = self.canvas_tabs.addTab(self._sheet_add_tab, "+")
        self._keep_add_tab_last()
        plus_index = self._plus_tab_index()
        self.canvas_tabs.setTabToolTip(plus_index, "New Canvas Sheet")
        self._sheet_tab_bar.set_add_tab_index(plus_index)

    def _keep_add_tab_last(self) -> None:
        if self._repositioning_add_tab:
            return
        plus_index = self._plus_tab_index()
        last_index = self.canvas_tabs.count() - 1
        if plus_index < 0 or plus_index == last_index:
            return
        self._repositioning_add_tab = True
        try:
            self._sheet_tab_bar.moveTab(plus_index, last_index)
        finally:
            self._repositioning_add_tab = False
        self._sheet_tab_bar.set_add_tab_index(self._plus_tab_index())

    def _on_canvas_tab_moved(self, from_index: int, to_index: int) -> None:
        if self._repositioning_add_tab:
            return
        self._keep_add_tab_last()

    def _can_delete_canvas_sheet(self, index: int) -> bool:
        if index < 0:
            return False
        return isinstance(self.canvas_tabs.widget(index), CanvasView) and self._canvas_sheet_count() > 1

    def _show_canvas_tab_context_menu(self, pos) -> None:
        index = self._sheet_tab_bar.tabAt(pos)
        if index < 0:
            return
        widget = self.canvas_tabs.widget(index)
        if not isinstance(widget, CanvasView):
            return

        menu = QMenu(self)
        delete_action = menu.addAction("Delete Sheet")
        delete_action.setEnabled(self._can_delete_canvas_sheet(index))
        chosen_action = menu.exec(self._sheet_tab_bar.mapToGlobal(pos))
        if chosen_action is delete_action and delete_action.isEnabled():
            self._delete_canvas_sheet(index)

    def _delete_canvas_sheet(self, index: int) -> None:
        if not self._can_delete_canvas_sheet(index):
            return

        widget = self.canvas_tabs.widget(index)
        previous_state = self._suspend_canvas_tab_reactions
        self._suspend_canvas_tab_reactions = True
        self.canvas_tabs.removeTab(index)
        self._ensure_add_sheet_tab()

        active_index = self.canvas_tabs.currentIndex()
        if not isinstance(self.canvas_tabs.currentWidget(), CanvasView):
            active_index = min(index, max(0, self._plus_tab_index() - 1))
            self.canvas_tabs.setCurrentIndex(active_index)
        self._last_canvas_tab_index = active_index
        self._suspend_canvas_tab_reactions = previous_state

        if widget is not None:
            widget.deleteLater()
        self._refresh_active_canvas_ui()

    def _create_canvas(self, *, template: CanvasView | None = None) -> CanvasView:
        canvas = CanvasView()
        canvas.setFrameStyle(0)
        if template is not None:
            canvas.renderer.set_bond_length(template.renderer.style.bond_length_px)
            canvas.arrow_line_width = template.arrow_line_width
            canvas.arrow_head_scale = template.arrow_head_scale
            canvas.orbital_phase_enabled = template.orbital_phase_enabled
            canvas.text_font_size = template.text_font_size
            canvas.text_font_weight = template.text_font_weight
            canvas.text_italic = template.text_italic
            canvas.mark_kind = template.mark_kind
        return canvas

    def _add_canvas_sheet(
        self,
        *,
        name: str,
        state: dict | None = None,
        select: bool = True,
        template: CanvasView | None = None,
    ) -> CanvasView:
        canvas = self._create_canvas(template=template)
        plus_index = self._plus_tab_index()
        if plus_index >= 0:
            index = self.canvas_tabs.insertTab(plus_index, canvas, name)
        else:
            index = self.canvas_tabs.addTab(canvas, name)
        if state is not None:
            canvas.restore_state(state)
        self._ensure_add_sheet_tab()
        if select:
            self.canvas_tabs.setCurrentIndex(index)
        self._bind_active_canvas()
        return canvas

    def _open_result_canvas_sheet(
        self,
        name: str,
        *,
        select: bool = True,
        exact_name: bool = False,
    ) -> tuple[str | None, CanvasView | None]:
        if exact_name and name:
            sheet_name = name
        else:
            sheet_name = self._next_canvas_sheet_name(prefix=name or "Result")
        canvas = self._add_canvas_sheet(
            name=sheet_name,
            select=select,
            template=self._active_canvas_or_none(),
        )
        return sheet_name, canvas

    def _bind_active_canvas(self) -> None:
        active_canvas = self.canvas
        self.preview_3d._rdkit = active_canvas.rdkit
        for canvas in self._all_canvases():
            if canvas is active_canvas:
                canvas.set_selection_info_callback(self._handle_selection_info)
                canvas.set_tool_change_callback(self._sync_tool_actions_from_canvas)
                canvas.set_zoom_callback(self._update_zoom_label)
            else:
                canvas.set_selection_info_callback(None)
                canvas.set_tool_change_callback(None)
                canvas.set_zoom_callback(None)

    def _handle_selection_info(self, _formula: str, _mw: str) -> None:
        self.preview_3d.refresh_from_canvas(self.canvas)

    def _current_zoom_percent(self) -> int:
        transform = self.canvas.transform()
        return max(1, int(round(transform.m11() * 100)))

    def _refresh_active_canvas_ui(self) -> None:
        self._bind_active_canvas()
        if self._atom_input is not None:
            self._atom_input.blockSignals(True)
            self._atom_input.setText(self.canvas.get_atom_symbol())
            self._atom_input.blockSignals(False)
        if hasattr(self, "_zoom_label"):
            self._update_zoom_label(self._current_zoom_percent())
        self._sync_tool_actions_from_canvas()
        self.preview_3d.refresh_from_canvas(self.canvas)

    def _on_canvas_tab_changed(self, index: int) -> None:
        if self._suspend_canvas_tab_reactions:
            return
        if index < 0:
            return
        widget = self.canvas_tabs.widget(index)
        if widget is self._sheet_add_tab:
            self._new_canvas_sheet()
            return
        if not isinstance(widget, CanvasView):
            return
        self._last_canvas_tab_index = index
        self._refresh_active_canvas_ui()

    def _new_canvas_sheet(self) -> None:
        self._add_canvas_sheet(
            name=self._next_canvas_sheet_name(),
            select=True,
            template=self._active_canvas_or_none(),
        )

    def _clear_canvas_sheets(self) -> None:
        previous_state = self._suspend_canvas_tab_reactions
        self._suspend_canvas_tab_reactions = True
        while self.canvas_tabs.count():
            widget = self.canvas_tabs.widget(0)
            self.canvas_tabs.removeTab(0)
            if widget is not None and widget is not self._sheet_add_tab:
                widget.deleteLater()
        self._sheet_add_tab = QWidget()
        self._sheet_tab_bar.set_add_tab_index(-1)
        self._suspend_canvas_tab_reactions = previous_state

    def _workbook_state(self) -> dict:
        sheets = []
        for sheet_index, (tab_index, canvas) in enumerate(self._canvas_tab_entries()):
            sheets.append(
                {
                    "name": self.canvas_tabs.tabText(tab_index) or f"Sheet {sheet_index + 1}",
                    "kind": "canvas",
                    "content": canvas.snapshot_state(),
                }
            )
        return {
            "active_sheet_index": self._active_canvas_sheet_index(),
            "sheets": sheets,
        }

    def _restore_single_sheet_document(self, state: dict) -> None:
        self._suspend_canvas_tab_reactions = True
        self._clear_canvas_sheets()
        self._add_canvas_sheet(name="Sheet 1", state=state, select=True)
        self._last_canvas_tab_index = self._active_canvas_tab_index()
        self._suspend_canvas_tab_reactions = False
        self._refresh_active_canvas_ui()

    def _restore_workbook_document(self, state: dict) -> None:
        self._suspend_canvas_tab_reactions = True
        self._clear_canvas_sheets()
        for sheet_state in state.get("sheets", []):
            if not isinstance(sheet_state, dict):
                continue
            if sheet_state.get("kind", "canvas") != "canvas":
                continue
            self._add_canvas_sheet(
                name=str(sheet_state.get("name", self._next_canvas_sheet_name())),
                state=sheet_state.get("content", {}),
                select=False,
            )
        if self._canvas_sheet_count() == 0:
            self._add_canvas_sheet(name="Sheet 1", select=True)
        canvas_entries = self._canvas_tab_entries()
        active_sheet_index = int(state.get("active_sheet_index", 0))
        active_sheet_index = max(0, min(active_sheet_index, len(canvas_entries) - 1))
        active_tab_index = canvas_entries[active_sheet_index][0]
        self.canvas_tabs.setCurrentIndex(active_tab_index)
        self._last_canvas_tab_index = active_tab_index
        self._suspend_canvas_tab_reactions = False
        self._refresh_active_canvas_ui()

    def _save_document_state(self, path: str) -> None:
        if self._canvas_sheet_count() == 1:
            self.canvas.save_to_file(path)
            return
        write_document(path, self._workbook_state(), self.WORKBOOK_FILE_VERSION)

    def _build_checkable_tool_action(
        self,
        tool_group: QActionGroup,
        *,
        key: str,
        label: str,
        icon_method: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> tuple[str, QAction]:
        action = QAction(label, self)
        action.setCheckable(True)
        action.setIcon(getattr(self, icon_method)())
        action.setToolTip(tooltip)
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        tool_group.addAction(action)
        return key, action

    def _activate_bond_style_tool(self, value: str) -> None:
        self._set_tool_with_status("bond", reset_bond_style=False)
        self._set_bond_style(value)

    def _activate_mark_tool(self, kind: str) -> None:
        self.canvas.set_mark_kind(kind)
        self.statusBar().showMessage("Mark Tool")

    def _build_tool_actions(self, tool_group: QActionGroup) -> dict[str, QAction]:
        actions = dict(
            self._build_checkable_tool_action(
                tool_group,
                key=key,
                label=label,
                icon_method=icon_method,
                tooltip=tooltip,
                callback=lambda tool=tool: self._set_tool_with_status(tool),
            )
            for key, label, tool, icon_method, tooltip in TOOL_ACTION_SPECS
        )
        actions.update(
            dict(
                self._build_checkable_tool_action(
                    tool_group,
                    key=key,
                    label=label,
                    icon_method=icon_method,
                    tooltip=tooltip,
                    callback=lambda value=value: self._activate_bond_style_tool(value),
                )
                for key, label, value, icon_method, tooltip in BOND_TOOL_ACTION_SPECS
            )
        )
        actions.update(
            dict(
                self._build_checkable_tool_action(
                    tool_group,
                    key=key,
                    label=label,
                    icon_method=icon_method,
                    tooltip=tooltip,
                    callback=lambda kind=kind: self._activate_mark_tool(kind),
                )
                for key, label, kind, icon_method, tooltip in MARK_TOOL_ACTION_SPECS
            )
        )
        return actions

    def _create_toolbar_button(
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

    def _create_corner_menu_button(
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

    def _create_save_menu_button(self, save_action: QAction, save_as_action: QAction) -> CornerMenuButton:
        return self._create_corner_menu_button(
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=lambda menu: menu.addAction(save_as_action),
            default_action=save_action,
        )

    def _init_toolbars(self) -> None:
        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        left_bar = QToolBar("Tools", self)
        left_bar.setOrientation(Qt.Orientation.Vertical)
        left_bar.setMovable(False)
        left_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        left_bar.setIconSize(QSize(26, 26))
        left_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        self._tool_actions = self._build_tool_actions(tool_group)
        for action_key in LEFT_TOOLBAR_ACTION_ORDER:
            left_bar.addAction(self._tool_actions[action_key])
        left_bar.addWidget(
            self._create_corner_menu_button(
                icon=self._icon_templates(),
                tooltip="Templates",
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=self._populate_template_menu,
            )
        )
        left_bar.addWidget(
            self._create_corner_menu_button(
                style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=self._populate_arrow_menu,
                default_action=self._tool_actions["arrow"],
            )
        )
        left_bar.addAction(self._tool_actions["ts_bracket"])
        left_bar.addWidget(
            self._create_toolbar_button(
                icon=self._icon_bond_length(),
                tooltip="Bond Length",
                callback=self._set_bond_length,
            )
        )
        left_bar.addWidget(
            self._create_toolbar_button(
                icon=self._icon_flip_h(),
                tooltip="Flip Horizontal (Ctrl+Shift+H)",
                callback=lambda: self.canvas.flip_horizontal(),
            )
        )
        left_bar.addWidget(
            self._create_toolbar_button(
                icon=self._icon_flip_v(),
                tooltip="Flip Vertical (Ctrl+Shift+V)",
                callback=lambda: self.canvas.flip_vertical(),
            )
        )

        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, left_bar)
        self._tool_actions["bond"].setChecked(True)

        panel_bar = QToolBar("Panels", self)
        panel_bar.setMovable(False)
        panel_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        panel_bar.setIconSize(QSize(24, 24))
        panel_bar.setStyleSheet(TOOLBAR_BUTTON_STYLE)

        save_action = QAction("Save", self)
        save_action.setIcon(self._icon_save())
        save_action.setToolTip("Save")
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_canvas)
        self.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setToolTip("Save As")
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._save_canvas_as)
        self.addAction(save_as_action)

        save_btn = self._create_save_menu_button(save_action, save_as_action)
        load_btn = self._create_toolbar_button(
            icon=self._icon_open(),
            tooltip="Load",
            callback=self._load_canvas,
            shortcut=QKeySequence.StandardKey.Open,
        )
        export_xyz_btn = self._create_toolbar_button(
            icon=self._icon_export_xyz(),
            tooltip="Export 3D XYZ",
            callback=self._export_xyz,
        )
        undo_btn = self._create_toolbar_button(
            icon=self._icon_undo(),
            tooltip="Undo",
            callback=lambda: self.canvas.undo(),
            shortcut=QKeySequence.StandardKey.Undo,
        )
        redo_btn = self._create_toolbar_button(
            icon=self._icon_redo(),
            tooltip="Redo",
            callback=lambda: self.canvas.redo(),
            shortcut=QKeySequence.StandardKey.Redo,
        )

        smiles_input = QLineEdit()
        smiles_input.setPlaceholderText("SMILES...")
        smiles_input.setFixedWidth(180)
        smiles_button = self._create_toolbar_button(
            text="Render",
            callback=lambda: self.canvas.begin_smiles_insert(smiles_input.text()),
            object_name="smiles_render_button",
            style_sheet=SMILES_RENDER_BUTTON_STYLE,
            auto_raise=False,
            cursor=Qt.CursorShape.PointingHandCursor,
        )
        smiles_input.returnPressed.connect(lambda: self.canvas.begin_smiles_insert(smiles_input.text()))

        panel_bar.addWidget(save_btn)
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
        atom_input.setText(self.canvas.get_atom_symbol())
        atom_input.textChanged.connect(lambda text: self.canvas.set_atom_symbol(text))
        panel_bar.addWidget(atom_input)
        color_button = self._create_corner_menu_button(
            icon=self._icon_color(),
            tooltip="Color",
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
            menu_builder=lambda menu: self._populate_palette_menu(menu, self._apply_color_preset),
        )
        panel_bar.addWidget(color_button)

        ring_fill_button = self._create_corner_menu_button(
            icon=self._icon_ring_fill(),
            tooltip="Ring Fill",
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
            menu_builder=lambda menu: self._populate_palette_menu(menu, self._apply_ring_fill_preset),
        )
        panel_bar.addWidget(ring_fill_button)
        panel_bar.addWidget(
            self._create_toolbar_button(
                icon=self._icon_bond_length(),
                tooltip="Bond Length",
                callback=self._set_bond_length,
            )
        )
        panel_bar.addSeparator()

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, panel_bar)
        self._atom_input = atom_input

    def _make_icon(self, painter_fn, size: int = 30) -> QIcon:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_fn(painter)
        painter.end()
        return QIcon(pixmap)

    def _icon_select(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#8b7355"))
            pen.setWidthF(2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(5, 6, 20, 18)
        return self._make_icon(draw)

    def _icon_bond(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(7, 23, 23, 7)
        return self._make_icon(draw)

    def _icon_bond_bold(self) -> QIcon:
        def draw(p):
            start = QPointF(6, 23)
            end = QPointF(24, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            start = QPointF(start.x() + dx * 0.025, start.y() + dy * 0.025)
            end = QPointF(end.x() - dx * 0.025, end.y() - dy * 0.025)
            p.setPen(self.canvas.renderer.bold_bond_pen())
            p.drawLine(start, end)
        return self._make_icon(draw)

    def _icon_mark_plus(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(15, 7, 15, 23)
            p.drawLine(7, 15, 23, 15)
        return self._make_icon(draw)

    def _icon_mark_minus(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(7, 15, 23, 15)
        return self._make_icon(draw)

    def _icon_mark_radical(self) -> QIcon:
        def draw(p):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3d3229"))
            p.drawEllipse(12, 12, 6, 6)
        return self._make_icon(draw)

    def _icon_text(self) -> QIcon:
        def draw(p):
            font = QFont("Arial")
            font.setBold(True)
            font.setPointSize(22)
            p.setFont(font)
            p.setPen(QPen(QColor("#3d3229")))
            p.drawText(7, 21, "A")
        return self._make_icon(draw)

    def _benzene_icon_polygon(self, center: QPointF, radius: float) -> QPolygonF:
        polygon = QPolygonF()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            polygon.append(
                QPointF(
                    center.x() + radius * math.cos(angle),
                    center.y() + radius * math.sin(angle),
                )
            )
        return polygon

    def _benzene_icon_inner_segments(
        self,
        polygon: QPolygonF,
        center: QPointF,
        *,
        spacing_scale: float = 1.0,
    ) -> list[tuple[QPointF, QPointF]]:
        if polygon.count() < 2:
            return []
        first = polygon[0]
        second = polygon[1]
        icon_bond_length = math.hypot(second.x() - first.x(), second.y() - first.y())
        if icon_bond_length <= 1e-6:
            return []
        canvas_bond_length = max(1.0, float(self.canvas.renderer.style.bond_length_px))
        scale = canvas_bond_length / icon_bond_length
        scaled_center = QPointF(center.x() * scale, center.y() * scale)
        segments: list[tuple[QPointF, QPointF]] = []
        for index in range(0, polygon.count(), 2):
            start = polygon[index]
            end = polygon[(index + 1) % polygon.count()]
            _, inner_seg, _ = self.canvas._ring_double_segments(
                Atom("C", start.x() * scale, start.y() * scale),
                Atom("C", end.x() * scale, end.y() * scale),
                scaled_center,
            )
            start_point = QPointF(inner_seg[0] / scale, inner_seg[1] / scale)
            end_point = QPointF(inner_seg[2] / scale, inner_seg[3] / scale)
            if abs(spacing_scale - 1.0) > 1e-6:
                midpoint = QPointF(
                    (start_point.x() + end_point.x()) / 2.0,
                    (start_point.y() + end_point.y()) / 2.0,
                )
                center_dx = midpoint.x() - center.x()
                center_dy = midpoint.y() - center.y()
                adjusted_midpoint = QPointF(
                    center.x() + center_dx * spacing_scale,
                    center.y() + center_dy * spacing_scale,
                )
                start_point = QPointF(
                    adjusted_midpoint.x() + (start_point.x() - midpoint.x()),
                    adjusted_midpoint.y() + (start_point.y() - midpoint.y()),
                )
                end_point = QPointF(
                    adjusted_midpoint.x() + (end_point.x() - midpoint.x()),
                    adjusted_midpoint.y() + (end_point.y() - midpoint.y()),
                )
            segments.append(
                (
                    start_point,
                    end_point,
                )
            )
        return segments

    def _icon_ring(self) -> QIcon:
        icon_size = 26
        center = QPointF(icon_size / 2.0, icon_size / 2.0)
        radius = 11.2

        def draw(p):
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.8)
            p.setPen(pen)
            outer = self._benzene_icon_polygon(center, radius)
            p.drawPolygon(outer)
            inner_pen = QPen(QColor("#3d3229"))
            inner_pen.setWidthF(1.8)
            p.setPen(inner_pen)
            for start, end in self._benzene_icon_inner_segments(outer, center, spacing_scale=0.92):
                p.drawLine(start, end)
        return self._make_icon(draw, size=icon_size)

    def _icon_ring_fill(self) -> QIcon:
        def draw(p):
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.8)
            center = QPointF(15.0, 15.0)
            radius = 10.0
            outer = QPolygonF()
            for i in range(5):
                angle = math.radians(360 / 5 * i - 90)
                outer.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.setPen(pen)
            p.setBrush(QBrush(QColor("#f3ead7")))
            p.drawPolygon(outer)
        return self._make_icon(draw)

    def _icon_undo(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawArc(5, 8, 18, 18, 90 * 16, 270 * 16)
            p.drawLine(8, 10, 5, 15)
            p.drawLine(8, 10, 11, 10)
        return self._make_icon(draw)

    def _icon_redo(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawArc(8, 8, 18, 18, 180 * 16, 270 * 16)
            p.drawLine(23, 10, 25, 15)
            p.drawLine(23, 10, 19, 10)
        return self._make_icon(draw)

    def _icon_save(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 5, 18, 20)
            p.drawLine(6, 11, 24, 11)
            p.drawRect(10, 15, 10, 8)
        return self._make_icon(draw)

    def _icon_open(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 13, 18, 10)
            p.drawLine(15, 6, 15, 16)
            p.drawLine(11, 10, 15, 6)
            p.drawLine(19, 10, 15, 6)
        return self._make_icon(draw)

    def _icon_export_xyz(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.3)
            p.setPen(pen)
            p.drawRect(7, 8, 10, 12)
            p.drawLine(17, 8, 23, 12)
            p.drawLine(17, 20, 23, 24)
            p.drawLine(23, 12, 23, 24)
            p.drawLine(7, 8, 13, 12)
            p.drawLine(13, 12, 23, 12)
            p.drawLine(7, 20, 13, 24)
            p.drawLine(13, 24, 23, 24)
        return self._make_icon(draw)

    def _icon_add_sheet(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawRect(6, 7, 18, 16)
            p.drawLine(15, 10, 15, 20)
            p.drawLine(10, 15, 20, 15)
            p.drawLine(9, 25, 21, 25)
        return self._make_icon(draw)

    def _icon_templates(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            chair = self._chair_icon_points(self._chair_icon_rect())
            if not chair.isEmpty():
                p.drawPolygon(chair)
        return self._make_icon(draw)

    def _icon_info(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawEllipse(7, 7, 16, 16)
            p.drawLine(15, 13, 15, 19)
            p.drawPoint(15, 10)
        return self._make_icon(draw)

    def _icon_bond_double(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.drawLine(5, 11, 25, 11)
            p.drawLine(5, 19, 25, 19)
        return self._make_icon(draw)

    def _icon_bond_triple(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 10, 25, 10)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(5, 20, 25, 20)
        return self._make_icon(draw)

    def _icon_bond_wedge(self) -> QIcon:
        def draw(p):
            start = QPointF(7, 23)
            end = QPointF(23, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            start = QPointF(start.x() + dx * 0.1, start.y() + dy * 0.1)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = math.hypot(dx, dy) or 1.0
            nx = -dy / length
            ny = dx / length
            half_width = self.canvas.renderer.bold_bond_pen().widthF() * 0.5 * 0.95
            p1 = start
            p2 = QPointF(end.x() + nx * half_width, end.y() + ny * half_width)
            p3 = QPointF(end.x() - nx * half_width, end.y() - ny * half_width)
            polygon = QPolygonF([p1, p2, p3])
            p.setPen(self.canvas.renderer.bond_pen())
            p.setBrush(QBrush(QColor(self.canvas.renderer.style.bond_color)))
            p.drawPolygon(polygon)
        return self._make_icon(draw)

    def _icon_bond_hash(self) -> QIcon:
        def draw(p):
            start = QPointF(7, 23)
            end = QPointF(23, 7)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = math.hypot(dx, dy) or 1.0
            nx = -dy / length
            ny = dx / length
            count = max(3, int(length / self.canvas.renderer.style.hash_spacing_px))
            max_size = self.canvas.renderer.bold_bond_pen().widthF()
            if count <= 1:
                t_positions = [0.5]
                t_sizes = [1.0]
            else:
                t_positions = [i / (count - 1) for i in range(count)]
                t_sizes = [(i + 1) / (count + 1) for i in range(count)]
            max_t = max(t_sizes) if t_sizes else 1.0
            p.setPen(self.canvas.renderer.bond_pen())
            for t_pos, t_size in zip(t_positions, t_sizes):
                cx = start.x() + dx * t_pos
                cy = start.y() + dy * t_pos
                size = max_size * (t_size / max_t) if max_t > 0 else max_size
                hx = nx * size / 2.0
                hy = ny * size / 2.0
                p.drawLine(QPointF(cx - hx, cy - hy), QPointF(cx + hx, cy + hy))
        return self._make_icon(draw)

    def _icon_bond_dotted(self) -> QIcon:
        def draw(p):
            pen = self.canvas.renderer.dotted_bond_pen()
            pen.setColor(QColor("#3d3229"))
            p.setPen(pen)
            p.drawLine(5, 15, 25, 15)
        return self._make_icon(draw)

    def _icon_bond_length(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(6, 15, 24, 15)
            p.drawLine(6, 11, 6, 19)
            p.drawLine(24, 11, 24, 19)
        return self._make_icon(draw)

    def _icon_arrow_preview(self, kind: str) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            if kind == "dotted":
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            if kind in {"curved_single", "curved_double"}:
                path = QPainterPath()
                path.moveTo(6, 19)
                path.quadTo(15, 6, 24, 15)
                p.drawPath(path)
                self._draw_arrow_head(p, QPointF(15, 8), QPointF(24, 15))
                if kind == "curved_double":
                    self._draw_arrow_head(p, QPointF(15, 8), QPointF(6, 19))
            elif kind == "equilibrium":
                p.drawLine(5, 11, 23, 11)
                self._draw_arrow_head(p, QPointF(5, 11), QPointF(23, 11))
                p.drawLine(23, 19, 5, 19)
                self._draw_arrow_head(p, QPointF(23, 19), QPointF(5, 19))
            elif kind == "resonance":
                p.drawLine(5, 15, 23, 15)
                self._draw_arrow_head(p, QPointF(5, 15), QPointF(23, 15))
                self._draw_arrow_head(p, QPointF(23, 15), QPointF(5, 15))
            elif kind == "inhibit":
                p.drawLine(5, 15, 23, 15)
                p.drawLine(23, 10, 23, 20)
            else:
                p.drawLine(5, 15, 23, 15)
                self._draw_arrow_head(p, QPointF(5, 15), QPointF(23, 15))
        return self._make_icon(draw)

    def _draw_arrow_head(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = 4.5
        head_angle = math.radians(25)
        left = QPointF(
            end.x() - head_len * math.cos(angle - head_angle),
            end.y() - head_len * math.sin(angle - head_angle),
        )
        right = QPointF(
            end.x() - head_len * math.cos(angle + head_angle),
            end.y() - head_len * math.sin(angle + head_angle),
        )
        painter.drawLine(left, end)
        painter.drawLine(right, end)

    def _icon_orbital_preview(self, kind: str) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            if kind == "s":
                p.drawEllipse(9, 9, 12, 12)
            elif kind == "p":
                p.drawEllipse(6, 11, 10, 10)
                p.drawEllipse(14, 9, 10, 10)
            elif kind == "sp":
                p.drawEllipse(6, 12, 10, 10)
                p.drawEllipse(16, 8, 10, 10)
                p.drawLine(5, 18, 25, 12)
            elif kind in {"sp2", "sp3"}:
                p.drawEllipse(7, 7, 8, 8)
                p.drawEllipse(15, 7, 8, 8)
                p.drawEllipse(11, 15, 8, 8)
                if kind == "sp3":
                    p.drawEllipse(11, 2, 8, 8)
            elif kind == "d":
                p.drawEllipse(6, 10, 8, 8)
                p.drawEllipse(16, 10, 8, 8)
                p.drawEllipse(11, 5, 8, 8)
                p.drawEllipse(11, 15, 8, 8)
            else:
                p.drawEllipse(9, 9, 12, 12)
                p.drawLine(15, 9, 15, 21)
        return self._make_icon(draw)

    def _icon_template_preview(self, label: str) -> QIcon:
        def draw_ring(p, sides: int):
            center = QPointF(15.0, 15.0)
            radius = 10.0
            poly = QPolygonF()
            for i in range(sides):
                angle = math.radians(360 / sides * i - 90)
                poly.append(
                    QPointF(
                        center.x() + radius * math.cos(angle),
                        center.y() + radius * math.sin(angle),
                    )
                )
            p.drawPolygon(poly)

        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            lower = label.lower()
            if "cyclopropane" in lower:
                draw_ring(p, 3)
            elif "cyclobutane" in lower:
                draw_ring(p, 4)
            elif "cyclopentane" in lower or "furan" in lower or "thiophene" in lower:
                draw_ring(p, 5)
            elif "benzene" in lower or "pyridine" in lower or "pyrimidine" in lower:
                draw_ring(p, 6)
            elif "naphthalene" in lower or "anthracene" in lower or "phenanthrene" in lower:
                draw_ring(p, 6)
                draw_ring(p, 6)
                p.drawLine(12, 7, 18, 7)
            elif "crown" in lower:
                draw_ring(p, 10)
            elif "chair" in lower:
                chair = self._chair_icon_points(self._chair_icon_rect())
                if not chair.isEmpty():
                    p.drawPolygon(chair)
            elif label in {"Me", "Et", "t-Bu", "i-Pr"}:
                p.drawLine(5, 15, 15, 15)
                p.drawText(16, 18, label)
            elif label in {"Vinyl", "Allyl"}:
                p.drawLine(5, 18, 14, 12)
                p.drawLine(14, 12, 23, 18)
            elif label in {"Carboxyl", "Carbonyl"}:
                p.drawLine(5, 15, 15, 15)
                p.drawLine(15, 15, 23, 10)
                p.drawText(23, 12, "O")
            elif label in {"Nitro", "Sulfonyl"}:
                p.drawLine(5, 15, 15, 15)
                p.drawText(16, 18, "NO2" if label == "Nitro" else "SO2")
            else:
                draw_ring(p, 6)
        return self._make_icon(draw)

    @staticmethod
    def _chair_icon_rect() -> QRectF:
        return QRectF(2.0, 5.5, 26.0, 19.0)

    def _chair_icon_points(self, rect: QRectF) -> QPolygonF:
        angle_steep = math.radians(-68.0)
        angle_shallow = math.radians(-25.0)
        v1 = QPointF(math.cos(angle_steep), math.sin(angle_steep))
        v2 = QPointF(math.cos(angle_shallow), math.sin(angle_shallow))

        points = [
            QPointF(0.0, 0.0),
            QPointF(v1.x(), v1.y()),
            QPointF(v1.x() + 1.0, v1.y()),
            QPointF(v1.x() + 1.0 + v2.x(), v1.y() + v2.y()),
            QPointF(1.0 + v2.x(), v2.y()),
            QPointF(v2.x(), v2.y()),
        ]
        min_x = min(point.x() for point in points)
        max_x = max(point.x() for point in points)
        min_y = min(point.y() for point in points)
        max_y = max(point.y() for point in points)
        width = max_x - min_x
        height = max_y - min_y
        if width <= 1e-6 or height <= 1e-6:
            return QPolygonF()
        scale = min(rect.width() / width, rect.height() / height) * 0.92
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        center = rect.center()
        poly = QPolygonF()
        for point in points:
            poly.append(
                QPointF(
                    center.x() + (point.x() - cx) * scale,
                    center.y() + (point.y() - cy) * scale,
                )
            )
        return poly

    def _icon_flip_h(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(15, 5, 15, 25)
            p.drawLine(7, 9, 13, 9)
            p.drawLine(7, 21, 13, 21)
            p.drawLine(17, 9, 23, 9)
            p.drawLine(17, 21, 23, 21)
        return self._make_icon(draw)

    def _icon_flip_v(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(9, 7, 9, 13)
            p.drawLine(21, 7, 21, 13)
            p.drawLine(9, 17, 9, 23)
            p.drawLine(21, 17, 21, 23)
        return self._make_icon(draw)

    def _icon_arrow(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(5, 15, 23, 15)
            p.drawLine(23, 15, 18, 11)
            p.drawLine(23, 15, 18, 19)
        return self._make_icon(draw)

    def _icon_ts_bracket(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.drawLine(8, 7, 5, 7)
            p.drawLine(5, 7, 5, 23)
            p.drawLine(5, 23, 8, 23)
            p.drawLine(22, 7, 25, 7)
            p.drawLine(25, 7, 25, 23)
            p.drawLine(25, 23, 22, 23)
            font = p.font()
            font.setPixelSize(8)
            p.setFont(font)
            p.drawText(QRectF(10.0, 8.0, 12.0, 8.0), Qt.AlignmentFlag.AlignCenter, "TS")
        return self._make_icon(draw)

    def _icon_orbital(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawEllipse(6, 10, 8, 10)
            p.drawEllipse(16, 10, 8, 10)
        return self._make_icon(draw)

    def _icon_move(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.drawLine(15, 5, 15, 25)
            p.drawLine(5, 15, 25, 15)
            p.drawLine(15, 5, 12, 8)
            p.drawLine(15, 5, 18, 8)
            p.drawLine(15, 25, 12, 22)
            p.drawLine(15, 25, 18, 22)
            p.drawLine(5, 15, 8, 12)
            p.drawLine(5, 15, 8, 18)
            p.drawLine(25, 15, 22, 12)
            p.drawLine(25, 15, 22, 18)
        return self._make_icon(draw)

    def _icon_color(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(QBrush(QColor("#d8c8a6")))
            palette = QPainterPath()
            palette.moveTo(4, 18)
            palette.cubicTo(4, 8, 15, 6, 25, 9)
            palette.cubicTo(29, 10, 29, 20, 23, 24)
            palette.cubicTo(18, 26, 11, 25, 9, 21)
            palette.cubicTo(14, 23, 15, 20, 14, 18)
            palette.cubicTo(11, 20, 6, 20, 4, 18)
            p.drawPath(palette)
            p.setBrush(QBrush(Qt.GlobalColor.white))
            p.drawEllipse(9, 13, 4, 4)
            p.drawEllipse(14, 11, 4, 4)
            p.drawEllipse(19, 15, 4, 4)
        return self._make_icon(draw)

    def _icon_perspective(self) -> QIcon:
        def draw(p):
            pen = QPen(QColor("#3d3229"))
            pen.setWidthF(1.4)
            p.setPen(pen)
            cx, cy, r = 15.0, 15.0, 10.0
            start_deg = 40.0
            span_deg = 280.0
            end_deg = (start_deg + span_deg) % 360.0
            p.drawArc(5, 5, 20, 20, int(start_deg * 16), int(span_deg * 16))
            rad = math.radians(end_deg)
            end = QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))
            tangent = rad + math.pi / 2.0
            head_len = 3.0
            head_angle = math.radians(25.0)
            left = QPointF(
                end.x() + head_len * math.cos(tangent + math.pi + head_angle),
                end.y() - head_len * math.sin(tangent + math.pi + head_angle),
            )
            right = QPointF(
                end.x() + head_len * math.cos(tangent + math.pi - head_angle),
                end.y() - head_len * math.sin(tangent + math.pi - head_angle),
            )
            p.drawLine(end, left)
            p.drawLine(end, right)
        return self._make_icon(draw)

    def _init_panels(self) -> None:
        dock = QDockWidget("Panels", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setMinimumWidth(320)
        dock.setMaximumWidth(420)
        title_bar = QWidget(dock)
        title_bar.setFixedHeight(0)
        dock.setTitleBarWidget(title_bar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.preview_3d)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([1])

        dock.setWidget(splitter)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.panel_splitter = splitter
        self.panel_dock = dock

    def _show_panel(self, index: int) -> None:
        if self.panel_dock is None:
            return
        self.panel_dock.show()
        self.panel_dock.raise_()

    def _apply_theme(self) -> None:
        self.setStyleSheet(MAIN_WINDOW_STYLESHEET)

    def _update_zoom_label(self, zoom_percent: int) -> None:
        if not hasattr(self, "_zoom_label"):
            return
        self._zoom_label.setText(f"{zoom_percent}%")

    def _open_arrow_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Arrow Settings")
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)

        preset_label = QLabel("Preset")
        preset_combo = QComboBox()
        preset_combo.addItems(["Default", "Bold", "Fine"])
        preset_combo.currentTextChanged.connect(self._set_arrow_preset)

        width_label = QLabel("Width")
        width_slider = QSlider(Qt.Orientation.Horizontal)
        width_slider.setMinimum(1)
        width_slider.setMaximum(6)
        width_slider.setValue(int(self.canvas.get_arrow_line_width()))
        width_slider.valueChanged.connect(lambda value: self.canvas.set_arrow_line_width(value))

        head_label = QLabel("Head")
        head_slider = QSlider(Qt.Orientation.Horizontal)
        head_slider.setMinimum(10)
        head_slider.setMaximum(60)
        head_slider.setValue(int(self.canvas.get_arrow_head_scale() * 100))
        head_slider.valueChanged.connect(lambda value: self.canvas.set_arrow_head_scale(value / 100.0))

        snap_check = QCheckBox("Curve Snap")
        snap_check.setChecked(self.canvas.get_curved_snap())
        snap_check.toggled.connect(self.canvas.set_curved_snap)

        symmetry_check = QCheckBox("Curve Symmetry")
        symmetry_check.setChecked(self.canvas.get_curved_symmetry())
        symmetry_check.toggled.connect(self.canvas.set_curved_symmetry)

        snap_label = QLabel("Snap Step")
        snap_slider = QSlider(Qt.Orientation.Horizontal)
        snap_slider.setMinimum(5)
        snap_slider.setMaximum(40)
        snap_slider.setValue(int(self.canvas.get_curved_snap_step() * 100))
        snap_slider.valueChanged.connect(lambda value: self.canvas.set_curved_snap_step(value / 100.0))

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

    def _add_menu_action(
        self,
        menu: QMenu,
        label: str,
        callback: Callable[[], None],
        icon: QIcon | None = None,
    ) -> QAction:
        action = menu.addAction(icon, label) if icon is not None else menu.addAction(label)
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        return action

    def _palette_icon(self, hex_value: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(hex_value))
        return QIcon(pixmap)

    def _populate_template_menu(self, menu: QMenu) -> None:
        for label, handler in self._template_entries():
            self._add_menu_action(menu, label, handler, self._icon_template_preview(label))

    def _populate_arrow_menu(self, menu: QMenu) -> None:
        for label, kind in ARROW_MENU_SPECS:
            self._add_menu_action(
                menu,
                label,
                lambda value=label: self._activate_arrow_type_from_menu(value),
                self._icon_arrow_preview(kind),
            )
        preset_menu = menu.addMenu("Preset")
        for label in ARROW_PRESET_SPECS:
            self._add_menu_action(
                preset_menu,
                label,
                lambda value=label: self._activate_arrow_preset_from_menu(value),
            )
        menu.addSeparator()
        self._add_menu_action(menu, "Settings...", self._open_arrow_settings)

    def _populate_palette_menu(self, menu: QMenu, callback: Callable[[str], None]) -> None:
        for label, hex_value in self._acs_color_palette():
            self._add_menu_action(
                menu,
                label,
                lambda value=hex_value: callback(value),
                self._palette_icon(hex_value),
            )

    def _activate_arrow_type_from_menu(self, value: str) -> None:
        self._set_tool_with_status("arrow")
        self._set_arrow_type(value)

    def _activate_arrow_preset_from_menu(self, value: str) -> None:
        self._set_tool_with_status("arrow")
        self._set_arrow_preset(value)

    def _template_entries(self) -> list[tuple[str, Callable[[], None]]]:
        return [
            (
                label,
                lambda ring_size=ring_size, style=style: self.canvas.begin_ring_template_insert(
                    ring_size,
                    style=style,
                ),
            )
            for label, ring_size, style in TEMPLATE_ENTRY_SPECS
        ]

    def _acs_color_palette(self) -> list[tuple[str, str]]:
        return list(COLOR_PALETTE_SPECS)

    def _apply_color_preset(self, hex_value: str) -> None:
        color = QColor(hex_value)
        tool = self.canvas.tools.tools.get("color") if hasattr(self.canvas, "tools") else None
        if tool is not None:
            tool._last_color = color.name()
        def apply_color() -> None:
            self.canvas.set_tool("color")
            for item in self.canvas.scene().selectedItems():
                if item.data(0) in {"bond", "atom", "ring"}:
                    self.canvas.apply_color_to_item(item, color)
        QTimer.singleShot(0, apply_color)

    def _apply_ring_fill_preset(self, hex_value: str) -> None:
        color = QColor(hex_value)
        def apply_fill() -> None:
            for item in self.canvas.scene().selectedItems():
                if item.data(0) == "ring":
                    self.canvas.apply_ring_fill_color(item, color)
        QTimer.singleShot(0, apply_fill)

    def _set_bond_style(self, value: str) -> None:
        mapping = {
            "Single": ("single", 1),
            "Double": ("double", 2),
            "Triple": ("triple", 3),
            "Bold": ("bold_in", 1),
            "Wedge": ("wedge", 1),
            "Hash": ("hash", 1),
            "Dotted": ("dotted", 1),
        }
        style, order = mapping.get(value, ("single", 1))
        self.canvas.set_bond_style(style, order)

    _tool_display_names = {
        "select": "Select",
        "bond": "Bond",
        "text": "Atom / Text",
        "benzene": "Ring",
        "arrow": "Arrow",
        "ts_bracket": "TS Bracket",
        "orbital": "Orbital",
        "perspective": "Perspective",
        "color": "Color",
        "mark": "Mark",
    }

    def _sync_tool_actions_from_canvas(self) -> None:
        if not hasattr(self, "_tool_actions"):
            return
        active = self.canvas.tools.active.name if self.canvas.tools.active is not None else None
        action = None
        if active == "bond":
            if self.canvas.active_bond_style in {"bold", "bold_in", "bold_out"}:
                action = self._tool_actions.get("bond_bold")
            elif self.canvas.active_bond_style == "wedge":
                action = self._tool_actions.get("bond_wedge")
            elif self.canvas.active_bond_style == "hash":
                action = self._tool_actions.get("bond_hash")
            elif self.canvas.active_bond_style == "dotted":
                action = self._tool_actions.get("bond_dotted")
            else:
                action = self._tool_actions.get("bond")
        elif active == "mark":
            action = self._tool_actions.get(f"mark_{self.canvas.mark_kind}")
        elif active is not None:
            action = self._tool_actions.get(active)
        if action is not None:
            action.setChecked(True)

    def _set_tool_with_status(self, tool: str, reset_bond_style: bool = True) -> None:
        self.canvas.set_tool(tool)
        if tool == "bond" and reset_bond_style:
            self._set_bond_style("Single")
        display = self._tool_display_names.get(tool, tool.capitalize())
        self.statusBar().showMessage(f"{display} Tool")

    def _set_arrow_type(self, value: str) -> None:
        mapping = {
            "Reaction": "reaction",
            "Equilibrium": "equilibrium",
            "Resonance": "resonance",
            "Curved Single": "curved_single",
            "Curved Double": "curved_double",
            "Inhibition": "inhibit",
            "Dotted": "dotted",
        }
        self.canvas.set_arrow_type(mapping.get(value, "reaction"))

    def _set_orbital_type(self, value: str) -> None:
        mapping = {
            "s": "s",
            "p": "p",
            "sp": "sp",
            "sp2": "sp2",
            "sp3": "sp3",
            "d": "d",
            "MO bonding": "mo_bonding",
            "MO antibonding": "mo_antibonding",
        }
        self.canvas.set_orbital_type(mapping.get(value, "s"))

    def _set_orbital_phase(self, value: str) -> None:
        self.canvas.set_orbital_phase_enabled(value == "Phase On")

    def _set_arrow_preset(self, value: str) -> None:
        presets = {
            "Default": (1.2, 0.3),
            "ACS": (1.2, 0.3),
            "Bold": (2.2, 0.4),
            "Fine": (0.8, 0.25),
        }
        width, head = presets.get(value, (1.2, 0.3))
        self.canvas.set_arrow_line_width(width)
        self.canvas.set_arrow_head_scale(head)

    def _set_text_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Text Color")
        if color.isValid():
            self.canvas.set_text_color(color)

    def _set_text_align(self, value: str) -> None:
        mapping = {"Left": "left", "Center": "center", "Right": "right"}
        self.canvas.set_text_alignment(mapping.get(value, "left"))

    def _set_note_box_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Box Color")
        if color.isValid():
            self.canvas.set_note_box_color(color)

    def _set_note_border_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Border Color")
        if color.isValid():
            self.canvas.set_note_border_color(color)

    def _set_text_preset(self, value: str) -> None:
        if value == "ACS":
            self.canvas.apply_text_preset_acs()
        elif value == "Paper Thin":
            self.canvas.apply_text_preset_paper_thin()
        elif value == "Paper Bold":
            self.canvas.apply_text_preset_paper_bold()

    @staticmethod
    def _normalize_xyz_export_path(dialog_path: str | None) -> str | None:
        if not dialog_path:
            return None
        path = Path(dialog_path)
        if path.suffix:
            return str(path)
        return str(path.with_suffix(".xyz"))

    def _default_xyz_export_path(self) -> str:
        if self._current_file_path:
            return str(Path(self._current_file_path).with_suffix(".xyz"))
        return ""

    def _default_save_dialog_path(self) -> str:
        return self._current_file_path or ""

    def _save_canvas_to_path(self, path: str) -> bool:
        try:
            self._save_document_state(path)
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save file:\n{exc}")
            return False
        self._current_file_path = path
        self.statusBar().showMessage(f"Saved: {path}")
        return True

    def _save_canvas(self) -> None:
        path = resolve_save_path(current_path=self._current_file_path)
        if path is None:
            self._save_canvas_as()
            return
        self._save_canvas_to_path(path)

    def _save_canvas_as(self) -> None:
        dialog_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Drawing As",
            self._default_save_dialog_path(),
            "LiteDraw (*.ldraw);;JSON (*.json);;All Files (*)",
        )
        path = resolve_save_as_path(dialog_path)
        if path is None:
            return
        self._save_canvas_to_path(path)

    def _export_xyz(self) -> None:
        dialog_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export 3D XYZ",
            self._default_xyz_export_path(),
            "XYZ (*.xyz);;All Files (*)",
        )
        path = self._normalize_xyz_export_path(dialog_path)
        if path is None:
            return
        try:
            self.canvas.export_xyz(path)
        except Exception as exc:
            QMessageBox.warning(self, "Export Error", f"Failed to export XYZ:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported XYZ: {path}")

    def _load_canvas(self) -> None:
        dialog_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Drawing",
            "",
            "LiteDraw (*.ldraw);;JSON (*.json);;All Files (*)",
        )
        path = resolve_load_path(dialog_path)
        if path is None:
            return
        try:
            document = read_document(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load file:\n{exc}")
            return
        state = document.state
        if "sheets" in state:
            self._restore_workbook_document(state)
        else:
            self._restore_single_sheet_document(state)
        self._current_file_path = path
        self.statusBar().showMessage(f"Loaded: {path}")

    def _set_bond_length(self) -> None:
        current = self.canvas.renderer.style.bond_length_px
        dialog = QDialog(self)
        dialog.setWindowTitle("Bond Length")
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)

        label = QLabel("Set bond length (px):")
        layout.addWidget(label)

        frame = QFrame()
        frame.setObjectName("spinFrame")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(2, 2, 2, 2)
        frame_layout.setSpacing(0)

        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(10.0, 200.0)
        spin.setValue(current)
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        spin.setMinimumWidth(90)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        frame_layout.addWidget(spin)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(0, 0, 0, 0)
        buttons_col.setSpacing(0)
        up_btn = ArrowButton("up")
        up_btn.setObjectName("spinUpButton")
        up_btn.setFixedSize(18, 14)
        down_btn = ArrowButton("down")
        down_btn.setObjectName("spinDownButton")
        down_btn.setFixedSize(18, 14)
        buttons_col.addWidget(up_btn)
        buttons_col.addWidget(down_btn)
        frame_layout.addLayout(buttons_col)

        layout.addWidget(frame)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        action_row.addWidget(ok_btn)
        action_row.addWidget(cancel_btn)
        layout.addLayout(action_row)

        up_btn.clicked.connect(lambda: spin.setValue(min(200.0, spin.value() + 1.0)))
        down_btn.clicked.connect(lambda: spin.setValue(max(10.0, spin.value() - 1.0)))
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.canvas.set_bond_length(spin.value())
