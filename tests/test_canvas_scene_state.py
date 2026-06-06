from __future__ import annotations

from unittest import mock

from ui.canvas_scene_state import canvas_scene_for, optional_canvas_scene_for


def test_canvas_scene_state_returns_canvas_scene() -> None:
    scene = object()
    canvas = mock.Mock()
    canvas.scene.return_value = scene

    assert canvas_scene_for(canvas) is scene
    assert optional_canvas_scene_for(canvas) is scene


def test_optional_canvas_scene_state_tolerates_deleted_qt_scene() -> None:
    canvas = mock.Mock()
    canvas.scene.side_effect = RuntimeError("deleted")

    assert optional_canvas_scene_for(canvas) is None
