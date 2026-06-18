from __future__ import annotations

from ui.canvas_view import CanvasView
from ui.canvas_window_access import restore_canvas_state_for
from ui.main_window_document_dialogs import prompt_sheet_setup
from ui.main_window_canvas_logic import copy_canvas_template_settings
from ui.sheet_setup_access import set_sheet_setup_for, sheet_orientation_for, sheet_size_for


class MainWindowCanvasSheetService:
    def __init__(
        self,
        *,
        tab_ui,
        active_canvas_ui,
        tab_refs_for_window,
        active_canvas_for_window,
        next_canvas_sheet_name_for_window,
        sheet_setup_prompt=prompt_sheet_setup,
    ) -> None:
        self._tab_ui = tab_ui
        self._active_canvas_ui = active_canvas_ui
        self._tab_refs_for_window = tab_refs_for_window
        self._active_canvas_for_window = active_canvas_for_window
        self._next_canvas_sheet_name_for_window = next_canvas_sheet_name_for_window
        self._sheet_setup_prompt = sheet_setup_prompt

    def create_canvas(
        self,
        window,
        *,
        template: CanvasView | None = None,
        sheet_setup: tuple[str, str] | None = None,
    ) -> CanvasView:
        canvas = CanvasView()
        canvas.setFrameStyle(0)
        copy_canvas_template_settings(canvas, template)
        if sheet_setup is not None:
            set_sheet_setup_for(canvas, *sheet_setup)
        return canvas

    def add_canvas_sheet(
        self,
        window,
        *,
        name: str,
        state: dict | None = None,
        select: bool = True,
        template: CanvasView | None = None,
        sheet_setup: tuple[str, str] | None = None,
    ) -> CanvasView:
        canvas = self.create_canvas(window, template=template, sheet_setup=sheet_setup)
        tab_refs = self._tab_refs_for_window(window)
        plus_index = tab_refs.plus_tab_index()
        if plus_index >= 0:
            index = tab_refs.canvas_tabs.insertTab(plus_index, canvas, name)
        else:
            index = tab_refs.canvas_tabs.addTab(canvas, name)
        if state is not None:
            restore_canvas_state_for(canvas, state)
        self._tab_ui.ensure_add_sheet_tab(window)
        if select:
            tab_refs.canvas_tabs.setCurrentIndex(index)
        self._active_canvas_ui.bind_active_canvas(window)
        return canvas

    def open_result_canvas_sheet(
        self,
        window,
        name: str,
        *,
        select: bool = True,
        exact_name: bool = False,
    ) -> tuple[str | None, CanvasView | None]:
        if exact_name and name:
            sheet_name = name
        else:
            sheet_name = self._next_canvas_sheet_name_for_window(window, prefix=name or "Result")
        canvas = self.add_canvas_sheet(
            window,
            name=sheet_name,
            select=select,
            template=self._active_canvas_for_window(window),
        )
        return sheet_name, canvas

    def new_canvas_sheet(self, window) -> CanvasView | None:
        template = self._active_canvas_for_window(window)
        tab_refs = self._tab_refs_for_window(window)
        previous_index = tab_refs.active_canvas_tab_index(template)
        if previous_index >= 0 and tab_refs.canvas_tabs.currentIndex() != previous_index:
            tab_refs.canvas_tabs.setCurrentIndex(previous_index)
        selected = self._sheet_setup_prompt(
            window,
            current_size=sheet_size_for(template),
            current_orientation=sheet_orientation_for(template),
        )
        if selected is None:
            return None
        return self.add_canvas_sheet(
            window,
            name=self._next_canvas_sheet_name_for_window(window),
            select=True,
            template=template,
            sheet_setup=(selected.size, selected.orientation),
        )


__all__ = ["MainWindowCanvasSheetService"]
