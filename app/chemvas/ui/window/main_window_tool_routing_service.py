from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.features.session import is_quit_pending
from chemvas.ui.window.main_window_ports import (
    color_mutation_service_for_window,
    color_tool_for_window,
    selected_scene_items_for_window,
)


class MainWindowToolRoutingService:
    def __init__(
        self,
        *,
        tool_state_service,
    ) -> None:
        self._tool_state = tool_state_service

    def _selected_scene_items(self, window):
        return selected_scene_items_for_window(window, excluded_kinds=set())

    def apply_color_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)
        tool = color_tool_for_window(window)
        set_color = getattr(tool, "set_color", None)
        if callable(set_color):
            set_color(color)

        def apply_color() -> None:
            if sip.isdeleted(window) or window.is_closing or is_quit_pending():
                return
            if color_tool_for_window(window) is not tool:
                window.statusBar().showMessage(
                    "Color not applied: active canvas changed; choose a swatch again.",
                    6000,
                )
                return
            self._tool_state.set_tool_with_status(window, "color")
            color_service = color_mutation_service_for_window(window)
            items = [
                item
                for item in self._selected_scene_items(window)
                if item.data(0)
                in {"bond", "atom", "ring", "note", "shape", "mark", "ts_bracket"}
                | VALID_ARROW_KINDS
            ]
            color_service.apply_color_to_items(items, color)

        qtimer.singleShot(0, apply_color)

    def apply_ring_fill_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)
        color_service = color_mutation_service_for_window(window)

        def apply_fill() -> None:
            if sip.isdeleted(window) or window.is_closing or is_quit_pending():
                return
            if color_mutation_service_for_window(window) is not color_service:
                window.statusBar().showMessage(
                    "Ring fill not applied: active canvas changed; choose a swatch again.",
                    6000,
                )
                return
            items = [
                item
                for item in self._selected_scene_items(window)
                if item.data(0) in {"ring", "atom", "bond"}
            ]
            color_service.apply_ring_fill_color_to_items(items, color)

        qtimer.singleShot(0, apply_fill)


__all__ = ["MainWindowToolRoutingService"]
