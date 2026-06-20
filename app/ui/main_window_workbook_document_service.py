from __future__ import annotations

from core.document_io import write_document

from ui.main_window_canvas_logic import (
    build_workbook_sheet_states,
    restorable_canvas_sheets,
)


class MainWindowWorkbookDocumentService:
    def __init__(
        self,
        *,
        active_canvas_ui,
        canvas_sheet,
        save_active_canvas_to_file_for_window,
        tab_refs_for_window,
        active_canvas_sheet_index_for_window,
        active_canvas_tab_index_for_window,
        canvas_sheet_count_for_window,
        reset_canvas_name_counter_for_window,
        tab_reactions_suspended_for_window,
        set_tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window,
    ) -> None:
        self._active_canvas_ui = active_canvas_ui
        self._canvas_sheet = canvas_sheet
        self._save_active_canvas_to_file_for_window = save_active_canvas_to_file_for_window
        self._tab_refs_for_window = tab_refs_for_window
        self._active_canvas_sheet_index_for_window = active_canvas_sheet_index_for_window
        self._active_canvas_tab_index_for_window = active_canvas_tab_index_for_window
        self._canvas_sheet_count_for_window = canvas_sheet_count_for_window
        self._reset_canvas_name_counter_for_window = reset_canvas_name_counter_for_window
        self._tab_reactions_suspended_for_window = tab_reactions_suspended_for_window
        self._set_tab_reactions_suspended_for_window = set_tab_reactions_suspended_for_window
        self._set_last_canvas_tab_index_for_window = set_last_canvas_tab_index_for_window

    def clear_canvas_sheets(self, window) -> None:
        previous_state = self._tab_reactions_suspended_for_window(window)
        self._set_tab_reactions_suspended_for_window(window, True)
        tab_refs = self._tab_refs_for_window(window)
        while tab_refs.canvas_tabs.count():
            widget = tab_refs.canvas_tabs.widget(0)
            tab_refs.canvas_tabs.removeTab(0)
            if widget is not None and widget is not tab_refs.sheet_add_tab:
                widget.deleteLater()
        tab_refs.recreate_sheet_add_tab(window)
        tab_refs.set_sheet_add_tab_index(-1)
        self._set_tab_reactions_suspended_for_window(window, previous_state)

    def workbook_state(self, window) -> dict:
        tab_refs = self._tab_refs_for_window(window)
        return {
            "active_sheet_index": self._active_canvas_sheet_index_for_window(window),
            "sheets": build_workbook_sheet_states(
                tab_refs.canvas_tab_entries(),
                tab_text_at=tab_refs.canvas_tabs.tabText,
            ),
        }

    def restore_single_sheet_document(self, window, state: dict) -> None:
        previous = self._tab_reactions_suspended_for_window(window)
        self._set_tab_reactions_suspended_for_window(window, True)
        try:
            self.clear_canvas_sheets(window)
            self._canvas_sheet.add_canvas_sheet(window, name="Sheet 1", state=state, select=True)
            self._reset_canvas_name_counter_for_window(window, ["Sheet 1"])
            self._set_last_canvas_tab_index_for_window(window, self._active_canvas_tab_index_for_window(window))
        finally:
            self._set_tab_reactions_suspended_for_window(window, previous)
        self._active_canvas_ui.refresh_active_canvas_ui(window)

    def restore_workbook_document(self, window, state: dict) -> None:
        sheets = restorable_canvas_sheets(state["sheets"])
        active_sheet_index = state["active_sheet_index"]
        if (
            type(active_sheet_index) is not int
            or active_sheet_index < 0
            or active_sheet_index >= len(sheets)
        ):
            raise ValueError("Invalid Chemvas file.")

        previous = self._tab_reactions_suspended_for_window(window)
        self._set_tab_reactions_suspended_for_window(window, True)
        try:
            self.clear_canvas_sheets(window)
            for sheet in sheets:
                self._canvas_sheet.add_canvas_sheet(
                    window,
                    name=sheet.name,
                    state=sheet.content,
                    select=False,
                )
            tab_refs = self._tab_refs_for_window(window)
            canvas_entries = tab_refs.canvas_tab_entries()
            self._reset_canvas_name_counter_for_window(
                window,
                [tab_refs.canvas_tabs.tabText(tab_index) for tab_index, _ in canvas_entries],
            )
            active_tab_index = canvas_entries[active_sheet_index][0]
            tab_refs.canvas_tabs.setCurrentIndex(active_tab_index)
            self._set_last_canvas_tab_index_for_window(window, active_tab_index)
        finally:
            self._set_tab_reactions_suspended_for_window(window, previous)
        self._active_canvas_ui.refresh_active_canvas_ui(window)

    def save_document_state(self, window, path: str, *, write_document_fn=write_document) -> None:
        if self._canvas_sheet_count_for_window(window) == 1:
            self._save_active_canvas_to_file_for_window(window, path)
            return
        write_document_fn(path, self.workbook_state(window), window.WORKBOOK_FILE_VERSION)

__all__ = ["MainWindowWorkbookDocumentService"]
