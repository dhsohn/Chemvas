from __future__ import annotations

from core.perspective_drag_logic import resolve_perspective_drag_update
from PyQt6.QtCore import Qt

from ui.canvas_rotation_state import rotation_state_for
from ui.perspective_tool_controller import PerspectiveToolController
from ui.tool_base import Tool


def _perspective_tool_controller_for(canvas, *, context) -> PerspectiveToolController:
    return PerspectiveToolController(canvas, context=context)


class PerspectiveTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("perspective", canvas, context=context)
        self._last_pos = None
        self._rotating = False
        self._axis_lock = None

    def activate(self) -> None:
        self.context.set_rubber_band_drag_mode()

    def deactivate(self) -> None:
        self._commit_active_rotation()

    def _commit_active_rotation(self) -> None:
        if not self._rotating:
            self._last_pos = None
            self._axis_lock = None
            return
        # Keep the local drag session intact until the controller confirms the
        # commit. If history/selection finalization raises, deactivate propagates
        # the error and a delayed release (or explicit retry) can finish the same
        # session instead of silently stranding it.
        self.context.end_selection_3d_rotation()
        self._last_pos = None
        self._rotating = False
        self._axis_lock = None

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._rotating:
            # A release/finalization callback may have failed while the visual
            # rotation remained active. Commit that same session before any
            # shift-toggle or new begin call can overwrite its shared state.
            # _commit_active_rotation deliberately preserves locals on failure,
            # so the exception aborts this press and a later press can retry.
            self._commit_active_rotation()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            item = self.context.item_at_event(event)
            if self.context.toggle_item_selection(item):
                return True
        self._rotating = _perspective_tool_controller_for(self.canvas, context=self.context).begin_selection_rotation(event)
        if self._rotating:
            self._last_pos = event.position()
            self._axis_lock = None
        else:
            self._last_pos = None
        return self._rotating

    def on_mouse_move(self, event) -> bool:
        if self._last_pos is None or not self._rotating:
            return self._rotating
        current = event.position()
        delta = current - self._last_pos
        update = resolve_perspective_drag_update(
            delta_x=delta.x(),
            delta_y=delta.y(),
            axis_lock=self._axis_lock,
            rotation_mode=rotation_state_for(self.canvas).mode,
            shift_pressed=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier),
        )
        if not update.should_update:
            self._axis_lock = update.axis_lock
            return True
        self.context.update_selection_3d_rotation(update.delta_x, update.delta_y)
        # Publish both local drag cursors only after the controller confirms
        # the preview update. A mutate-then-raise controller rolls its own
        # preview back; retaining these values lets the next move retry the
        # exact same delta and axis-lock decision.
        self._axis_lock = update.axis_lock
        self._last_pos = current
        return True

    def on_mouse_release(self, event) -> bool:
        self._commit_active_rotation()
        return True


__all__ = ["PerspectiveTool"]
