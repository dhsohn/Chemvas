from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton

from chemvas.ui.main_window_document_dialogs import prompt_zoom_percent
from chemvas.ui.main_window_toolbar_logic import tool_display_name
from chemvas.ui.selection_collection_access import selection_status_count_for


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

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._suppress_release:
            self._suppress_release = False
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pending_single = True
            self._timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, event) -> None:
        self._timer.stop()
        self._pending_single = False
        self._suppress_release = True
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_double()


TOOL_HINTS: dict[str, str] = {
    "select": "Select: click or drag marquee",
    "bond": "Bond: click-drag to draw",
    "text": "Atom / Text: click to place label",
    "mark": "Mark: click atom or label",
    "benzene": "Ring: click to place template",
    "arrow": "Arrow: drag to draw",
    "ts_bracket": "Brackets: drag around selection",
    "orbital": "Orbital: click to place",
    "perspective": "Perspective: drag selection to rotate",
    "color": "Color: choose a swatch",
    "ring_fill": "Ring Fill: choose fill color",
}


class MainWindowStatusService:
    def __init__(
        self,
        *,
        active_tool_name_for_window,
        current_zoom_percent_for_window,
        active_canvas_or_none_for_window,
        canvas_count_for_window,
        active_canvas_name_for_window,
        active_canvas_index_for_window,
        context_bar_page_override_for_window,
        zoom_in_for_window=None,
        zoom_out_for_window=None,
        reset_zoom_for_window=None,
        fit_canvas_to_view_for_window=None,
        set_zoom_percent_for_window=None,
    ) -> None:
        self._active_tool_name_for_window = active_tool_name_for_window
        self._current_zoom_percent_for_window = current_zoom_percent_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._canvas_count_for_window = canvas_count_for_window
        self._active_canvas_name_for_window = active_canvas_name_for_window
        self._active_canvas_index_for_window = active_canvas_index_for_window
        self._context_bar_page_override_for_window = (
            context_bar_page_override_for_window
        )
        self._zoom_in_for_window = zoom_in_for_window
        self._zoom_out_for_window = zoom_out_for_window
        self._reset_zoom_for_window = reset_zoom_for_window
        self._fit_canvas_to_view_for_window = fit_canvas_to_view_for_window
        self._set_zoom_percent_for_window = set_zoom_percent_for_window
        self.tool_label: QLabel | None = None
        self.sheet_label: QLabel | None = None
        self.selection_label: QLabel | None = None
        self.zoom_caption: QLabel | None = None
        self.zoom_out_button: QToolButton | None = None
        self.zoom_in_button: QToolButton | None = None
        self.zoom_fit_button: QToolButton | None = None
        self.zoom_label: QToolButton | None = None

    def init_status_bar(self, window) -> None:
        self.tool_label = QLabel()
        self.sheet_label = QLabel()
        self.selection_label = QLabel()
        self.zoom_caption = QLabel("Zoom")

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
            lambda: self._apply_zoom(window, self._zoom_out_for_window),
        )
        # The percent reads like a label but is interactive: a single click
        # resets to 100%, a double click opens a dialog to type an exact value.
        self.zoom_label = _ZoomPercentButton(
            on_single=lambda: self._apply_zoom(window, self._reset_zoom_for_window),
            on_double=lambda: self._prompt_zoom(window),
        )
        self.zoom_label.setText("100%")
        self.zoom_label.setToolTip(
            "Click to reset to 100% · double-click to type a value"
        )
        self.zoom_label.setStatusTip(
            "Click to reset zoom, double-click to enter a value"
        )
        self.zoom_label.setAutoRaise(True)
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.setObjectName("statusZoomLabel")
        self.zoom_label.setMinimumWidth(46)
        self.zoom_in_button = self._build_zoom_button(
            "+",
            "Zoom in (Ctrl++)",
            lambda: self._apply_zoom(window, self._zoom_in_for_window),
        )
        self.zoom_fit_button = self._build_zoom_button(
            "Fit",
            "Fit the page to the window",
            lambda: self._apply_zoom(window, self._fit_canvas_to_view_for_window),
        )
        self.zoom_fit_button.setObjectName("statusZoomFitButton")

        window.statusBar().addPermanentWidget(self.tool_label)
        window.statusBar().addPermanentWidget(self.sheet_label)
        window.statusBar().addPermanentWidget(self.selection_label)
        window.statusBar().addPermanentWidget(self.zoom_caption)
        window.statusBar().addPermanentWidget(self.zoom_out_button)
        window.statusBar().addPermanentWidget(self.zoom_label)
        window.statusBar().addPermanentWidget(self.zoom_in_button)
        window.statusBar().addPermanentWidget(self.zoom_fit_button)
        self.refresh_status_context(window)
        self.show_active_tool_hint(window)

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
        if self._set_zoom_percent_for_window is None:
            return
        current = self._current_zoom_percent_for_window(window)
        selected = prompt_zoom_percent(window, current)
        if selected is not None:
            self.update_zoom_label(self._set_zoom_percent_for_window(window, selected))

    def refresh_status_context(self, window, *, update_zoom: bool = True) -> None:
        self.update_tool_status_label(window)
        self.update_sheet_status_label(window)
        self.update_selection_status_label(window)
        if update_zoom:
            self.update_zoom_label(self._current_zoom_percent_for_window(window))
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
            self.selection_label.setText(f"Selection: {selection_count}")

    def update_zoom_label(self, zoom_percent: int) -> None:
        if self.zoom_label is None:
            return
        self.zoom_label.setText(f"{zoom_percent}%")
        self.zoom_label.setToolTip(f"Zoom: {zoom_percent}%")
        self.zoom_label.setStatusTip(f"Zoom: {zoom_percent}%")

    def show_error_message(
        self, window, message: str, *, timeout: int, qtimer=QTimer
    ) -> None:
        bar = window.statusBar()
        bar.setProperty("statusState", "error")
        bar.style().unpolish(bar)
        bar.style().polish(bar)
        bar.showMessage(message, timeout)
        qtimer.singleShot(timeout, lambda: self.reset_status_state(window))

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

    def zoom_status_tip(self) -> str:
        return self.zoom_label.statusTip() if self.zoom_label is not None else ""

    def has_zoom_label(self) -> bool:
        return self.zoom_label is not None

    def active_tool_status_text(self, window) -> str:
        page_override = self._context_bar_page_override_for_window(window)
        if page_override == "ring_fill":
            return "Tool: Ring Fill"
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return "Tool: None"
        tool_name = self._active_tool_name_for_window(window)
        if not tool_name:
            return "Tool: None"
        return f"Tool: {tool_display_name(str(tool_name))}"

    def active_tool_hint_text(self, window) -> str:
        page_override = self._context_bar_page_override_for_window(window)
        if page_override == "ring_fill":
            return TOOL_HINTS["ring_fill"]
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return "No active canvas"
        tool_name = self._active_tool_name_for_window(window)
        if not tool_name:
            return "Choose a drawing tool"
        key = str(tool_name)
        return TOOL_HINTS.get(key, f"{tool_display_name(key)}: ready")

    def show_active_tool_hint(self, window) -> None:
        status_bar = window.statusBar() if hasattr(window, "statusBar") else None
        if status_bar is None:
            return
        status_bar.showMessage(self.active_tool_hint_text(window))

    def active_sheet_status_text(self, window) -> str:
        canvas_count = self._canvas_count_for_window(window)
        if canvas_count <= 0:
            return "Canvas: None"
        canvas_name = self._active_canvas_name_for_window(window) or "Untitled"
        return f"Canvas: {canvas_name}"

    def current_selection_count(self, window) -> int:
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return 0
        return selection_status_count_for(canvas)


__all__ = ["MainWindowStatusService"]
