from __future__ import annotations

from typing import Any

from core.renderer import Renderer

from ui.canvas_state_lookup import canvas_state_object


def renderer_for(canvas: Any):
    renderer = canvas_state_object(canvas, "renderer")
    if renderer is not None:
        return renderer
    renderer = Renderer()
    canvas.renderer = renderer
    return renderer


def set_renderer_for(canvas: Any, renderer) -> None:
    canvas.renderer = renderer


__all__ = ["renderer_for", "set_renderer_for"]
