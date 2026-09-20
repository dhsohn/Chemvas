from __future__ import annotations

from chemvas.ui.scene_render_access import scene_render_context_for


def label_rect_for_atom_for(canvas, atom_id: int):
    return scene_render_context_for(canvas).geometry.label_rect_for_atom(atom_id)


def trim_line_for_labels_for(
    canvas,
    a_id: int | None,
    b_id: int | None,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    offsets: tuple[tuple[float, float], ...] = (),
) -> tuple[float, float]:
    return scene_render_context_for(canvas).geometry.trim_line_for_labels(
        a_id, b_id, x1, y1, x2, y2, offsets
    )


__all__ = ["label_rect_for_atom_for", "trim_line_for_labels_for"]
