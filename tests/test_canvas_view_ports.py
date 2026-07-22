from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from chemvas.ui.canvas_view_ports import (
    input_controller_for_view,
    pointer_controller_for_view,
    scene_pos_from_event_for_view,
)
from PyQt6.QtCore import QPointF

from tests.runtime_services import canvas_runtime_services


def test_input_controller_for_view_returns_attached_input_controller() -> None:
    input_controller = object()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(
            input=SimpleNamespace(input_controller=input_controller)
        )
    )

    assert input_controller_for_view(canvas) is input_controller


def test_input_controller_for_view_returns_none_when_services_are_missing() -> None:
    assert input_controller_for_view(SimpleNamespace()) is None


def test_pointer_controller_for_view_returns_attached_pointer_controller() -> None:
    pointer_controller = object()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(
            input=SimpleNamespace(pointer_controller=pointer_controller)
        )
    )

    assert pointer_controller_for_view(canvas) is pointer_controller


def test_pointer_controller_for_view_returns_none_when_services_are_missing() -> None:
    assert pointer_controller_for_view(SimpleNamespace()) is None


def test_scene_pos_from_event_for_view_uses_qt6_position_point() -> None:
    event = mock.Mock()
    event.position.return_value.toPoint.return_value = "position-point"
    canvas = mock.Mock()
    canvas.mapToScene.return_value = QPointF(1.0, 2.0)

    assert scene_pos_from_event_for_view(canvas, event) == QPointF(1.0, 2.0)

    canvas.mapToScene.assert_called_once_with("position-point")
