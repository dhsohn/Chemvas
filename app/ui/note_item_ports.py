from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def note_controller_for_access(canvas):
    return canvas_services_for(canvas).note_controller


__all__ = ["note_controller_for_access"]
