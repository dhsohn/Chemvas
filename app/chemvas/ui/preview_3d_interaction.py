from __future__ import annotations

from PyQt6.QtCore import QPointF


def preview_drag_rotation(
    rotation_x: float,
    rotation_y: float,
    last_pos: QPointF,
    current_pos: QPointF,
    *,
    sensitivity: float = 0.01,
) -> tuple[float, float, QPointF]:
    delta = current_pos - last_pos
    return (
        rotation_x + delta.y() * sensitivity,
        rotation_y + delta.x() * sensitivity,
        QPointF(current_pos),
    )


def preview_zoom_for_wheel_delta(
    zoom: float,
    delta_y: int,
    *,
    step: float = 0.1,
    min_zoom: float = 0.3,
    max_zoom: float = 3.0,
) -> float:
    if not delta_y:
        return zoom
    factor = 1.0 + (step if delta_y > 0 else -step)
    return max(min_zoom, min(max_zoom, zoom * factor))


__all__ = [
    "preview_drag_rotation",
    "preview_zoom_for_wheel_delta",
]
