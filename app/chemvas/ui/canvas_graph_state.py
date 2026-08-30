from __future__ import annotations

from typing import Any, cast

from chemvas.features.graph import CanvasGraphState


def graph_state_for(canvas: Any) -> CanvasGraphState:
    return cast("CanvasGraphState", canvas.runtime_state.graph_state)


__all__ = ["CanvasGraphState", "graph_state_for"]
