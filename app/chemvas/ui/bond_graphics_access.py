from __future__ import annotations

import math

from PyQt6.QtCore import Qt

from chemvas.ui.bond_renderer_access import bond_renderer_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_service_ports import geometry_controller_for_access
from chemvas.ui.renderer_style_access import bond_length_px_for


def add_bond_graphics_for(canvas, bond_id: int) -> None:
    bond_renderer_for(canvas).add_bond_graphics(bond_id)


def _bond_renderer_method(canvas, name: str):
    renderer = bond_renderer_for(canvas)
    method = getattr(renderer, name, None)
    return method if callable(method) else None


def _renderer_method(canvas, renderer_name: str):
    method = _bond_renderer_method(canvas, renderer_name)
    if method is not None:
        return method
    return None


def parallel_bond_segments_for(canvas, *args):
    method = _renderer_method(canvas, "parallel_bond_segments")
    if method is not None:
        return method(*args)
    return []


def ring_double_segments_for(canvas, *args):
    method = _renderer_method(canvas, "ring_double_segments")
    if method is not None:
        return method(*args)
    return None


def draw_ring_double_bond_for(canvas, *args, **kwargs):
    method = _renderer_method(canvas, "draw_ring_double_bond")
    if method is not None:
        return method(*args, **kwargs)
    return None


def line_normal_components(
    x1: float, y1: float, x2: float, y2: float
) -> tuple[float, float, float]:
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0, 0.0
    return -dy / length, dx / length, length


def orient_normal_toward_target(
    nx: float,
    ny: float,
    mid_x: float,
    mid_y: float,
    target_x: float,
    target_y: float,
) -> tuple[float, float]:
    to_tx = target_x - mid_x
    to_ty = target_y - mid_y
    if nx * to_tx + ny * to_ty < 0:
        return -nx, -ny
    return nx, ny


def line_normal_for(
    canvas, x1: float, y1: float, x2: float, y2: float, target=None
) -> tuple[float, float]:
    nx, ny, _ = line_normal_components(x1, y1, x2, y2)
    if target is None:
        return nx, ny
    mid_x = (x1 + x2) / 2.0
    mid_y = (y1 + y2) / 2.0
    return orient_normal_toward_target(nx, ny, mid_x, mid_y, target.x(), target.y())


def project_point_3d_for(
    canvas,
    point: tuple[float, float, float],
    center_3d: tuple[float, float, float] | None = None,
    anchor_2d: tuple[float, float] | None = None,
) -> tuple[float, float]:
    rotation = rotation_state_for(canvas)
    if center_3d is None:
        center_3d = rotation.projection_center_3d
    if center_3d is None:
        return point[0], point[1]
    if anchor_2d is None:
        anchor_2d = rotation.projection_anchor_2d or (center_3d[0], center_3d[1])
    cx, cy, cz = center_3d
    anchor_x, anchor_y = anchor_2d
    focal = max(bond_length_px_for(canvas) * 8.0, 120.0)
    dz = max(min(point[2] - cz, focal * 0.7), -focal * 0.8)
    denom = max(focal - dz, focal * 0.2)
    scale = focal / denom
    return (
        anchor_x + (point[0] - cx) * scale,
        anchor_y + (point[1] - cy) * scale,
    )


def bond_offset_unit_3d_for(
    canvas,
    a_id: int,
    b_id: int,
    target: tuple[float, float, float] | None = None,
) -> tuple[float, float] | None:
    atom_a = atom_for_id(canvas, a_id)
    atom_b = atom_for_id(canvas, b_id)
    if atom_a is None or atom_b is None:
        return None
    ax, ay = atom_a.x, atom_a.y
    bx, by = atom_b.x, atom_b.y
    nx, ny, length = line_normal_components(ax, ay, bx, by)
    if length < 1e-9:
        return None
    if target is not None:
        mid_x = (ax + bx) * 0.5
        mid_y = (ay + by) * 0.5
        target_x, target_y = project_point_3d_for(canvas, target)
        nx, ny = orient_normal_toward_target(nx, ny, mid_x, mid_y, target_x, target_y)
    return nx, ny


def ring_center_for_bond_for(canvas, bond):
    try:
        return geometry_controller_for_access(canvas).ring_center_for_bond(bond)
    except AttributeError:
        return None


def ring_center_3d_for_bond_for(canvas, bond):
    try:
        return geometry_controller_for_access(canvas).ring_center_3d_for_bond(bond)
    except AttributeError:
        return None


def apply_color_to_bond_item_for(canvas, item, color) -> None:
    if hasattr(item, "setPen"):
        pen = item.pen()
        pen.setColor(color)
        item.setPen(pen)
    if hasattr(item, "setBrush") and item.brush().style() != Qt.BrushStyle.NoBrush:
        item.setBrush(color)


__all__ = [
    "add_bond_graphics_for",
    "apply_color_to_bond_item_for",
    "bond_offset_unit_3d_for",
    "draw_ring_double_bond_for",
    "line_normal_components",
    "line_normal_for",
    "orient_normal_toward_target",
    "parallel_bond_segments_for",
    "project_point_3d_for",
    "ring_center_3d_for_bond_for",
    "ring_center_for_bond_for",
    "ring_double_segments_for",
]
