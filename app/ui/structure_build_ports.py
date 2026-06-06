from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def structure_build_service_for_access(canvas):
    return canvas_services_for(canvas).structure_build_service


__all__ = ["structure_build_service_for_access"]
