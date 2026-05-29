from __future__ import annotations

from ui.canvas_view import CanvasView
from ui.main_window_canvas_logic import bind_active_canvas_callbacks


class MainWindowActiveCanvasUIService:
    def bind_active_canvas(self, window) -> None:
        active_canvas = window.canvas
        window.preview_3d._rdkit = active_canvas.rdkit
        bind_active_canvas_callbacks(
            window._all_canvases(),
            active_canvas,
            selection_info_callback=window._handle_selection_info,
            tool_change_callback=window._sync_tool_actions_from_canvas,
            zoom_callback=window._update_zoom_label,
            history_change_callback=window._update_action_availability,
            error_callback=getattr(window, "_show_error_message", None),
        )

    def handle_selection_info(self, window, _formula: str, _mw: str) -> None:
        window.preview_3d.refresh_from_canvas(window.canvas)

    def current_zoom_percent(self, window) -> int:
        transform = window.canvas.transform()
        return max(1, int(round(transform.m11() * 100)))

    def refresh_active_canvas_ui(self, window) -> None:
        self.bind_active_canvas(window)
        if window._atom_input is not None:
            window._atom_input.blockSignals(True)
            window._atom_input.setText(window.canvas.get_atom_symbol())
            window._atom_input.blockSignals(False)
        if hasattr(window, "_zoom_label"):
            window._update_zoom_label(self.current_zoom_percent(window))
        window._sync_tool_actions_from_canvas()
        window._update_action_availability()
        window.preview_3d.refresh_from_canvas(window.canvas)

    def on_canvas_tab_changed(self, window, index: int) -> None:
        if window._suspend_canvas_tab_reactions:
            return
        if index < 0:
            return
        widget = window.canvas_tabs.widget(index)
        if widget is window._sheet_add_tab:
            window._new_canvas_sheet()
            return
        if not isinstance(widget, CanvasView):
            return
        window._last_canvas_tab_index = index
        self.refresh_active_canvas_ui(window)


__all__ = ["MainWindowActiveCanvasUIService"]
