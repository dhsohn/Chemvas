from __future__ import annotations

from typing import Any

from ui.canvas_state_lookup import canvas_state_object


def bond_renderer_for(canvas: Any):
    renderer = canvas_state_object(canvas, "bond_renderer")
    if renderer is not None:
        return renderer
    from ui.bond_renderer import BondRenderer

    renderer = BondRenderer(canvas)
    canvas.bond_renderer = renderer
    return renderer


def set_bond_renderer_for(canvas: Any, renderer) -> None:
    canvas.bond_renderer = renderer


__all__ = ["bond_renderer_for", "set_bond_renderer_for"]
