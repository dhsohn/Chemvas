from __future__ import annotations

from typing import Any, cast

from chemvas.features.hover import HoverState


def hover_state_for(canvas: Any) -> HoverState:
    """Return the canonical hover state owned by ``CanvasRuntimeState``."""

    return cast(HoverState, canvas.runtime_state.hover_preview_state)


__all__ = ["HoverState", "hover_state_for"]
