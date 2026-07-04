from __future__ import annotations

from types import SimpleNamespace

import pytest
from ui.canvas_service_access import canvas_services_for, optional_canvas_service_method


def _attach_private_shaped_attr(canvas, attr: str, value) -> None:
    setattr(canvas, attr, value)


def test_canvas_services_for_returns_attached_services_bundle() -> None:
    services = SimpleNamespace(scene_item_controller=object())
    canvas = SimpleNamespace(services=services)

    assert canvas_services_for(canvas) is services
    with pytest.raises(AttributeError):
        canvas_services_for(SimpleNamespace())


def test_canvas_services_for_does_not_promote_private_shaped_attr() -> None:
    legacy = object()
    canvas = SimpleNamespace(services=SimpleNamespace())
    _attach_private_shaped_attr(canvas, "_scene_item_controller", legacy)

    assert canvas_services_for(canvas) is canvas.services
    assert not hasattr(canvas.services, "scene_item_controller")


def test_optional_canvas_service_method_returns_callable_method() -> None:
    calls = []
    service = SimpleNamespace(record=lambda value: calls.append(value))
    canvas = SimpleNamespace(services=SimpleNamespace(history=service))

    method = optional_canvas_service_method(canvas, lambda target: target.services.history, "record")

    assert method is service.record
    method("update")
    assert calls == ["update"]


def test_optional_canvas_service_method_returns_none_without_service_or_method() -> None:
    canvas = SimpleNamespace()

    assert optional_canvas_service_method(canvas, lambda target: target.services.history, "record") is None
    assert optional_canvas_service_method(SimpleNamespace(services=SimpleNamespace()), lambda target: target.services, "record") is None
