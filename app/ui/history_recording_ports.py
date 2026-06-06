from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def history_recording_service_for_access(canvas):
    return canvas_services_for(canvas).canvas_history_recording_service


__all__ = ["history_recording_service_for_access"]
