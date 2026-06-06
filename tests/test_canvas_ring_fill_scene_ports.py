from __future__ import annotations

from types import SimpleNamespace

from ui.canvas_ring_fill_scene_ports import ring_fill_scene_service_for_access


def test_ring_fill_scene_service_port_returns_attached_service() -> None:
    ring_fill_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(canvas_ring_fill_scene_service=ring_fill_service)
    )

    assert ring_fill_scene_service_for_access(canvas) is ring_fill_service
