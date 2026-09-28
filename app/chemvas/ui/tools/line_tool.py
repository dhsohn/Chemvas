from __future__ import annotations

from typing import override

from PyQt6.QtCore import QPointF, Qt

from chemvas.features.rendering import (
    LEVEL_PRESET_BOND_LENGTHS,
    LINE_ANGLE_STEP_DEGREES,
    line_click_endpoint,
)
from chemvas.ui.scene.scene_decoration_build_access import mark_snapped_points_for
from chemvas.ui.tools.endpoint_snap_access import (
    snap_drawing_point_for,
)
from chemvas.ui.tools.preview_tools import PreviewDragTool


class LineTool(PreviewDragTool):
    snap_start_point = True

    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("line", canvas, context=context)
        self._angle_locked = False

    def _line_kind(self) -> str:
        return self.canvas.runtime_state.tool_settings_state.active_line_kind

    def _read_angle_lock(self, event) -> None:
        self._angle_locked = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

    def _end_point(self, current_pos: QPointF) -> QPointF:
        click_end = self._click_end_or_none(current_pos)
        if click_end is not None:
            return click_end
        return snap_drawing_point_for(
            self.canvas,
            current_pos,
            avoid=self._start_pos,
            angle_step=LINE_ANGLE_STEP_DEGREES if self._angle_locked else None,
        )

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
        item = self.canvas.services.arrow_build_service.preview_arrow(
            self._start_pos, end, self._line_kind()
        )
        mark_snapped_points_for(self.canvas, item, [self._start_pos, end])
        return item

    @override
    def _commit_drag(self, end_pos) -> None:
        end = self._end_point(end_pos)
        if end == self._start_pos:
            point = line_click_endpoint(
                (self._start_pos.x(), self._start_pos.y()),
                bond_length=self.canvas.renderer.style.bond_length_px,
                occupied=self.context.item_at_scene_pos(end) is not None,
            )
            if point is None:
                return
            end = QPointF(*point)
        self.canvas.services.scene_decoration_service.add_arrow(
            self._start_pos, end, self._line_kind()
        )


__all__ = ["LEVEL_PRESET_BOND_LENGTHS", "LINE_ANGLE_STEP_DEGREES", "LineTool"]
