from __future__ import annotations

from typing import Literal, override

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
)

from chemvas.shell.toolbar_buttons import CornerMenuButton
from chemvas.shell.toolbar_styles import TOOLBAR_MENU_BUTTON_STYLE
from chemvas.ui.scene.mark_ownership import mark_is_distant_for, mark_owner_text_for
from chemvas.ui.selection.selection_queries import (
    scene_selected_items_for,
    selection_status_count_for,
)
from chemvas.ui.window.main_window_document_dialogs import prompt_zoom_percent
from chemvas.ui.window.main_window_ports import (
    active_canvas_name_for_window,
    active_canvas_or_none_for_window,
    active_tool_name_for_window,
    color_tool_for_window,
    current_zoom_percent_for_window,
    fit_canvas_to_view_for_window,
    reset_zoom_for_window,
    set_zoom_percent_for_window,
    zoom_in_for_window,
    zoom_out_for_window,
)
from chemvas.ui.window.main_window_toolbar_logic import tool_display_name


class _ZoomPercentButton(QToolButton):
    """Zoom-readout button: single click resets, double click types a value.

    A single click is deferred by the double-click interval so a double click
    cancels it cleanly — the view never flashes to 100% on its way to the
    custom-value dialog, and the dialog opens with the real current zoom.
    """

    def __init__(self, on_single, on_double) -> None:
        super().__init__()
        self._on_single = on_single
        self._on_double = on_double
        self._pending_single = False
        self._suppress_release = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_single)

    def _emit_single(self) -> None:
        if self._pending_single:
            self._pending_single = False
            self._on_single()

    @override
    def keyPressEvent(self, event) -> None:
        if event.modifiers() == Qt.KeyboardModifier.NoModifier and event.key() in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self._timer.stop()
            self._pending_single = False
            if not event.isAutoRepeat():
                if event.key() == Qt.Key.Key_Space:
                    self._on_single()
                else:
                    self._on_double()
            event.accept()
            return
        super().keyPressEvent(event)

    @override
    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._suppress_release:
            self._suppress_release = False
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pending_single = True
            self._timer.start(QApplication.doubleClickInterval())

    @override
    def mouseDoubleClickEvent(self, event) -> None:
        self._timer.stop()
        self._pending_single = False
        self._suppress_release = True
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_double()


TOOL_HINTS: dict[str, str] = {
    "select": "Select: double-click arrows/lines for labels",
    "bond": "Bond: click-drag to draw",
    "text": "Atom / Text: click to place label",
    "mark": "Mark: click atom or label",
    "benzene": "Ring: click to place template",
    "arrow": "Arrow: drag to draw; double-click for labels",
    "line": "Line: double-click for labels; Shift locks angle",
    "note": "Text: click to add/edit; Esc to finish",
    "ts_bracket": "Brackets: drag around selection",
    "orbital": "Orbital: click to place",
    "perspective": "Perspective: drag selection to rotate",
    "color": "Color: choose a swatch",
    "ring_fill": "Ring Fill: select a complete ring, then choose a fill color",
}


class MainWindowStatusService:
    def __init__(self) -> None:
        self.tool_label: QLabel | None = None
        self.sheet_label: QLabel | None = None
        self.selection_label: QLabel | None = None
        self.autosave_error_label: QLabel | None = None
        self.zoom_caption: QLabel | None = None
        self.zoom_out_button: QToolButton | None = None
        self.zoom_in_button: QToolButton | None = None
        self.zoom_fit_button: QToolButton | None = None
        self.zoom_label: QToolButton | None = None
        self.grid_button: QToolButton | None = None
        self._grid_actions: dict[str, QAction] = {}
        self._grid_opacity_actions: dict[int, QAction] = {}

    def init_status_bar(self, window) -> None:
        self.tool_label = QLabel()
        self.sheet_label = QLabel()
        self.selection_label = QLabel()
        self.autosave_error_label = QLabel()
        self.zoom_caption = QLabel("Zoom")

        self.autosave_error_label.setObjectName("statusAutosaveErrorLabel")
        self.autosave_error_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.autosave_error_label.setMaximumWidth(480)
        self.autosave_error_label.hide()

        for label in (
            self.tool_label,
            self.sheet_label,
            self.selection_label,
            self.zoom_caption,
        ):
            label.setObjectName("statusContextLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.zoom_out_button = self._build_zoom_button(
            "−",
            "Zoom out (Ctrl+-)",
            lambda: self._apply_zoom(window, zoom_out_for_window),
        )
        # The percent reads like a label but is interactive: a single click
        # resets to 100%, a double click opens a dialog to type an exact value.
        self.zoom_label = _ZoomPercentButton(
            on_single=lambda: self._apply_zoom(window, reset_zoom_for_window),
            on_double=lambda: self._prompt_zoom(window),
        )
        self.zoom_label.setText("100%")
        self.zoom_label.setToolTip(
            "Click or Space to reset to 100% · double-click or Enter to type a value"
        )
        self.zoom_label.setStatusTip(
            "Click or Space to reset zoom, double-click or Enter to enter a value"
        )
        self.zoom_label.setAutoRaise(True)
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.setObjectName("statusZoomLabel")
        self.zoom_label.setMinimumWidth(46)
        self.zoom_in_button = self._build_zoom_button(
            "+",
            "Zoom in (Ctrl++)",
            lambda: self._apply_zoom(window, zoom_in_for_window),
        )
        self.zoom_fit_button = self._build_zoom_button(
            "Fit",
            "Fit the page to the window",
            lambda: self._apply_zoom(window, fit_canvas_to_view_for_window),
        )
        self.zoom_fit_button.setObjectName("statusZoomFitButton")

        window.statusBar().addPermanentWidget(self.autosave_error_label, 1)
        window.statusBar().addPermanentWidget(self.tool_label)
        window.statusBar().addPermanentWidget(self.sheet_label)
        window.statusBar().addPermanentWidget(self.selection_label)
        window.statusBar().addPermanentWidget(self._build_grid_control(window))
        window.statusBar().addPermanentWidget(self.zoom_caption)
        # The four zoom controls read as one instrument: a single outlined
        # pill with the percentage in the middle and Fit set off at the end.
        zoom_group = QFrame()
        zoom_group.setObjectName("statusZoomGroup")
        zoom_layout = QHBoxLayout(zoom_group)
        zoom_layout.setContentsMargins(2, 0, 2, 0)
        zoom_layout.setSpacing(0)
        for widget in (
            self.zoom_out_button,
            self.zoom_label,
            self.zoom_in_button,
            self.zoom_fit_button,
        ):
            zoom_layout.addWidget(widget)
        window.statusBar().addPermanentWidget(zoom_group)
        window.statusBar().messageChanged.connect(
            lambda message: self.show_active_tool_hint(window) if not message else None
        )
        self.refresh_status_context(window)
        self.show_active_tool_hint(window)

    def _build_grid_control(self, window) -> QToolButton:
        button = CornerMenuButton()
        button.setObjectName("statusGridButton")
        button.setStyleSheet(TOOLBAR_MENU_BUTTON_STYLE)
        button.setAutoRaise(True)
        button.setToolTip(
            "Cycle grid and arrow/line snapping; open the menu for grid strength"
        )
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button.clicked.connect(lambda _checked=False: self._cycle_grid(window))
        menu = QMenu(button)
        group = QActionGroup(menu)
        modes: tuple[Literal["none", "hex", "square"], ...] = ("none", "hex", "square")
        for mode in modes:
            action = QAction(mode.title(), menu)
            action.setCheckable(True)
            group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, value=mode: self._set_grid(window, value)
            )
            menu.addAction(action)
            self._grid_actions[mode] = action
        menu.addSeparator()
        opacity_group = QActionGroup(menu)
        for percent in (15, 20, 25):
            action = QAction(f"Strength {percent}%", menu)
            action.setCheckable(True)
            opacity_group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, value=percent: self._set_grid_opacity(
                    window, value
                )
            )
            menu.addAction(action)
            self._grid_opacity_actions[percent] = action
        menu.aboutToShow.connect(lambda: self.update_grid_control(window))
        button.setMenu(menu)
        self.grid_button = button
        return button

    def _set_grid(self, window, mode: Literal["none", "hex", "square"]) -> None:
        from chemvas.ui.window.main_window_ports import set_grid_snap_for_window

        canvas = active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        if mode != "none":
            canvas.runtime_state.tool_settings_state.grid_style = mode
        set_grid_snap_for_window(window, mode != "none")

    def _cycle_grid(self, window) -> None:
        canvas = active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        settings = canvas.runtime_state.tool_settings_state
        if not settings.grid_snap_enabled:
            self._set_grid(window, "hex")
        elif settings.grid_style == "hex":
            self._set_grid(window, "square")
        else:
            self._set_grid(window, "none")

    def _set_grid_opacity(self, window, percent: int) -> None:

        canvas = active_canvas_or_none_for_window(window)
        if canvas is not None:
            canvas.runtime_state.tool_settings_state.grid_opacity = percent / 100
            viewport = canvas.viewport()
            if viewport is not None:
                viewport.update()
            self.update_grid_control(window)

    def update_grid_control(self, window) -> None:
        if self.grid_button is None:
            return
        canvas = active_canvas_or_none_for_window(window)
        self.grid_button.setEnabled(canvas is not None)
        settings = (
            canvas.runtime_state.tool_settings_state if canvas is not None else None
        )
        mode = (
            settings.grid_style
            if settings is not None and settings.grid_snap_enabled
            else "none"
        )
        self.grid_button.setText(f"Grid: {mode.title()}")
        for key, action in self._grid_actions.items():
            action.setChecked(key == mode)
        for percent, action in self._grid_opacity_actions.items():
            action.setChecked(
                settings is not None and round(settings.grid_opacity * 100) == percent
            )

    @staticmethod
    def _build_zoom_button(text: str, tooltip: str, callback) -> QToolButton:
        button = QToolButton()
        button.setObjectName("statusZoomButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setStatusTip(tooltip)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False: callback())
        return button

    def _apply_zoom(self, window, zoom_action) -> None:
        if zoom_action is None:
            return
        self.update_zoom_label(zoom_action(window))

    def _prompt_zoom(self, window) -> None:
        current = current_zoom_percent_for_window(window)
        selected = prompt_zoom_percent(window, current)
        if selected is not None:
            self.update_zoom_label(set_zoom_percent_for_window(window, selected))

    def refresh_status_context(self, window, *, update_zoom: bool = True) -> None:
        self.update_grid_control(window)
        self.update_tool_status_label(window)
        self.update_sheet_status_label(window)
        self.update_selection_status_label(window)
        if update_zoom:
            self.update_zoom_label(current_zoom_percent_for_window(window))
        self.show_active_tool_hint(window)

    def update_tool_status_label(self, window) -> None:
        if self.tool_label is not None:
            self.tool_label.setText(self.active_tool_status_text(window))

    def update_sheet_status_label(self, window) -> None:
        if self.sheet_label is not None:
            self.sheet_label.setText(self.active_sheet_status_text(window))

    def update_selection_status_label(self, window) -> None:
        selection_count = self.current_selection_count(window)
        if self.selection_label is not None:
            text = f"Selection: {selection_count}"
            canvas = active_canvas_or_none_for_window(window)
            marks = (
                []
                if canvas is None
                else [
                    item
                    for item in scene_selected_items_for(canvas)
                    if item.data(0) == "mark"
                ]
            )
            if canvas is not None and len(marks) == 1:
                text += " | " + mark_owner_text_for(canvas, marks[0])
            elif canvas is not None and marks:
                distant = sum(mark_is_distant_for(canvas, item) for item in marks)
                text += f" | Marks: {len(marks)}, far from owner: {distant}"
            self.selection_label.setText(text)
            self.selection_label.setToolTip(
                "Moving marks keeps their chemical owner. Dashed lines show their owners; amber means far away. Right-click a mark to reassign it."
                if marks
                else ""
            )

    def update_zoom_label(self, zoom_percent: int) -> None:
        if self.zoom_label is None:
            return
        self.zoom_label.setText(f"{zoom_percent}%")
        self.zoom_label.setToolTip(f"Zoom: {zoom_percent}%")
        self.zoom_label.setStatusTip(f"Zoom: {zoom_percent}%")

    def show_error_message(self, window, message: str, *, timeout: int) -> None:
        bar = window.statusBar()
        bar.setProperty("statusState", "error")
        bar.style().unpolish(bar)
        bar.style().polish(bar)
        bar.showMessage(message, timeout)
        reset_timer = QTimer(window)
        reset_timer.setSingleShot(True)
        reset_timer.timeout.connect(lambda: self.reset_status_state(window))
        reset_timer.timeout.connect(reset_timer.deleteLater)
        reset_timer.start(timeout)

    def set_autosave_error(self, window, message: str | None) -> None:
        label = self.autosave_error_label
        if label is None:
            raise RuntimeError("status bar must be initialized before autosave status")
        if message is None:
            label.clear()
            label.setToolTip("")
            label.setStatusTip("")
            label.hide()
            return
        label.setText(message)
        label.setToolTip(message)
        label.setStatusTip(message)
        label.show()

    def reset_status_state(self, window) -> None:
        bar = window.statusBar()
        bar.setProperty("statusState", "")
        bar.style().unpolish(bar)
        bar.style().polish(bar)

    def status_context_texts(self) -> dict[str, str]:
        return {
            "tool": self.tool_label.text() if self.tool_label is not None else "",
            "sheet": self.sheet_label.text() if self.sheet_label is not None else "",
            "selection": self.selection_label.text()
            if self.selection_label is not None
            else "",
            "zoom_caption": self.zoom_caption.text()
            if self.zoom_caption is not None
            else "",
            "zoom": self.zoom_label.text() if self.zoom_label is not None else "",
        }

    def has_zoom_label(self) -> bool:
        return self.zoom_label is not None

    def active_tool_status_text(self, window) -> str:
        canvas = active_canvas_or_none_for_window(window)
        if canvas is None:
            return "Tool: None"
        tool_name = active_tool_name_for_window(window)
        if not tool_name:
            return "Tool: None"
        return f"Tool: {tool_display_name(str(tool_name))}"

    def active_tool_hint_text(self, window) -> str:
        page_override = window.runtime_state.context_bar_page_override
        if page_override == "ring_fill":
            return TOOL_HINTS["ring_fill"]
        canvas = active_canvas_or_none_for_window(window)
        if canvas is None:
            return "No active canvas"
        tool_name = active_tool_name_for_window(window)
        if not tool_name:
            return "Choose a drawing tool"
        key = str(tool_name)
        if key == "color":
            tool = color_tool_for_window(window)
            if tool is not None and tool.current_color is not None:
                return f"Color: {tool.current_color} — click an item or choose a swatch"
        return TOOL_HINTS.get(key, f"{tool_display_name(key)}: ready")

    def show_active_tool_hint(self, window) -> None:
        window.statusBar().showMessage(self.active_tool_hint_text(window))

    def active_sheet_status_text(self, window) -> str:
        canvas_count = window.tab_references.canvas_count()
        if canvas_count <= 0:
            return "Canvas: None"
        canvas_name = active_canvas_name_for_window(window) or "Untitled"
        return f"Canvas: {canvas_name}"

    def current_selection_count(self, window) -> int:
        canvas = active_canvas_or_none_for_window(window)
        if canvas is None:
            return 0
        return selection_status_count_for(canvas)


__all__ = ["MainWindowStatusService"]
