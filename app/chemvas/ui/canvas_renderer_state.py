from __future__ import annotations

from typing import Any

from chemvas.core.renderer import Renderer
from chemvas.ui.canvas_state_lookup import ensure_canvas_state


def renderer_for(canvas: Any):
    return ensure_canvas_state(canvas, "renderer", Renderer, runtime_field=False)


def set_renderer_for(canvas: Any, renderer) -> None:
    canvas.renderer = renderer


__all__ = ["renderer_for", "set_renderer_for"]
