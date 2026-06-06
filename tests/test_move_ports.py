from __future__ import annotations

from types import SimpleNamespace

from ui.move_ports import move_controller_for_access


def test_move_controller_port_returns_attached_service() -> None:
    move_controller = object()
    canvas = SimpleNamespace(services=SimpleNamespace(move_controller=move_controller))

    assert move_controller_for_access(canvas) is move_controller
