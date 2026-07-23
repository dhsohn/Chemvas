from __future__ import annotations


def bond_renderer_for(canvas):
    return canvas.bond_renderer


def update_bond_geometry_for(canvas, bond_id: int) -> None:
    bond_renderer_for(canvas).update_bond_geometry(bond_id)


__all__ = ["bond_renderer_for", "update_bond_geometry_for"]
