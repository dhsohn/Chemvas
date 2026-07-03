from __future__ import annotations

from ui.canvas_service_ports import geometry_controller_for_access


def _geometry_method(canvas, name: str):
    try:
        controller = geometry_controller_for_access(canvas)
    except AttributeError:
        controller = None
    method = getattr(controller, name, None)
    return method if callable(method) else None


def visible_label_rect_for_atom_for(canvas, atom_id: int):
    method = _geometry_method(canvas, "visible_label_rect_for_atom")
    if callable(method):
        return method(atom_id)
    return None


def mark_clearance_for_kind_for(canvas, kind: str) -> float:
    method = _geometry_method(canvas, "mark_clearance_for_kind")
    if callable(method):
        return method(kind)
    return 0.0


def label_cut_radius_for_atom_for(canvas, atom_id: int) -> float | None:
    method = _geometry_method(canvas, "label_cut_radius_for_atom")
    if callable(method):
        return method(atom_id)
    return None


def mark_target_distance_for_atom_for(
    canvas,
    atom_id: int,
    direction_x: float,
    direction_y: float,
    kind: str,
) -> float:
    method = _geometry_method(canvas, "mark_target_distance_for_atom")
    if callable(method):
        return method(atom_id, direction_x, direction_y, kind)
    return 0.0


__all__ = [
    "label_cut_radius_for_atom_for",
    "mark_clearance_for_kind_for",
    "mark_target_distance_for_atom_for",
    "visible_label_rect_for_atom_for",
]
