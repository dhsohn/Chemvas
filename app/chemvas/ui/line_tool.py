from __future__ import annotations

from typing import override

from PyQt6.QtCore import QPointF, Qt

from chemvas.features.rendering import snapped_line_end
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.endpoint_snap_access import (
    snap_drawing_point_for,
    snap_to_endpoint_for,
    snap_to_grid_for,
)
from chemvas.ui.preview_tools import PreviewDragTool
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_decoration_access import add_arrow_for, preview_arrow_for
from chemvas.ui.scene_decoration_build_access import mark_snapped_points_for

# Shift locks the drag to multiples of this angle so energy-diagram levels and
# connectors come out exactly horizontal, vertical or diagonal.
LINE_ANGLE_STEP_DEGREES = 15.0
# A click on empty canvas places a horizontal level this many bond lengths
# long, starting at the (snapped) press point, in the active line style.
LEVEL_PRESET_BOND_LENGTHS = 2.0


class LineTool(PreviewDragTool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("line", canvas, context=context)
        self._angle_locked = False

    def _line_kind(self) -> str:
        return tool_settings_state_for(self.canvas).active_line_kind

    def _read_angle_lock(self, event) -> None:
        self._angle_locked = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

    def _end_point(self, current_pos: QPointF) -> QPointF:
        click_end = self._click_end_or_none(current_pos)
        if click_end is not None:
            return click_end
        # An existing endpoint is the most specific target, but never the end
        # this drag started from, or a short drag would collapse. Shift is the
        # user's explicit direction, so it outranks the grid, which catches
        # everything else.
        endpoint = snap_to_endpoint_for(self.canvas, current_pos, avoid=self._start_pos)
        if endpoint is not None:
            return endpoint
        if self._angle_locked and self._start_pos is not None:
            x, y = snapped_line_end(
                (self._start_pos.x(), self._start_pos.y()),
                (current_pos.x(), current_pos.y()),
                step_degrees=LINE_ANGLE_STEP_DEGREES,
            )
            return QPointF(x, y)
        return snap_to_grid_for(self.canvas, current_pos)

    @override
    def on_mouse_press(self, event) -> bool:
        handled = super().on_mouse_press(event)
        if handled and self._start_pos is not None:
            self._start_pos = snap_drawing_point_for(self.canvas, self._start_pos)
        return handled

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
        end = self._end_point(current_pos)
        item = preview_arrow_for(self.canvas, self._start_pos, end, self._line_kind())
        mark_snapped_points_for(self.canvas, item, [self._start_pos, end])
        return item

    @override
    def _commit_drag(self, end_pos) -> None:
        end = self._end_point(end_pos)
        if end == self._start_pos:
            if self.context.item_at_scene_pos(end) is not None:
                # A click on an existing object is a selection or a
                # double-click gesture, never a request for a new level.
                return
            length = bond_length_px_for(self.canvas) * LEVEL_PRESET_BOND_LENGTHS
            end = QPointF(self._start_pos.x() + length, self._start_pos.y())
        add_arrow_for(self.canvas, self._start_pos, end, self._line_kind())


__all__ = ["LEVEL_PRESET_BOND_LENGTHS", "LINE_ANGLE_STEP_DEGREES", "LineTool"]
