from __future__ import annotations

from ui.canvas_view import CanvasView
from ui.main_window_canvas_logic import copy_canvas_template_settings


class MainWindowCanvasSheetService:
    def create_canvas(self, window, *, template: CanvasView | None = None) -> CanvasView:
        canvas = CanvasView()
        canvas.setFrameStyle(0)
        copy_canvas_template_settings(canvas, template)
        return canvas

    def add_canvas_sheet(
        self,
        window,
        *,
        name: str,
        state: dict | None = None,
        select: bool = True,
        template: CanvasView | None = None,
    ) -> CanvasView:
        canvas = self.create_canvas(window, template=template)
        plus_index = window._plus_tab_index()
        if plus_index >= 0:
            index = window.canvas_tabs.insertTab(plus_index, canvas, name)
        else:
            index = window.canvas_tabs.addTab(canvas, name)
        if state is not None:
            canvas.restore_state(state)
        window._ensure_add_sheet_tab()
        if select:
            window.canvas_tabs.setCurrentIndex(index)
        window._bind_active_canvas()
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
            sheet_name = window._next_canvas_sheet_name(prefix=name or "Result")
        canvas = self.add_canvas_sheet(
            window,
            name=sheet_name,
            select=select,
            template=window._active_canvas_or_none(),
        )
        return sheet_name, canvas

    def new_canvas_sheet(self, window) -> CanvasView:
        return self.add_canvas_sheet(
            window,
            name=window._next_canvas_sheet_name(),
            select=True,
            template=window._active_canvas_or_none(),
        )


__all__ = ["MainWindowCanvasSheetService"]
