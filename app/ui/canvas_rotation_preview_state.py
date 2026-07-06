from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QGraphicsItemGroup

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasRotationPreviewState:
    group: QGraphicsItemGroup | None = None


def rotation_preview_state_for(canvas) -> CanvasRotationPreviewState:
    return ensure_canvas_state(canvas, "rotation_preview_state", CanvasRotationPreviewState)


__all__ = ["CanvasRotationPreviewState", "rotation_preview_state_for"]
