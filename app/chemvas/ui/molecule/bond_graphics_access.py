from __future__ import annotations

import math

from chemvas.ui.molecule.bond_graphics_build_service import apply_color_to_bond_item
from chemvas.ui.molecule.bond_renderer_access import bond_renderer_for
from chemvas.ui.scene.scene_geometry import SceneGeometry, project_point_in_scene


def add_bond_graphics_for(canvas, bond_id: int) -> None:
    bond_renderer_for(canvas).add_bond_graphics(bond_id)


def parallel_bond_segments_for(canvas, *args):
    return bond_renderer_for(canvas).parallel_bond_segments(*args)


def ring_double_segments_for(canvas, *args):
    return bond_renderer_for(canvas).ring_double_segments(*args)


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
    return SceneGeometry.line_normal(x1, y1, x2, y2, target)


def project_point_3d_for(
    canvas,
    point: tuple[float, float, float],
    center_3d: tuple[float, float, float] | None = None,
    anchor_2d: tuple[float, float] | None = None,
) -> tuple[float, float]:
    rotation = canvas.runtime_state.rotation_state
    if center_3d is None:
        center_3d = rotation.projection_center_3d
    if center_3d is None:
        return point[0], point[1]
    if anchor_2d is None:
        anchor_2d = rotation.projection_anchor_2d or (center_3d[0], center_3d[1])
    return project_point_in_scene(
        point,
        bond_length_px=canvas.renderer.style.bond_length_px,
        center_3d=center_3d,
        anchor_2d=anchor_2d,
    )


def bond_offset_unit_3d_for(
    canvas,
    a_id: int,
    b_id: int,
    target: tuple[float, float, float] | None = None,
) -> tuple[float, float] | None:
    return canvas.render_context.geometry.bond_offset_unit_3d(a_id, b_id, target)


def ring_center_for_bond_for(canvas, bond):
    return canvas.render_context.geometry.ring_center_for_bond(bond)


def ring_center_3d_for_bond_for(canvas, bond):
    return canvas.render_context.geometry.ring_center_3d_for_bond(bond)


def apply_color_to_bond_item_for(canvas, item, color) -> None:
    apply_color_to_bond_item(item, color)


__all__ = [
    "add_bond_graphics_for",
    "apply_color_to_bond_item_for",
    "bond_offset_unit_3d_for",
    "line_normal_components",
    "line_normal_for",
    "orient_normal_toward_target",
    "parallel_bond_segments_for",
    "project_point_3d_for",
    "ring_center_3d_for_bond_for",
    "ring_center_for_bond_for",
    "ring_double_segments_for",
]
