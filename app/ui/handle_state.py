from __future__ import annotations

from dataclasses import dataclass, field

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class CanvasHandleState:
    active_handles: list = field(default_factory=list)
    target: object | None = None


def handle_state_for(canvas) -> CanvasHandleState:
    state = canvas_state_object(canvas, "handle_state")
    if state is not None:
        return state
    state = CanvasHandleState()
    canvas.handle_state = state
    return state


def active_handles_for(canvas):
    return handle_state_for(canvas).active_handles


def set_active_handles_for(canvas, handles) -> None:
    state = handle_state_for(canvas)
    state.active_handles = handles


def handle_target_for(canvas):
    return handle_state_for(canvas).target


def set_handle_target_for(canvas, target) -> None:
    state = handle_state_for(canvas)
    state.target = target


__all__ = [
    "CanvasHandleState",
    "active_handles_for",
    "handle_target_for",
    "handle_state_for",
    "set_active_handles_for",
    "set_handle_target_for",
]
