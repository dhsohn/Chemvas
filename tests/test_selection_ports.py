from __future__ import annotations

from types import SimpleNamespace

from ui.selection_ports import selection_service_for_access


def test_selection_service_port_returns_attached_service() -> None:
    selection_controller = object()
    canvas = SimpleNamespace(services=SimpleNamespace(selection_controller=selection_controller))

    assert selection_service_for_access(canvas) is selection_controller
