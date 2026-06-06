from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def selection_highlight_styler_for_access(canvas):
    return canvas_services_for(canvas).selection_highlight_styler


__all__ = ["selection_highlight_styler_for_access"]
