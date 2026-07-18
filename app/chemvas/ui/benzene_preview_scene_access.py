from __future__ import annotations

from chemvas.ui.benzene_preview_renderer import (
    clear_benzene_preview,
    rebuild_benzene_preview,
)
from chemvas.ui.scene_item_access import canvas_scene_for


def clear_benzene_preview_for_canvas(canvas, items):
    return clear_benzene_preview(canvas_scene_for(canvas), items)


def rebuild_benzene_preview_for_canvas(
    canvas,
    points,
    *,
    base_pen,
    atom_radius: float,
    create_inner_bond_item,
):
    return rebuild_benzene_preview(
        canvas_scene_for(canvas),
        points,
        base_pen=base_pen,
        atom_radius=atom_radius,
        create_inner_bond_item=create_inner_bond_item,
    )


__all__ = ["clear_benzene_preview_for_canvas", "rebuild_benzene_preview_for_canvas"]
