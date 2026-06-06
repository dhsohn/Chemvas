from __future__ import annotations

from ui.canvas_geometry_ports import geometry_controller_for_access


def label_rect_for_atom_for(canvas, atom_id: int):
    try:
        controller = geometry_controller_for_access(canvas)
    except AttributeError:
        controller = None
    label_rect_for_atom = getattr(controller, "label_rect_for_atom", None)
    if callable(label_rect_for_atom):
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
    try:
        controller = geometry_controller_for_access(canvas)
    except AttributeError:
        controller = None
    trim_line_for_labels = getattr(controller, "trim_line_for_labels", None)
    if callable(trim_line_for_labels):
        return trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
    return (0.0, 1.0)


__all__ = ["label_rect_for_atom_for", "trim_line_for_labels_for"]
