from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtGui import QTransform

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class InputViewState:
    base_transform: QTransform = field(default_factory=QTransform)
    perspective_shear: float = 0.0
    perspective_scale_y: float = 1.0
    # Persistent view magnification (1.0 == 100%). Survives the transform
    # resets that scrolling and native gestures trigger, unlike the transient
    # rotation/perspective tracked above.
    zoom: float = 1.0


def input_view_state_for(canvas: Any) -> InputViewState:
    state = canvas_state_object(canvas, "input_view_state")
    if state is not None:
        return state
    state = InputViewState()
    canvas.input_view_state = state
    return state


__all__ = ["InputViewState", "input_view_state_for"]
