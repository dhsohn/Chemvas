from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CanvasHandleState:
    active_handles: list = field(default_factory=list)
    target: object | None = None


def set_active_handles_for(canvas, handles) -> None:
    state = canvas.runtime_state.handle_state
    state.active_handles = handles


def set_handle_target_for(canvas, target) -> None:
    state = canvas.runtime_state.handle_state
    state.target = target


__all__ = [
    "CanvasHandleState",
    "set_active_handles_for",
    "set_handle_target_for",
]
