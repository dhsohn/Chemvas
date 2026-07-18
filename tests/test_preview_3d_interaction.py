from __future__ import annotations

from chemvas.ui.preview_3d_interaction import (
    preview_drag_rotation,
    preview_zoom_for_wheel_delta,
)
from PyQt6.QtCore import QPointF


def test_preview_drag_rotation_applies_pointer_delta_with_default_sensitivity() -> None:
    rotation_x, rotation_y, last_pos = preview_drag_rotation(
        1.0,
        2.0,
        QPointF(4.0, 5.0),
        QPointF(10.0, 8.0),
    )

    assert rotation_x == 1.03
    assert rotation_y == 2.06
    assert last_pos == QPointF(10.0, 8.0)


def test_preview_drag_rotation_accepts_custom_sensitivity() -> None:
    rotation_x, rotation_y, _ = preview_drag_rotation(
        0.0,
        0.0,
        QPointF(1.0, 2.0),
        QPointF(4.0, 6.0),
        sensitivity=0.5,
    )

    assert rotation_x == 2.0
    assert rotation_y == 1.5


def test_preview_zoom_for_wheel_delta_scales_and_clamps() -> None:
    assert preview_zoom_for_wheel_delta(1.0, 120) == 1.1
    assert preview_zoom_for_wheel_delta(1.0, -120) == 0.9
    assert preview_zoom_for_wheel_delta(1.5, 0) == 1.5
    assert preview_zoom_for_wheel_delta(2.9, 120) == 3.0
    assert preview_zoom_for_wheel_delta(0.31, -120) == 0.3
