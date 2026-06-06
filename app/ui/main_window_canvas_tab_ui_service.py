from __future__ import annotations

from PyQt6.QtWidgets import QMenu

from ui.canvas_view import CanvasView


class MainWindowCanvasTabUIService:
    def __init__(
        self,
        *,
        active_canvas_ui,
        tab_refs_for_window,
        repositioning_add_tab_for_window,
        set_repositioning_add_tab_for_window,
        tab_reactions_suspended_for_window,
        set_tab_reactions_suspended_for_window,
        set_last_canvas_tab_index_for_window,
    ) -> None:
        self._active_canvas_ui = active_canvas_ui
        self._tab_refs_for_window = tab_refs_for_window
        self._repositioning_add_tab_for_window = repositioning_add_tab_for_window
        self._set_repositioning_add_tab_for_window = set_repositioning_add_tab_for_window
        self._tab_reactions_suspended_for_window = tab_reactions_suspended_for_window
        self._set_tab_reactions_suspended_for_window = set_tab_reactions_suspended_for_window
        self._set_last_canvas_tab_index_for_window = set_last_canvas_tab_index_for_window

    def ensure_add_sheet_tab(self, window) -> None:
        tab_refs = self._tab_refs_for_window(window)
        plus_index = tab_refs.plus_tab_index()
        if plus_index < 0:
            plus_index = tab_refs.canvas_tabs.addTab(tab_refs.recreate_sheet_add_tab(window), "+")
        self.keep_add_tab_last(window)
        plus_index = tab_refs.plus_tab_index()
        tab_refs.canvas_tabs.setTabToolTip(plus_index, "New Canvas Sheet")
        tab_refs.set_sheet_add_tab_index(plus_index)

    def keep_add_tab_last(self, window) -> None:
        if self._repositioning_add_tab_for_window(window):
            return
        tab_refs = self._tab_refs_for_window(window)
        plus_index = tab_refs.plus_tab_index()
        last_index = tab_refs.canvas_tabs.count() - 1
        if plus_index < 0 or plus_index == last_index:
            return
        self._set_repositioning_add_tab_for_window(window, True)
        try:
            tab_refs.move_sheet_tab(plus_index, last_index)
        finally:
            self._set_repositioning_add_tab_for_window(window, False)
        tab_refs.set_sheet_add_tab_index(tab_refs.plus_tab_index())

    def on_canvas_tab_moved(self, window, from_index: int, to_index: int) -> None:
        del from_index, to_index
        if self._repositioning_add_tab_for_window(window):
            return
        self.keep_add_tab_last(window)

    def can_delete_canvas_sheet(self, window, index: int) -> bool:
        if index < 0:
            return False
        tab_refs = self._tab_refs_for_window(window)
        return isinstance(tab_refs.canvas_tabs.widget(index), CanvasView) and tab_refs.canvas_sheet_count() > 1

    def show_canvas_tab_context_menu(self, window, pos, *, menu_factory=QMenu) -> None:
        tab_refs = self._tab_refs_for_window(window)
        index = tab_refs.sheet_tab_at(pos)
        if index < 0:
            return
        widget = tab_refs.canvas_tabs.widget(index)
        if not isinstance(widget, CanvasView):
            return

        menu = menu_factory(window)
        delete_action = menu.addAction("Delete Sheet")
        delete_action.setEnabled(self.can_delete_canvas_sheet(window, index))
        chosen_action = menu.exec(tab_refs.sheet_tab_global_pos(pos))
        if chosen_action is delete_action and delete_action.isEnabled():
            self.delete_canvas_sheet(window, index)

    def delete_canvas_sheet(self, window, index: int) -> None:
        if not self.can_delete_canvas_sheet(window, index):
            return

        tab_refs = self._tab_refs_for_window(window)
        widget = tab_refs.canvas_tabs.widget(index)
        previous_state = self._tab_reactions_suspended_for_window(window)
        self._set_tab_reactions_suspended_for_window(window, True)
        tab_refs.canvas_tabs.removeTab(index)
        self.ensure_add_sheet_tab(window)

        active_index = tab_refs.canvas_tabs.currentIndex()
        if not isinstance(tab_refs.canvas_tabs.currentWidget(), CanvasView):
            active_index = min(index, max(0, tab_refs.plus_tab_index() - 1))
            tab_refs.canvas_tabs.setCurrentIndex(active_index)
        self._set_last_canvas_tab_index_for_window(window, active_index)
        self._set_tab_reactions_suspended_for_window(window, previous_state)

        widget.deleteLater()
        self._active_canvas_ui.refresh_active_canvas_ui(window)


__all__ = ["MainWindowCanvasTabUIService"]
