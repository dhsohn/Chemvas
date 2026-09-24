from __future__ import annotations


def create_ring_fill_item_for(canvas, points, atom_ids):
    return canvas.services.canvas_ring_fill_scene_service.create_ring_fill_item(
        points, atom_ids
    )


def update_ring_fills_for_atoms_for(
    canvas,
    atom_ids: set[int],
    *,
    ring_items: tuple[object, ...] | None = None,
) -> None:
    service = canvas.services.canvas_ring_fill_scene_service
    service.update_ring_fills_for_atoms(atom_ids, ring_items=ring_items)


__all__ = [
    "create_ring_fill_item_for",
    "update_ring_fills_for_atoms_for",
]
