from __future__ import annotations

from ui.canvas_view import CanvasView
from ui.main_window_canvas_logic import bind_active_canvas_callbacks
from ui.rdkit_adapter_access import rdkit_adapter_for


class MainWindowActiveCanvasUIService:
    def __init__(
        self,
        *,
        tool_mode_controller_for_window,
        active_canvas_for_window,
        all_canvases_for_window,
        current_zoom_percent_for_window,
        status_service,
        context_bar_service,
        action_availability_service,
        context_page_state_service,
        new_canvas_sheet_for_window,
        tab_refs_for_window,
        preview_for_window,
        atom_input_for_window,
        sheet_add_tab_for_window,
        tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window,
    ) -> None:
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._active_canvas_for_window = active_canvas_for_window
        self._all_canvases_for_window = all_canvases_for_window
        self._current_zoom_percent_for_window = current_zoom_percent_for_window
        self._status = status_service
        self._context_bar = context_bar_service
        self._action_availability = action_availability_service
        self._context_page_state = context_page_state_service
        self._new_canvas_sheet_for_window = new_canvas_sheet_for_window
        self._tab_refs_for_window = tab_refs_for_window
        self._preview_for_window = preview_for_window
        self._atom_input_for_window = atom_input_for_window
        self._sheet_add_tab_for_window = sheet_add_tab_for_window
        self._tab_reactions_suspended_for_window = tab_reactions_suspended_for_window
        self._set_last_canvas_tab_index_for_window = set_last_canvas_tab_index_for_window

    def bind_active_canvas(self, window) -> None:
        active_canvas = self._active_canvas_for_window(window)
        self._preview_for_window(window).set_rdkit_adapter(rdkit_adapter_for(active_canvas))
        bind_active_canvas_callbacks(
            self._all_canvases_for_window(window),
            active_canvas,
            selection_info_callback=lambda formula, mw: self.handle_selection_info(window, formula, mw),
            tool_change_callback=lambda: self._context_page_state.sync_tool_actions_from_canvas(window),
            zoom_callback=self._status.update_zoom_label,
            history_change_callback=lambda: self._action_availability.update_action_availability(window),
            error_callback=lambda message: self._status.show_error_message(window, message, timeout=6000),
        )

    def handle_selection_info(self, window, formula: str, mw: str) -> None:
        try:
            canvas = self._active_canvas_for_window(window)
            self._preview_for_window(window).refresh_selected_from_canvas(canvas)
            self._status.update_selection_status_label(window)
            self._status.update_chemical_status_label(formula, mw)
            self._action_availability.update_action_availability(window)
        except RuntimeError:
            return

    def current_zoom_percent(self, window) -> int:
        return self._current_zoom_percent_for_window(window)

    def refresh_active_canvas_ui(self, window) -> None:
        self.bind_active_canvas(window)
        atom_input = self._atom_input_for_window(window)
        if atom_input is not None:
            atom_input.blockSignals(True)
            atom_input.setText(self._tool_mode_controller_for_window(window).get_atom_symbol())
            atom_input.blockSignals(False)
        if self._status.has_zoom_label():
            self._status.update_zoom_label(self.current_zoom_percent(window))
        self._context_page_state.sync_tool_actions_from_canvas(window)
        self._action_availability.update_action_availability(window)
        self._preview_for_window(window).refresh_selected_from_canvas(self._active_canvas_for_window(window))

    def on_canvas_tab_changed(self, window, index: int) -> None:
        self._on_canvas_tab_changed(window, index)
        self._status.refresh_status_context(window, update_zoom=False)
        self._context_bar.refresh_window(window)

    def _on_canvas_tab_changed(self, window, index: int) -> None:
        if self._tab_reactions_suspended_for_window(window):
            return
        if index < 0:
            return
        tab_refs = self._tab_refs_for_window(window)
        widget = tab_refs.canvas_tabs.widget(index)
        if widget is self._sheet_add_tab_for_window(window):
            self._new_canvas_sheet_for_window(window)
            return
        if not isinstance(widget, CanvasView):
            return
        self._set_last_canvas_tab_index_for_window(window, index)
        self.refresh_active_canvas_ui(window)


__all__ = ["MainWindowActiveCanvasUIService"]
