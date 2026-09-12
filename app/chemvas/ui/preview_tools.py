from __future__ import annotations

from typing import override

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from chemvas.core.tool_overlay_logic import (
    activate_tool_no_drag,
    clear_temporary_tool_overlay,
)
from chemvas.domain.document import VALID_ARC_KINDS, mirrored_arc_kind
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.endpoint_snap_access import snap_drawing_point_for
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_orbital_for,
    add_shape_from_points_for,
    add_ts_bracket_from_points_for,
    preview_arrow_for,
    preview_shape_for,
    preview_ts_bracket_for,
)
from chemvas.ui.scene_decoration_build_access import mark_snapped_points_for
from chemvas.ui.tool_base import Tool


class PreviewDragTool(Tool):
    def __init__(self, name: str, canvas, *, context=None) -> None:
        super().__init__(name, canvas, context=context)
        self._start_pos: QPointF | None = None
        self._press_pos: QPointF | None = None
        self._press_view_pos: QPointF | None = None
        self._drag_threshold_exceeded = False
        self._preview_item = None

    @property
    @override
    def has_active_gesture(self) -> bool:
        return self._start_pos is not None

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    @override
    def deactivate(self) -> None:
        self._clear_preview()
        self._start_pos = None
        self._press_pos = None
        self._press_view_pos = None
        self._drag_threshold_exceeded = False

    def _clear_preview(self) -> None:
        clear_temporary_tool_overlay(self.canvas, preview_item=self._preview_item)
        self._preview_item = None

    def _click_end_or_none(self, current_pos: QPointF) -> QPointF | None:
        """The end of a gesture below the system's screen-pixel drag distance.

        The press point goes through the snap funnel once, on press.
        Asking the funnel again on release answers differently whenever
        the press took an existing endpoint, because that endpoint is
        then the one point the release may not take, and the click would
        commit a stub instead of reading as a click.
        """
        if self._start_pos is None or self._press_pos is None:
            return None
        return self._start_pos if not self._drag_threshold_exceeded else None

    def _update_drag_distance(self, event) -> None:
        if self._press_view_pos is not None:
            distance = (event.position() - self._press_view_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._drag_threshold_exceeded = True

    def _build_preview(self, current_pos):
        raise NotImplementedError

    def _commit_drag(self, end_pos) -> None:
        raise NotImplementedError

    @override
    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start_pos = self.context.scene_pos_from_event(event)
        self._press_pos = QPointF(self._start_pos)
        self._press_view_pos = QPointF(event.position())
        self._drag_threshold_exceeded = False
        return True

    @override
    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        self._update_drag_distance(event)
        current_pos = self.context.scene_pos_from_event(event)
        self._clear_preview()
        self._preview_item = self._build_preview(current_pos)
        return True

    @override
    def on_mouse_release(self, event) -> bool:
        if self._start_pos is None:
            return False
        self._update_drag_distance(event)
        end_pos = self.context.scene_pos_from_event(event)
        self._clear_preview()
        try:
            self._commit_drag(end_pos)
        finally:
            self._start_pos = None
            self._press_pos = None
            self._press_view_pos = None
            self._drag_threshold_exceeded = False
        return True


class ArrowTool(PreviewDragTool):
    def __init__(self, canvas, mode: str = "auto", *, context=None) -> None:
        super().__init__("arrow", canvas, context=context)
        self.mode = mode
        self._mirror_arc = False

    def _arrow_type(self) -> str:
        kind = (
            self.mode
            if self.mode != "auto"
            else tool_settings_state_for(self.canvas).active_arrow_type
        )
        if self._mirror_arc and kind in VALID_ARC_KINDS:
            return mirrored_arc_kind(kind)
        return kind

    def _read_arc_mirror(self, event) -> None:
        # Shift while dragging bulges an arc to the other side of the drag.
        self._mirror_arc = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

    @override
    def on_mouse_press(self, event) -> bool:
        handled = super().on_mouse_press(event)
        if handled and self._start_pos is not None:
            self._start_pos = snap_drawing_point_for(self.canvas, self._start_pos)
        return handled

    @override
    def on_mouse_move(self, event) -> bool:
        self._read_arc_mirror(event)
        return super().on_mouse_move(event)

    @override
    def on_mouse_release(self, event) -> bool:
        self._read_arc_mirror(event)
        return super().on_mouse_release(event)

    def _end_point(self, current_pos):
        click_end = self._click_end_or_none(current_pos)
        if click_end is not None:
            return click_end
        # Never take the end this drag started from, or a short drag from an
        # existing endpoint would be swallowed; the grid may still land there,
        # which is how a drag shorter than one grid step reads as a click.
        return snap_drawing_point_for(self.canvas, current_pos, avoid=self._start_pos)

    @override
    def _build_preview(self, current_pos):
        end = self._end_point(current_pos)
        item = preview_arrow_for(self.canvas, self._start_pos, end, self._arrow_type())
        mark_snapped_points_for(self.canvas, item, [self._start_pos, end])
        return item

    @override
    def _commit_drag(self, end_pos) -> None:
        end = self._end_point(end_pos)
        if end == self._start_pos:
            # A click without a drag would add a headless stub; it also lets a
            # double-click reach the arrow under the cursor instead of a stub.
            return
        add_arrow_for(self.canvas, self._start_pos, end, self._arrow_type())


class TSBracketTool(PreviewDragTool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("ts_bracket", canvas, context=context)

    def _bracket_type(self) -> str:
        return tool_settings_state_for(self.canvas).active_bracket_type

    @override
    def _build_preview(self, current_pos):
        return preview_ts_bracket_for(
            self.canvas, self._start_pos, current_pos, self._bracket_type()
        )

    @override
    def _commit_drag(self, end_pos) -> None:
        add_ts_bracket_from_points_for(
            self.canvas, self._start_pos, end_pos, self._bracket_type()
        )


class ShapeTool(PreviewDragTool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("shape", canvas, context=context)

    def _shape_kind(self) -> str:
        return tool_settings_state_for(self.canvas).active_shape_type

    def _stroke_style(self) -> str:
        return tool_settings_state_for(self.canvas).active_shape_stroke

    @override
    def _build_preview(self, current_pos):
        return preview_shape_for(
            self.canvas,
            self._start_pos,
            current_pos,
            shape_kind=self._shape_kind(),
            stroke_style=self._stroke_style(),
        )

    @override
    def _commit_drag(self, end_pos) -> None:
        add_shape_from_points_for(
            self.canvas,
            self._start_pos,
            end_pos,
            shape_kind=self._shape_kind(),
            stroke_style=self._stroke_style(),
        )


class OrbitalTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("orbital", canvas, context=context)

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    @override
    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        add_orbital_for(self.canvas, pos)
        return True


__all__ = ["ArrowTool", "OrbitalTool", "PreviewDragTool", "ShapeTool", "TSBracketTool"]
