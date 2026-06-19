from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel

from ui.main_window_toolbar_logic import tool_display_name
from ui.selection_collection_access import selection_status_count_for


class MainWindowStatusService:
    def __init__(
        self,
        *,
        active_tool_name_for_window,
        current_zoom_percent_for_window,
        active_canvas_or_none_for_window,
        canvas_sheet_count_for_window,
        active_canvas_sheet_name_for_window,
        active_canvas_sheet_index_for_window,
        context_bar_page_override_for_window,
    ) -> None:
        self._active_tool_name_for_window = active_tool_name_for_window
        self._current_zoom_percent_for_window = current_zoom_percent_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._canvas_sheet_count_for_window = canvas_sheet_count_for_window
        self._active_canvas_sheet_name_for_window = active_canvas_sheet_name_for_window
        self._active_canvas_sheet_index_for_window = active_canvas_sheet_index_for_window
        self._context_bar_page_override_for_window = context_bar_page_override_for_window
        self.tool_label: QLabel | None = None
        self.sheet_label: QLabel | None = None
        self.selection_label: QLabel | None = None
        self.chemical_label: QLabel | None = None
        self.zoom_caption: QLabel | None = None
        self.zoom_label: QLabel | None = None

    def init_status_bar(self, window) -> None:
        self.tool_label = QLabel()
        self.sheet_label = QLabel()
        self.selection_label = QLabel()
        self.chemical_label = QLabel()
        self.zoom_caption = QLabel("Zoom")
        self.zoom_label = QLabel("100%")

        for label in (
            self.tool_label,
            self.sheet_label,
            self.selection_label,
            self.chemical_label,
            self.zoom_caption,
        ):
            label.setObjectName("statusContextLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.zoom_label.setObjectName("statusZoomLabel")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        window.statusBar().addPermanentWidget(self.tool_label)
        window.statusBar().addPermanentWidget(self.sheet_label)
        window.statusBar().addPermanentWidget(self.selection_label)
        window.statusBar().addPermanentWidget(self.chemical_label)
        window.statusBar().addPermanentWidget(self.zoom_caption)
        window.statusBar().addPermanentWidget(self.zoom_label)
        self.refresh_status_context(window)
        self.update_chemical_status_label("", "")
        window.statusBar().showMessage("Ready")

    def refresh_status_context(self, window, *, update_zoom: bool = True) -> None:
        self.update_tool_status_label(window)
        self.update_sheet_status_label(window)
        self.update_selection_status_label(window)
        if update_zoom:
            self.update_zoom_label(self._current_zoom_percent_for_window(window))

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
        if selection_count == 0:
            self.update_chemical_status_label("", "")

    def update_chemical_status_label(self, formula: str, mw: str) -> None:
        if self.chemical_label is None:
            return
        text = self.chemical_status_text(formula, mw)
        self.chemical_label.setText(text)
        self.chemical_label.setVisible(bool(text))
        self.chemical_label.setToolTip(text)
        self.chemical_label.setStatusTip(text)

    def update_zoom_label(self, zoom_percent: int) -> None:
        if self.zoom_label is None:
            return
        self.zoom_label.setText(f"{zoom_percent}%")
        self.zoom_label.setToolTip(f"Zoom: {zoom_percent}%")
        self.zoom_label.setStatusTip(f"Zoom: {zoom_percent}%")

    def show_error_message(self, window, message: str, *, timeout: int, qtimer=QTimer) -> None:
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
            "selection": self.selection_label.text() if self.selection_label is not None else "",
            "chemical": self.chemical_label.text() if self.chemical_label is not None else "",
            "zoom_caption": self.zoom_caption.text() if self.zoom_caption is not None else "",
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

    def active_sheet_status_text(self, window) -> str:
        sheet_count = self._canvas_sheet_count_for_window(window)
        if sheet_count <= 0:
            return "Sheet: None"
        sheet_name = self._active_canvas_sheet_name_for_window(window) or "Untitled"
        sheet_index = self._active_canvas_sheet_index_for_window(window) + 1
        return f"Sheet: {sheet_name} ({sheet_index}/{sheet_count})"

    def chemical_status_text(self, formula: str, mw: str) -> str:
        parts: list[str] = []
        if formula:
            parts.append(f"Formula: {formula}")
        if mw:
            parts.append(f"MW: {mw}")
        return "   ".join(parts)

    def current_selection_count(self, window) -> int:
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return 0
        return selection_status_count_for(canvas)


__all__ = ["MainWindowStatusService"]
