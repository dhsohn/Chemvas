from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.canvas.sheet_setup_access import refresh_canvas_scroll_range_for
from chemvas.ui.selection.selection_info_access import emit_selection_info_for
from chemvas.ui.window.main_window_canvas_logic import bind_active_canvas_callbacks
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    current_zoom_percent_for_window,
    tool_mode_controller_for_window,
)

if TYPE_CHECKING:
    from chemvas.ui.window.main_window_like import MainWindowLike


class MainWindowActiveCanvasUIService:
    def __init__(
        self,
        *,
        status_service,
        context_bar_service,
        action_availability_service,
        tool_state_service,
        refresh_document_chrome_for_window,
    ) -> None:
        self._status = status_service
        self._context_bar = context_bar_service
        self._action_availability = action_availability_service
        self._tool_state = tool_state_service
        self._refresh_document_chrome_for_window = refresh_document_chrome_for_window

    def bind_active_canvas(self, window: MainWindowLike) -> None:
        active_canvas = active_canvas_for_window(window)
        window.preview_3d.set_rdkit_adapter(active_canvas.rdkit)
        bind_active_canvas_callbacks(
            window.tab_references.all_canvases(),
            active_canvas,
            selection_info_callback=lambda _formula, _mw: self.handle_selection_info(
                window
            ),
            tool_change_callback=lambda: self._tool_state.sync_tool_actions_from_canvas(
                window
            ),
            zoom_callback=self._status.update_zoom_label,
            history_change_callback=lambda: self._on_history_change(window),
            document_change_callback=lambda **kwargs: (
                self._refresh_document_chrome_for_window(window, **kwargs)
            ),
            error_callback=lambda message: self._status.show_error_message(
                window, message, timeout=6000
            ),
        )

    def _on_history_change(self, window: MainWindowLike) -> None:
        active_canvas_for_window(
            window
        ).runtime_state.document_metadata_state.invalidate_note_chrome()
        self._action_availability.update_action_availability(window)
        # Undo/redo can change the bond length without re-showing the bond page,
        # so keep its spin box in sync to avoid writing a stale value later.
        self._context_bar.reflect_bond_length(window)
        # Exact rollback publishes here after restoring document settings. Keep
        # annotation controls in sync even if their earlier tool callback failed.
        self._context_bar.refresh_window(window)
        # Every edit can flip the document's saved/unsaved state, so refresh the
        # tab's unsaved marker (and window-modified hint) live.
        self._refresh_document_chrome_for_window(window)
        # History publishes after a gesture commits (or is restored on failure),
        # not during pointer movement. Recompute from persistent content only.
        refresh_canvas_scroll_range_for(active_canvas_for_window(window))

    def handle_selection_info(self, window: MainWindowLike) -> None:
        try:
            canvas = active_canvas_for_window(window)
            window.preview_3d.refresh_selected_from_canvas(canvas)
            self._status.update_selection_status_label(window)
            self._action_availability.update_action_availability(window)
        except RuntimeError:
            return

    def current_zoom_percent(self, window: MainWindowLike) -> int:
        return current_zoom_percent_for_window(window)

    def refresh_active_canvas_ui(self, window: MainWindowLike) -> None:
        self.bind_active_canvas(window)
        # Inactive canvases have no history callback; catch up on activation.
        refresh_canvas_scroll_range_for(active_canvas_for_window(window))
        self._action_availability.sync_grid_snap_action(window)
        atom_input = window.ui_references.atom_input
        if atom_input is not None:
            atom_input.blockSignals(True)
            atom_input.setText(
                tool_mode_controller_for_window(window).get_atom_symbol()
            )
            atom_input.blockSignals(False)
        if self._status.has_zoom_label():
            self._status.update_zoom_label(self.current_zoom_percent(window))
        self._tool_state.sync_tool_actions_from_canvas(window)
        self._refresh_selection_derived_ui(window)

    def _refresh_selection_derived_ui(self, window: MainWindowLike) -> None:
        # Re-emit the active canvas's selection info so the molecule info panel,
        # selection status label and action availability all refresh
        # through the same path as a live selection change. Without this the
        # preview could keep the previous canvas's structure when the active
        # canvas switches without a selection event firing. Defer to the next
        # event-loop turn so switching tabs stays responsive.
        QTimer.singleShot(0, lambda: self._emit_active_selection_info(window))

    def _emit_active_selection_info(self, window: MainWindowLike) -> None:
        try:
            canvas = active_canvas_for_window(window)
        except RuntimeError:
            return
        emit_selection_info_for(canvas)

    def on_canvas_tab_changed(self, window: MainWindowLike, index: int) -> None:
        self._on_canvas_tab_changed(window, index)
        self._status.refresh_status_context(window, update_zoom=False)

    def _on_canvas_tab_changed(self, window: MainWindowLike, index: int) -> None:
        if index < 0:
            return
        tab_refs = window.tab_references
        widget = tab_refs.canvas_tabs.widget(index)
        if not isinstance(widget, CanvasView):
            return
        window.runtime_state.last_canvas_tab_index = index
        self.refresh_active_canvas_ui(window)


__all__ = ["MainWindowActiveCanvasUIService"]
