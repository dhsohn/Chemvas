from __future__ import annotations

from chemvas.ui.canvas_service_ports import ring_fill_scene_service_for_access


def create_ring_fill_item_for(canvas, points, atom_ids):
    return ring_fill_scene_service_for_access(canvas).create_ring_fill_item(
        points, atom_ids
    )


def update_ring_fills_for_atoms_for(
    canvas,
    atom_ids: set[int],
    *,
    ring_items: tuple[object, ...] | None = None,
) -> None:
    service = ring_fill_scene_service_for_access(canvas)
    if ring_items is None:
        # Preserve the legacy collaborator surface for injected/lightweight
        # canvases. The new cache port is only required by an active preview.
        service.update_ring_fills_for_atoms(atom_ids)
        return
    service.update_ring_fills_for_atoms(atom_ids, ring_items=ring_items)


__all__ = [
    "create_ring_fill_item_for",
    "update_ring_fills_for_atoms_for",
]
