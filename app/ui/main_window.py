from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QIcon,
    QPainter,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QColorDialog,
    QLabel,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QToolButton,
    QTabBar,
    QTabWidget,
    QWidget,
)

from core.document_io import read_document
from ui.canvas_view import CanvasView
from ui.main_window_canvas_logic import (
    active_canvas_sheet_index as active_canvas_sheet_index_helper,
    active_canvas_tab_index as active_canvas_tab_index_helper,
    resolve_active_canvas,
)
from ui.main_window_canvas_sheet_service import MainWindowCanvasSheetService
from ui.main_window_icon_factory import MainWindowIconFactory
from ui.main_window_text_style_service import MainWindowTextStyleService
from ui.main_window_tool_state_service import MainWindowToolStateService
from ui.main_window_tool_routing_service import MainWindowToolRoutingService
from ui.main_window_canvas_tab_ui_service import MainWindowCanvasTabUIService
from ui.main_window_active_canvas_ui_service import MainWindowActiveCanvasUIService
from ui.main_window_workbook_document_service import MainWindowWorkbookDocumentService
from ui.main_window_path_logic import resolve_load_path, resolve_save_as_path, resolve_save_path
from ui.main_window_document_action_service import MainWindowDocumentActionService
from ui.main_window_ui_assembly_service import (
    CornerMenuButton,
    MainWindowUIAssemblyService,
)
from ui.main_window_tool_action_service import MainWindowToolActionService
from ui.preview_3d import Preview3D


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
        self._document_action_service = MainWindowDocumentActionService()
        self._tool_action_service = MainWindowToolActionService()
        self._tool_state_service = MainWindowToolStateService()
        self._tool_routing_service = MainWindowToolRoutingService()
        self._text_style_service = MainWindowTextStyleService()
        self._canvas_tab_ui_service = MainWindowCanvasTabUIService()
        self._canvas_sheet_service = MainWindowCanvasSheetService()
        self._active_canvas_ui_service = MainWindowActiveCanvasUIService()
        self._workbook_document_service = MainWindowWorkbookDocumentService()
        self._ui_assembly_service = MainWindowUIAssemblyService()

        self._add_canvas_sheet(name=self._next_canvas_sheet_name(), select=True)
        self._icon_factory = MainWindowIconFactory(self)
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
        return resolve_active_canvas(
            self.canvas_tabs.currentWidget(),
            self._last_canvas_tab_index,
            self._canvas_tab_entries(),
        )

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
        return active_canvas_tab_index_helper(
            self._canvas_tab_entries(),
            self._active_canvas_or_none(),
        )

    def _active_canvas_sheet_index(self) -> int:
        return active_canvas_sheet_index_helper(
            self._canvas_tab_entries(),
            self._active_canvas_or_none(),
        )

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
        self._canvas_tab_ui_service.ensure_add_sheet_tab(self)

    def _keep_add_tab_last(self) -> None:
        self._canvas_tab_ui_service.keep_add_tab_last(self)

    def _on_canvas_tab_moved(self, from_index: int, to_index: int) -> None:
        self._canvas_tab_ui_service.on_canvas_tab_moved(self, from_index, to_index)

    def _can_delete_canvas_sheet(self, index: int) -> bool:
        return self._canvas_tab_ui_service.can_delete_canvas_sheet(self, index)

    def _show_canvas_tab_context_menu(self, pos) -> None:
        self._canvas_tab_ui_service.show_canvas_tab_context_menu(self, pos)

    def _delete_canvas_sheet(self, index: int) -> None:
        self._canvas_tab_ui_service.delete_canvas_sheet(self, index)

    def _create_canvas(self, *, template: CanvasView | None = None) -> CanvasView:
        return self._canvas_sheet_service.create_canvas(self, template=template)

    def _add_canvas_sheet(
        self,
        *,
        name: str,
        state: dict | None = None,
        select: bool = True,
        template: CanvasView | None = None,
    ) -> CanvasView:
        return self._canvas_sheet_service.add_canvas_sheet(
            self,
            name=name,
            state=state,
            select=select,
            template=template,
        )

    def _open_result_canvas_sheet(
        self,
        name: str,
        *,
        select: bool = True,
        exact_name: bool = False,
    ) -> tuple[str | None, CanvasView | None]:
        return self._canvas_sheet_service.open_result_canvas_sheet(
            self,
            name,
            select=select,
            exact_name=exact_name,
        )

    def _bind_active_canvas(self) -> None:
        self._active_canvas_ui_service.bind_active_canvas(self)

    def _handle_selection_info(self, _formula: str, _mw: str) -> None:
        self._active_canvas_ui_service.handle_selection_info(self, _formula, _mw)

    def _current_zoom_percent(self) -> int:
        return self._active_canvas_ui_service.current_zoom_percent(self)

    def _refresh_active_canvas_ui(self) -> None:
        self._active_canvas_ui_service.refresh_active_canvas_ui(self)

    def _on_canvas_tab_changed(self, index: int) -> None:
        self._active_canvas_ui_service.on_canvas_tab_changed(self, index)

    def _new_canvas_sheet(self) -> None:
        self._canvas_tab_ui_service.new_canvas_sheet(self)

    def _clear_canvas_sheets(self) -> None:
        self._workbook_document_service.clear_canvas_sheets(self)

    def _workbook_state(self) -> dict:
        return self._workbook_document_service.workbook_state(self)

    def _restore_single_sheet_document(self, state: dict) -> None:
        self._workbook_document_service.restore_single_sheet_document(self, state)

    def _restore_workbook_document(self, state: dict) -> None:
        self._workbook_document_service.restore_workbook_document(self, state)

    def _save_document_state(self, path: str) -> None:
        self._workbook_document_service.save_document_state(self, path)

    def _new_tool_action(self, label: str) -> QAction:
        return QAction(label, self)

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
        return self._tool_action_service.build_checkable_tool_action(
            self,
            tool_group,
            key=key,
            label=label,
            icon_method=icon_method,
            tooltip=tooltip,
            callback=callback,
        )

    def _activate_bond_style_tool(self, value: str) -> None:
        self._tool_action_service.activate_bond_style_tool(self, value)

    def _activate_mark_tool(self, kind: str) -> None:
        self._tool_action_service.activate_mark_tool(self, kind)

    def _build_tool_actions(self, tool_group: QActionGroup) -> dict[str, QAction]:
        return self._tool_action_service.build_tool_actions(self, tool_group)

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
        return self._ui_assembly_service.create_toolbar_button(
            icon=icon,
            tooltip=tooltip,
            callback=callback,
            shortcut=shortcut,
            text=text,
            object_name=object_name,
            style_sheet=style_sheet,
            auto_raise=auto_raise,
            cursor=cursor,
        )

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
        return self._ui_assembly_service.create_corner_menu_button(
            icon=icon,
            tooltip=tooltip,
            style_sheet=style_sheet,
            popup_mode=popup_mode,
            menu_builder=menu_builder,
            default_action=default_action,
        )

    def _create_save_menu_button(self, save_action: QAction, save_as_action: QAction) -> CornerMenuButton:
        return self._ui_assembly_service.create_save_menu_button(save_action, save_as_action)

    def _init_toolbars(self) -> None:
        assembly = self._ui_assembly_service.init_toolbars(self)
        self._tool_actions = assembly.tool_actions
        self._atom_input = assembly.atom_input

    def _make_icon(self, painter_fn, size: int = 30) -> QIcon:
        return self._icon_factory.make_icon(painter_fn, size)

    def _icon_select(self) -> QIcon:
        return self._icon_factory.icon_select()

    def _icon_bond(self) -> QIcon:
        return self._icon_factory.icon_bond()

    def _icon_bond_bold(self) -> QIcon:
        return self._icon_factory.icon_bond_bold()

    def _icon_mark_plus(self) -> QIcon:
        return self._icon_factory.icon_mark_plus()

    def _icon_mark_minus(self) -> QIcon:
        return self._icon_factory.icon_mark_minus()

    def _icon_mark_radical(self) -> QIcon:
        return self._icon_factory.icon_mark_radical()

    def _icon_text(self) -> QIcon:
        return self._icon_factory.icon_text()

    def _benzene_icon_polygon(self, center: QPointF, radius: float) -> QPolygonF:
        return self._icon_factory.benzene_icon_polygon(center, radius)

    def _benzene_icon_inner_segments(
        self,
        polygon: QPolygonF,
        center: QPointF,
        *,
        spacing_scale: float = 1.0,
    ) -> list[tuple[QPointF, QPointF]]:
        return self._icon_factory.benzene_icon_inner_segments(
            polygon,
            center,
            spacing_scale=spacing_scale,
        )

    def _icon_ring(self) -> QIcon:
        return self._icon_factory.icon_ring()

    def _icon_ring_fill(self) -> QIcon:
        return self._icon_factory.icon_ring_fill()

    def _icon_undo(self) -> QIcon:
        return self._icon_factory.icon_undo()

    def _icon_redo(self) -> QIcon:
        return self._icon_factory.icon_redo()

    def _icon_save(self) -> QIcon:
        return self._icon_factory.icon_save()

    def _icon_open(self) -> QIcon:
        return self._icon_factory.icon_open()

    def _icon_export_xyz(self) -> QIcon:
        return self._icon_factory.icon_export_xyz()

    def _icon_add_sheet(self) -> QIcon:
        return self._icon_factory.icon_add_sheet()

    def _icon_templates(self) -> QIcon:
        return self._icon_factory.icon_templates()

    def _icon_info(self) -> QIcon:
        return self._icon_factory.icon_info()

    def _icon_bond_double(self) -> QIcon:
        return self._icon_factory.icon_bond_double()

    def _icon_bond_triple(self) -> QIcon:
        return self._icon_factory.icon_bond_triple()

    def _icon_bond_wedge(self) -> QIcon:
        return self._icon_factory.icon_bond_wedge()

    def _icon_bond_hash(self) -> QIcon:
        return self._icon_factory.icon_bond_hash()

    def _icon_bond_dotted(self) -> QIcon:
        return self._icon_factory.icon_bond_dotted()

    def _icon_bond_length(self) -> QIcon:
        return self._icon_factory.icon_bond_length()

    def _icon_arrow_preview(self, kind: str) -> QIcon:
        return self._icon_factory.icon_arrow_preview(kind)

    def _draw_arrow_head(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        self._icon_factory.draw_arrow_head(painter, start, end)

    def _icon_orbital_preview(self, kind: str) -> QIcon:
        return self._icon_factory.icon_orbital_preview(kind)

    def _icon_template_preview(self, label: str) -> QIcon:
        return self._icon_factory.icon_template_preview(label)

    def _chair_icon_rect(self) -> QRectF:
        return self._icon_factory.chair_icon_rect()

    def _chair_icon_points(self, rect: QRectF) -> QPolygonF:
        return self._icon_factory.chair_icon_points(rect)

    def _icon_flip_h(self) -> QIcon:
        return self._icon_factory.icon_flip_h()

    def _icon_flip_v(self) -> QIcon:
        return self._icon_factory.icon_flip_v()

    def _icon_arrow(self) -> QIcon:
        return self._icon_factory.icon_arrow()

    def _icon_ts_bracket(self) -> QIcon:
        return self._icon_factory.icon_ts_bracket()

    def _icon_orbital(self) -> QIcon:
        return self._icon_factory.icon_orbital()

    def _icon_move(self) -> QIcon:
        return self._icon_factory.icon_move()

    def _icon_color(self) -> QIcon:
        return self._icon_factory.icon_color()

    def _icon_perspective(self) -> QIcon:
        return self._icon_factory.icon_perspective()

    def _init_panels(self) -> None:
        assembly = self._ui_assembly_service.init_panels(self)
        self.panel_splitter = assembly.splitter
        self.panel_dock = assembly.dock

    def _show_panel(self, index: int) -> None:
        if self.panel_dock is None:
            return
        self.panel_dock.show()
        self.panel_dock.raise_()

    def _apply_theme(self) -> None:
        self._ui_assembly_service.apply_theme(self)

    def _update_zoom_label(self, zoom_percent: int) -> None:
        if not hasattr(self, "_zoom_label"):
            return
        self._zoom_label.setText(f"{zoom_percent}%")

    def _open_arrow_settings(self) -> None:
        self._ui_assembly_service.open_arrow_settings(self)

    def _add_menu_action(
        self,
        menu: QMenu,
        label: str,
        callback: Callable[[], None],
        icon: QIcon | None = None,
    ) -> QAction:
        return self._tool_routing_service.add_menu_action(menu, label, callback, icon)

    def _palette_icon(self, hex_value: str) -> QIcon:
        return self._tool_routing_service.palette_icon(hex_value)

    def _populate_template_menu(self, menu: QMenu) -> None:
        self._tool_routing_service.populate_template_menu(self, menu)

    def _populate_arrow_menu(self, menu: QMenu) -> None:
        self._tool_routing_service.populate_arrow_menu(self, menu)

    def _populate_palette_menu(self, menu: QMenu, callback: Callable[[str], None]) -> None:
        self._tool_routing_service.populate_palette_menu(self, menu, callback)

    def _activate_arrow_type_from_menu(self, value: str) -> None:
        self._tool_routing_service.activate_arrow_type_from_menu(self, value)

    def _activate_arrow_preset_from_menu(self, value: str) -> None:
        self._tool_routing_service.activate_arrow_preset_from_menu(self, value)

    def _template_entries(self) -> list[tuple[str, Callable[[], None]]]:
        return self._tool_routing_service.template_entries(self)

    def _acs_color_palette(self) -> list[tuple[str, str]]:
        return self._tool_routing_service.acs_color_palette()

    def _apply_color_preset(self, hex_value: str) -> None:
        self._tool_routing_service.apply_color_preset(self, hex_value, qtimer=QTimer)

    def _apply_ring_fill_preset(self, hex_value: str) -> None:
        self._tool_routing_service.apply_ring_fill_preset(self, hex_value, qtimer=QTimer)

    def _set_bond_style(self, value: str) -> None:
        self._tool_state_service.set_bond_style(self, value)

    def _sync_tool_actions_from_canvas(self) -> None:
        self._tool_state_service.sync_tool_actions_from_canvas(self)

    def _set_tool_with_status(self, tool: str, reset_bond_style: bool = True) -> None:
        self._tool_state_service.set_tool_with_status(self, tool, reset_bond_style=reset_bond_style)

    def _set_arrow_type(self, value: str) -> None:
        self._tool_state_service.set_arrow_type(self, value)

    def _set_orbital_type(self, value: str) -> None:
        self._tool_state_service.set_orbital_type(self, value)

    def _set_orbital_phase(self, value: str) -> None:
        self._tool_state_service.set_orbital_phase(self, value)

    def _set_arrow_preset(self, value: str) -> None:
        self._tool_state_service.set_arrow_preset(self, value)

    def _set_text_color(self) -> None:
        self._text_style_service.set_text_color(self, get_color=QColorDialog.getColor)

    def _set_text_align(self, value: str) -> None:
        self._text_style_service.set_text_align(self, value)

    def _set_note_box_color(self) -> None:
        self._text_style_service.set_note_box_color(self, get_color=QColorDialog.getColor)

    def _set_note_border_color(self) -> None:
        self._text_style_service.set_note_border_color(self, get_color=QColorDialog.getColor)

    def _set_text_preset(self, value: str) -> None:
        self._text_style_service.set_text_preset(self, value)

    @staticmethod
    def _normalize_xyz_export_path(dialog_path: str | None) -> str | None:
        return MainWindowDocumentActionService.normalize_xyz_export_path(dialog_path)

    def _default_xyz_export_path(self) -> str:
        return self._document_action_service.default_xyz_export_path(self)

    def _default_save_dialog_path(self) -> str:
        return self._document_action_service.default_save_dialog_path(self)

    def _save_canvas_to_path(self, path: str) -> bool:
        return self._document_action_service.save_canvas_to_path(self, path, message_box=QMessageBox)

    def _save_canvas(self) -> None:
        self._document_action_service.save_canvas(self, resolve_save_path=resolve_save_path)

    def _save_canvas_as(self) -> None:
        self._document_action_service.save_canvas_as(
            self,
            file_dialog=QFileDialog,
            resolve_save_as_path=resolve_save_as_path,
        )

    def _export_xyz(self) -> None:
        self._document_action_service.export_xyz(self, file_dialog=QFileDialog, message_box=QMessageBox)

    def _load_canvas(self) -> None:
        self._document_action_service.load_canvas(
            self,
            file_dialog=QFileDialog,
            message_box=QMessageBox,
            read_document=read_document,
            resolve_load_path=resolve_load_path,
        )

    def _set_bond_length(self) -> None:
        self._document_action_service.set_bond_length(self)
