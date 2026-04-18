from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from core.document_io import write_document
from ui.main_window_canvas_logic import (
    build_workbook_sheet_states,
    canvas_sheet_name_counter,
    clamp_active_sheet_index,
    coerce_active_sheet_index,
    restorable_canvas_sheets,
)


class MainWindowWorkbookDocumentService:
    def clear_canvas_sheets(self, window) -> None:
        previous_state = window._suspend_canvas_tab_reactions
        window._suspend_canvas_tab_reactions = True
        while window.canvas_tabs.count():
            widget = window.canvas_tabs.widget(0)
            window.canvas_tabs.removeTab(0)
            if widget is not None and widget is not window._sheet_add_tab:
                widget.deleteLater()
        window._sheet_add_tab = QWidget()
        window._sheet_tab_bar.set_add_tab_index(-1)
        window._suspend_canvas_tab_reactions = previous_state

    def workbook_state(self, window) -> dict:
        return {
            "active_sheet_index": window._active_canvas_sheet_index(),
            "sheets": build_workbook_sheet_states(
                window._canvas_tab_entries(),
                tab_text_at=window.canvas_tabs.tabText,
            ),
        }

    def restore_single_sheet_document(self, window, state: dict) -> None:
        window._suspend_canvas_tab_reactions = True
        self.clear_canvas_sheets(window)
        window._add_canvas_sheet(name="Sheet 1", state=state, select=True)
        window._canvas_name_counter = canvas_sheet_name_counter(["Sheet 1"])
        window._last_canvas_tab_index = window._active_canvas_tab_index()
        window._suspend_canvas_tab_reactions = False
        window._refresh_active_canvas_ui()

    def restore_workbook_document(self, window, state: dict) -> None:
        window._suspend_canvas_tab_reactions = True
        self.clear_canvas_sheets(window)
        for sheet in restorable_canvas_sheets(
            state.get("sheets", []),
            default_name_factory=window._next_canvas_sheet_name,
        ):
            window._add_canvas_sheet(
                name=sheet.name,
                state=sheet.content,
                select=False,
            )
        if window._canvas_sheet_count() == 0:
            window._add_canvas_sheet(name="Sheet 1", select=True)
        canvas_entries = window._canvas_tab_entries()
        window._canvas_name_counter = canvas_sheet_name_counter(
            [window.canvas_tabs.tabText(tab_index) for tab_index, _ in canvas_entries]
        )
        active_sheet_index = clamp_active_sheet_index(
            coerce_active_sheet_index(state.get("active_sheet_index", 0)),
            len(canvas_entries),
        )
        active_tab_index = canvas_entries[active_sheet_index][0]
        window.canvas_tabs.setCurrentIndex(active_tab_index)
        window._last_canvas_tab_index = active_tab_index
        window._suspend_canvas_tab_reactions = False
        window._refresh_active_canvas_ui()

    def save_document_state(self, window, path: str, *, write_document_fn=write_document) -> None:
        if window._canvas_sheet_count() == 1:
            window.canvas.save_to_file(path)
            return
        write_document_fn(path, self.workbook_state(window), window.WORKBOOK_FILE_VERSION)


__all__ = ["MainWindowWorkbookDocumentService"]
