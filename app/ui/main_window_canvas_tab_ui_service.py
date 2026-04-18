from __future__ import annotations

from PyQt6.QtWidgets import QMenu, QWidget

from ui.canvas_view import CanvasView


class MainWindowCanvasTabUIService:
    def ensure_add_sheet_tab(self, window) -> None:
        plus_index = window._plus_tab_index()
        if plus_index < 0:
            window._sheet_add_tab = QWidget()
            plus_index = window.canvas_tabs.addTab(window._sheet_add_tab, "+")
        self.keep_add_tab_last(window)
        plus_index = window._plus_tab_index()
        window.canvas_tabs.setTabToolTip(plus_index, "New Canvas Sheet")
        window._sheet_tab_bar.set_add_tab_index(plus_index)

    def keep_add_tab_last(self, window) -> None:
        if window._repositioning_add_tab:
            return
        plus_index = window._plus_tab_index()
        last_index = window.canvas_tabs.count() - 1
        if plus_index < 0 or plus_index == last_index:
            return
        window._repositioning_add_tab = True
        try:
            window._sheet_tab_bar.moveTab(plus_index, last_index)
        finally:
            window._repositioning_add_tab = False
        window._sheet_tab_bar.set_add_tab_index(window._plus_tab_index())

    def on_canvas_tab_moved(self, window, from_index: int, to_index: int) -> None:
        del from_index, to_index
        if window._repositioning_add_tab:
            return
        self.keep_add_tab_last(window)

    def can_delete_canvas_sheet(self, window, index: int) -> bool:
        if index < 0:
            return False
        return isinstance(window.canvas_tabs.widget(index), CanvasView) and window._canvas_sheet_count() > 1

    def show_canvas_tab_context_menu(self, window, pos, *, menu_factory=QMenu) -> None:
        index = window._sheet_tab_bar.tabAt(pos)
        if index < 0:
            return
        widget = window.canvas_tabs.widget(index)
        if not isinstance(widget, CanvasView):
            return

        menu = menu_factory(window)
        delete_action = menu.addAction("Delete Sheet")
        delete_action.setEnabled(self.can_delete_canvas_sheet(window, index))
        chosen_action = menu.exec(window._sheet_tab_bar.mapToGlobal(pos))
        if chosen_action is delete_action and delete_action.isEnabled():
            self.delete_canvas_sheet(window, index)

    def delete_canvas_sheet(self, window, index: int) -> None:
        if not self.can_delete_canvas_sheet(window, index):
            return

        widget = window.canvas_tabs.widget(index)
        previous_state = window._suspend_canvas_tab_reactions
        window._suspend_canvas_tab_reactions = True
        window.canvas_tabs.removeTab(index)
        self.ensure_add_sheet_tab(window)

        active_index = window.canvas_tabs.currentIndex()
        if not isinstance(window.canvas_tabs.currentWidget(), CanvasView):
            active_index = min(index, max(0, window._plus_tab_index() - 1))
            window.canvas_tabs.setCurrentIndex(active_index)
        window._last_canvas_tab_index = active_index
        window._suspend_canvas_tab_reactions = previous_state

        widget.deleteLater()
        window._refresh_active_canvas_ui()

    def new_canvas_sheet(self, window) -> None:
        window._canvas_sheet_service.new_canvas_sheet(window)


__all__ = ["MainWindowCanvasTabUIService"]
