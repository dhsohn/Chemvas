from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def canvas_window_document_session_service(canvas):
    return canvas_services_for(canvas).canvas_document_session_service


__all__ = ["canvas_window_document_session_service"]
