from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def atom_label_service_for_access(canvas):
    return canvas_services_for(canvas).atom_label_service


__all__ = ["atom_label_service_for_access"]
