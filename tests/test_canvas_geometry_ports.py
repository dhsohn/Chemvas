from __future__ import annotations

from types import SimpleNamespace

from ui.canvas_geometry_ports import geometry_controller_for_access


def test_geometry_controller_port_returns_attached_service() -> None:
    geometry_controller = object()
    canvas = SimpleNamespace(services=SimpleNamespace(geometry_controller=geometry_controller))

    assert geometry_controller_for_access(canvas) is geometry_controller
