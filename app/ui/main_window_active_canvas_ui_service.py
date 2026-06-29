from __future__ import annotations

from PyQt6.QtCore import QTimer

from ui.canvas_view import CanvasView
from ui.main_window_canvas_logic import bind_active_canvas_callbacks
from ui.rdkit_adapter_access import rdkit_adapter_for
from ui.selection_info_access import emit_selection_info_for


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
        tab_refs_for_window,
        preview_for_window,
        atom_input_for_window,
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
        self._tab_refs_for_window = tab_refs_for_window
        self._preview_for_window = preview_for_window
        self._atom_input_for_window = atom_input_for_window
        self._tab_reactions_suspended_for_window = tab_reactions_suspended_for_window
        self._set_last_canvas_tab_index_for_window = set_last_canvas_tab_index_for_window

    def bind_active_canvas(self, window) -> None:
        active_canvas = self._active_canvas_for_window(window)
        self._preview_for_window(window).set_rdkit_adapter(rdkit_adapter_for(active_canvas))
        bind_active_canvas_callbacks(
            self._all_canvases_for_window(window),
            active_canvas,
            selection_info_callback=lambda _formula, _mw: self.handle_selection_info(window),
            tool_change_callback=lambda: self._context_page_state.sync_tool_actions_from_canvas(window),
            zoom_callback=self._status.update_zoom_label,
            history_change_callback=lambda: self._on_history_change(window),
            error_callback=lambda message: self._status.show_error_message(window, message, timeout=6000),
        )

    def _on_history_change(self, window) -> None:
        self._action_availability.update_action_availability(window)
        # Undo/redo can change the bond length without re-showing the bond page,
        # so keep its spin box in sync to avoid writing a stale value later.
        self._context_bar.reflect_bond_length(window)

    def handle_selection_info(self, window) -> None:
        try:
            canvas = self._active_canvas_for_window(window)
            self._preview_for_window(window).refresh_selected_from_canvas(canvas)
            self._status.update_selection_status_label(window)
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
        self._refresh_selection_derived_ui(window)

    def _refresh_selection_derived_ui(self, window) -> None:
        # Re-emit the active canvas's selection info so the molecule info panel,
        # selection status label and action availability all refresh
        # through the same path as a live selection change. Without this the
        # preview could keep the previous canvas's structure when the active
        # canvas switches without a selection event firing. Defer to the next
        # event-loop turn so switching tabs stays responsive.
        QTimer.singleShot(0, lambda: self._emit_active_selection_info(window))

    def _emit_active_selection_info(self, window) -> None:
        try:
            canvas = self._active_canvas_for_window(window)
        except RuntimeError:
            return
        emit_selection_info_for(canvas)

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
        if not isinstance(widget, CanvasView):
            return
        self._set_last_canvas_tab_index_for_window(window, index)
        self.refresh_active_canvas_ui(window)


__all__ = ["MainWindowActiveCanvasUIService"]
