from __future__ import annotations

from types import SimpleNamespace

from chemvas.ui.canvas.canvas_view_ports import (
    input_controller_for_view,
    pointer_controller_for_view,
)
from tests.runtime_services import canvas_runtime_services


def test_input_controller_for_view_returns_attached_input_controller() -> None:
    input_controller = object()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(input_controller=input_controller)
    )

    assert input_controller_for_view(canvas) is input_controller


def test_input_controller_for_view_returns_none_when_services_are_missing() -> None:
    assert input_controller_for_view(SimpleNamespace()) is None


def test_pointer_controller_for_view_returns_attached_pointer_controller() -> None:
    pointer_controller = object()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(pointer_controller=pointer_controller)
    )

    assert pointer_controller_for_view(canvas) is pointer_controller


def test_pointer_controller_for_view_returns_none_when_services_are_missing() -> None:
    assert pointer_controller_for_view(SimpleNamespace()) is None
