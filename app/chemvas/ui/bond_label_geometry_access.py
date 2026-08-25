from __future__ import annotations

from chemvas.ui.canvas_service_ports import geometry_controller_for_access


def label_rect_for_atom_for(canvas, atom_id: int):
    return geometry_controller_for_access(canvas).label_rect_for_atom(atom_id)


def trim_line_for_labels_for(
    canvas,
    a_id: int | None,
    b_id: int | None,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[float, float]:
    return geometry_controller_for_access(canvas).trim_line_for_labels(
        a_id, b_id, x1, y1, x2, y2
    )


__all__ = ["label_rect_for_atom_for", "trim_line_for_labels_for"]
