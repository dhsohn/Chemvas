from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsItemGroup

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass(frozen=True, slots=True)
class RotationPreviewItemSnapshot:
    item: QGraphicsItem
    state: dict


@dataclass(slots=True)
class CanvasRotationPreviewState:
    group: QGraphicsItemGroup | None = None
    position_snapshots: list[RotationPreviewItemSnapshot] = field(default_factory=list)
    center: object | None = None


def rotation_preview_state_for(canvas) -> CanvasRotationPreviewState:
    return ensure_canvas_state(canvas, "rotation_preview_state", CanvasRotationPreviewState)


__all__ = [
    "CanvasRotationPreviewState",
    "RotationPreviewItemSnapshot",
    "rotation_preview_state_for",
]
