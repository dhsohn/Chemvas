from __future__ import annotations


def bond_renderer_for(canvas):
    return canvas.bond_renderer


def update_bond_geometry_for(
    canvas, bond_id: int, *, allow_topology_rebuild: bool = False
) -> None:
    renderer = bond_renderer_for(canvas)
    if allow_topology_rebuild:
        renderer.update_bond_geometry(bond_id, allow_topology_rebuild=True)
        return
    renderer.update_bond_geometry(bond_id)


__all__ = ["bond_renderer_for", "update_bond_geometry_for"]
