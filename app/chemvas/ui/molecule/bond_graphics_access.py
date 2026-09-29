from __future__ import annotations

from chemvas.domain.document.perspective import project_point_3d
from chemvas.ui.molecule.bond_graphics_build_service import apply_color_to_bond_item


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
    return project_point_3d(
        point,
        bond_length_px=canvas.renderer.style.bond_length_px,
        center_3d=center_3d,
        anchor_2d=rotation.projection_anchor_2d if anchor_2d is None else anchor_2d,
    )


def apply_color_to_bond_item_for(canvas, item, color) -> None:
    apply_color_to_bond_item(item, color)


__all__ = [
    "apply_color_to_bond_item_for",
    "project_point_3d_for",
]
