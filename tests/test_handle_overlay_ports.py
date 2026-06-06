from __future__ import annotations

from types import SimpleNamespace

from ui.handle_overlay_ports import handle_overlay_service_for_access


def test_handle_overlay_service_port_returns_attached_service() -> None:
    overlay_service = object()
    canvas = SimpleNamespace(services=SimpleNamespace(handle_overlay_service=overlay_service))

    assert handle_overlay_service_for_access(canvas) is overlay_service
