from __future__ import annotations


class MainWindowCanvasTabUIService:
    def __init__(
        self,
        *,
        close_canvas_tab_for_window,
    ) -> None:
        self._close_canvas_tab_for_window = close_canvas_tab_for_window

    def close_canvas_tab(self, window, index: int) -> None:
        self._close_canvas_tab_for_window(window, index)


__all__ = ["MainWindowCanvasTabUIService"]
