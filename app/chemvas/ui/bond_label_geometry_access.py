from __future__ import annotations

from chemvas.ui.canvas_service_access import optional_canvas_service_method
from chemvas.ui.canvas_service_ports import geometry_controller_for_access


def label_rect_for_atom_for(canvas, atom_id: int):
    label_rect_for_atom = optional_canvas_service_method(
        canvas,
        geometry_controller_for_access,
        "label_rect_for_atom",
    )
    if label_rect_for_atom is not None:
        return label_rect_for_atom(atom_id)
    return None


def trim_line_for_labels_for(
    canvas,
    a_id: int | None,
    b_id: int | None,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[float, float]:
    trim_line_for_labels = optional_canvas_service_method(
        canvas,
        geometry_controller_for_access,
        "trim_line_for_labels",
    )
    if trim_line_for_labels is not None:
        return trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
    return (0.0, 1.0)


__all__ = ["label_rect_for_atom_for", "trim_line_for_labels_for"]
