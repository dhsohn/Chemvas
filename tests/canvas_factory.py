from __future__ import annotations

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.canvas_view import CanvasView


def build_canvas_view() -> CanvasView:
    return CanvasView(renderer=Renderer())


__all__ = ["build_canvas_view"]
