from __future__ import annotations

from types import SimpleNamespace

from ui.history_recording_ports import history_recording_service_for_access


def test_history_recording_service_port_returns_attached_service() -> None:
    recording_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(canvas_history_recording_service=recording_service)
    )

    assert history_recording_service_for_access(canvas) is recording_service
