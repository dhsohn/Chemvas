from __future__ import annotations

from PyQt6.QtCore import Qt

from chemvas.core.tool_overlay_logic import activate_tool_no_drag
from chemvas.ui.input_view_access import rotate_view_for
from chemvas.ui.tool_base import Tool


class RotateTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("rotate", canvas, context=context)
        self._last_pos = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = event.position()
            return True
        return False

    def on_mouse_move(self, event) -> bool:
        if self._last_pos is None:
            return False
        current_pos = event.position()
        delta_x = current_pos.x() - self._last_pos.x()
        rotate_view_for(self.canvas, delta_x * 0.3)
        self._last_pos = current_pos
        return True

    def on_mouse_release(self, event) -> bool:
        self._last_pos = None
        return False


__all__ = ["RotateTool"]
