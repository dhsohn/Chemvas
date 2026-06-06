from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def benzene_preview_service_for_access(canvas):
    return canvas_services_for(canvas).benzene_preview_service


__all__ = ["benzene_preview_service_for_access"]
