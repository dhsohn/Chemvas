from __future__ import annotations

from types import SimpleNamespace

from ui.canvas_window_ports import canvas_window_document_session_service


def test_canvas_window_document_session_port_returns_attached_service() -> None:
    document_session_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(canvas_document_session_service=document_session_service)
    )

    assert canvas_window_document_session_service(canvas) is document_session_service
