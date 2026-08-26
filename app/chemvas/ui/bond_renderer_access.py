from __future__ import annotations


def bond_renderer_for(canvas):
    return canvas.bond_renderer


def update_bond_geometry_for(
    canvas, bond_id: int, *, allow_topology_rebuild: bool = False
) -> None:
    bond_renderer_for(canvas).update_bond_geometry(
        bond_id, allow_topology_rebuild=allow_topology_rebuild
    )


__all__ = ["bond_renderer_for", "update_bond_geometry_for"]
