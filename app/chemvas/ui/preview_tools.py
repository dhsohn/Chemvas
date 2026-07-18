from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt

from chemvas.core.tool_overlay_logic import (
    activate_tool_no_drag,
    clear_temporary_tool_overlay,
)
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_orbital_for,
    add_shape_from_points_for,
    add_ts_bracket_from_points_for,
    preview_arrow_for,
    preview_shape_for,
    preview_ts_bracket_for,
)
from chemvas.ui.tool_base import Tool


class PreviewDragTool(Tool):
    def __init__(self, name: str, canvas, *, context=None) -> None:
        super().__init__(name, canvas, context=context)
        self._start_pos: QPointF | None = None
        self._preview_item = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        self._clear_preview()
        self._start_pos = None

    def _clear_preview(self) -> None:
        self._preview_item = clear_temporary_tool_overlay(
            self.canvas, preview_item=self._preview_item
        )

    def _build_preview(self, current_pos):
        raise NotImplementedError

    def _commit_drag(self, end_pos) -> None:
        raise NotImplementedError

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start_pos = self.context.scene_pos_from_event(event)
        return True

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        current_pos = self.context.scene_pos_from_event(event)
        self._clear_preview()
        self._preview_item = self._build_preview(current_pos)
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is None:
            return False
        end_pos = self.context.scene_pos_from_event(event)
        self._clear_preview()
        try:
            self._commit_drag(end_pos)
        finally:
            self._start_pos = None
        return True


class ArrowTool(PreviewDragTool):
    def __init__(self, canvas, mode: str = "auto", *, context=None) -> None:
        super().__init__("arrow", canvas, context=context)
        self.mode = mode

    def _arrow_type(self) -> str:
        return (
            self.mode
            if self.mode != "auto"
            else tool_settings_state_for(self.canvas).active_arrow_type
        )

    def _build_preview(self, current_pos):
        return preview_arrow_for(
            self.canvas, self._start_pos, current_pos, self._arrow_type()
        )

    def _commit_drag(self, end_pos) -> None:
        add_arrow_for(self.canvas, self._start_pos, end_pos, self._arrow_type())


class TSBracketTool(PreviewDragTool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("ts_bracket", canvas, context=context)

    def _bracket_type(self) -> str:
        return tool_settings_state_for(self.canvas).active_bracket_type

    def _build_preview(self, current_pos):
        return preview_ts_bracket_for(
            self.canvas, self._start_pos, current_pos, self._bracket_type()
        )

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

    def _build_preview(self, current_pos):
        return preview_shape_for(
            self.canvas,
            self._start_pos,
            current_pos,
            shape_kind=self._shape_kind(),
            stroke_style=self._stroke_style(),
        )

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

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        add_orbital_for(self.canvas, pos)
        return True


__all__ = ["ArrowTool", "OrbitalTool", "PreviewDragTool", "ShapeTool", "TSBracketTool"]
