from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor


class MainWindowToolRoutingService:
    def __init__(
        self,
        *,
        tool_mode_controller_for_window,
        color_mutation_service_for_window,
        color_tool_for_window,
        selected_scene_items_for_window,
        tool_state_service,
        context_page_state_service,
    ) -> None:
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._color_mutation_service_for_window = color_mutation_service_for_window
        self._color_tool_for_window = color_tool_for_window
        self._selected_scene_items_for_window = selected_scene_items_for_window
        self._tool_state = tool_state_service
        self._context_page_state = context_page_state_service

    def _selected_scene_items(self, window):
        return self._selected_scene_items_for_window(window, excluded_kinds=set())

    def apply_color_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)
        tool = self._color_tool_for_window(window)
        set_color = getattr(tool, "set_color", None)
        if callable(set_color):
            set_color(color)

        def apply_color() -> None:
            self._tool_mode_controller_for_window(window).set_tool("color")
            color_service = self._color_mutation_service_for_window(window)
            items = [
                item
                for item in self._selected_scene_items(window)
                if item.data(0) in {"bond", "atom", "ring", "note", "shape"}
            ]
            color_service.apply_color_to_items(items, color)

        qtimer.singleShot(0, apply_color)

    def apply_ring_fill_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)

        def apply_fill() -> None:
            color_service = self._color_mutation_service_for_window(window)
            items = [
                item
                for item in self._selected_scene_items(window)
                if item.data(0) == "ring"
            ]
            color_service.apply_ring_fill_color_to_items(items, color)

        qtimer.singleShot(0, apply_fill)


__all__ = ["MainWindowToolRoutingService"]
