from __future__ import annotations

from typing import override

from PyQt6.QtCore import QPointF, Qt

from chemvas.features.rendering import snapped_line_end
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.preview_tools import PreviewDragTool
from chemvas.ui.scene_decoration_access import add_arrow_for, preview_arrow_for

# Shift locks the drag to multiples of this angle so energy-diagram levels and
# connectors come out exactly horizontal, vertical or diagonal.
LINE_ANGLE_STEP_DEGREES = 15.0


class LineTool(PreviewDragTool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("line", canvas, context=context)
        self._angle_locked = False

    def _line_kind(self) -> str:
        return tool_settings_state_for(self.canvas).active_line_kind

    def _read_angle_lock(self, event) -> None:
        self._angle_locked = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

    def _end_point(self, current_pos: QPointF) -> QPointF:
        if not self._angle_locked or self._start_pos is None:
            return current_pos
        x, y = snapped_line_end(
            (self._start_pos.x(), self._start_pos.y()),
            (current_pos.x(), current_pos.y()),
            step_degrees=LINE_ANGLE_STEP_DEGREES,
        )
        return QPointF(x, y)

    @override
    def on_mouse_move(self, event) -> bool:
        self._read_angle_lock(event)
        return super().on_mouse_move(event)

    @override
    def on_mouse_release(self, event) -> bool:
        self._read_angle_lock(event)
        return super().on_mouse_release(event)

    @override
    def _build_preview(self, current_pos):
        return preview_arrow_for(
            self.canvas,
            self._start_pos,
            self._end_point(current_pos),
            self._line_kind(),
        )

    @override
    def _commit_drag(self, end_pos) -> None:
        end = self._end_point(end_pos)
        if end == self._start_pos:
            # A click without a drag would add an invisible zero-length line.
            return
        add_arrow_for(self.canvas, self._start_pos, end, self._line_kind())


__all__ = ["LINE_ANGLE_STEP_DEGREES", "LineTool"]
