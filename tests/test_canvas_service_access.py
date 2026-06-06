from __future__ import annotations

from types import SimpleNamespace

import pytest
from ui.canvas_service_access import canvas_services_for


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
