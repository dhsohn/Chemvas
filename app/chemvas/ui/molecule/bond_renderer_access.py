from __future__ import annotations

from typing import Any


def update_bond_geometry_for(
    canvas: Any, bond_id: int, *, allow_topology_rebuild: bool = False
) -> None:
    renderer = canvas.bond_renderer
    if allow_topology_rebuild:
        renderer.update_bond_geometry(bond_id, allow_topology_rebuild=True)
        return
    renderer.update_bond_geometry(bond_id)


__all__ = ["update_bond_geometry_for"]
