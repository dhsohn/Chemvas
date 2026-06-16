from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QGraphicsItemGroup

from ui.canvas_state_lookup import canvas_state_object


@dataclass(slots=True)
class CanvasRotationPreviewState:
    group: QGraphicsItemGroup | None = None


def rotation_preview_state_for(canvas) -> CanvasRotationPreviewState:
    state = canvas_state_object(canvas, "rotation_preview_state")
    if state is not None:
        return state
    state = CanvasRotationPreviewState()
    canvas.rotation_preview_state = state
    return state


__all__ = ["CanvasRotationPreviewState", "rotation_preview_state_for"]
