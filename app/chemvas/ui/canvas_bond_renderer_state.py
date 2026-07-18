from __future__ import annotations

from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state


def bond_renderer_for(canvas: Any):
    from chemvas.ui.bond_renderer import BondRenderer

    return ensure_canvas_state(
        canvas, "bond_renderer", lambda: BondRenderer(canvas), runtime_field=False
    )


def set_bond_renderer_for(canvas: Any, renderer) -> None:
    canvas.bond_renderer = renderer


def update_bond_geometry_for(canvas: Any, bond_id: int) -> None:
    """Refresh one bond's geometry; tolerates stub renderers without the hook."""
    update = getattr(bond_renderer_for(canvas), "update_bond_geometry", None)
    if callable(update):
        update(bond_id)


__all__ = ["bond_renderer_for", "set_bond_renderer_for", "update_bond_geometry_for"]
