from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerspectiveDragUpdate:
    delta_x: float
    delta_y: float
    axis_lock: str | None
    should_update: bool


def resolve_perspective_drag_update(
    *,
    delta_x: float,
    delta_y: float,
    axis_lock: str | None,
    rotation_mode: str,
    shift_pressed: bool,
) -> PerspectiveDragUpdate:
    if rotation_mode != "rigid" or not shift_pressed:
        return PerspectiveDragUpdate(
            delta_x=delta_x,
            delta_y=delta_y,
            axis_lock=None,
            should_update=True,
        )

    next_axis_lock = axis_lock
    if next_axis_lock is None:
        if abs(delta_x) < 1e-9 and abs(delta_y) < 1e-9:
            return PerspectiveDragUpdate(
                delta_x=delta_x,
                delta_y=delta_y,
                axis_lock=None,
                should_update=False,
            )
        next_axis_lock = "x" if abs(delta_x) >= abs(delta_y) else "y"

    if next_axis_lock == "x":
        return PerspectiveDragUpdate(
            delta_x=delta_x,
            delta_y=0.0,
            axis_lock=next_axis_lock,
            should_update=True,
        )

    return PerspectiveDragUpdate(
        delta_x=0.0,
        delta_y=delta_y,
        axis_lock=next_axis_lock,
        should_update=True,
    )


__all__ = ["PerspectiveDragUpdate", "resolve_perspective_drag_update"]
