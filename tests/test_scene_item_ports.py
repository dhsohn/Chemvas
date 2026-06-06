from __future__ import annotations

from types import SimpleNamespace

from ui.scene_item_ports import scene_item_controller_for_access


def test_scene_item_controller_port_returns_attached_service() -> None:
    scene_item_controller = object()
    canvas = SimpleNamespace(services=SimpleNamespace(scene_item_controller=scene_item_controller))

    assert scene_item_controller_for_access(canvas) is scene_item_controller
