from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF

if TYPE_CHECKING:
    from chemvas.features.insertion import Molecule3DScene

ProjectedAtom = tuple[float, float, float, float]


def preview_projection_rect(
    widget_rect: QRectF,
    *,
    footer_height: float = 0.0,
    viewport_rect: QRectF | None = None,
) -> QRectF:
    if viewport_rect is not None:
        return QRectF(viewport_rect)
    content_rect = QRectF(widget_rect).adjusted(18.0, 18.0, -18.0, -18.0)
    if footer_height > 0.0:
        content_rect.setBottom(
            max(content_rect.top() + 40.0, content_rect.bottom() - footer_height)
        )
    return content_rect


def project_3d_scene(
    scene: Molecule3DScene,
    *,
    rotation_x: float,
    rotation_y: float,
    zoom: float,
    content_rect: QRectF,
) -> list[ProjectedAtom]:
    if not scene.atoms or content_rect.isEmpty():
        return []
    cx = sum(atom.x for atom in scene.atoms) / len(scene.atoms)
    cy = sum(atom.y for atom in scene.atoms) / len(scene.atoms)
    cz = sum(atom.z for atom in scene.atoms) / len(scene.atoms)

    rotated: list[tuple[float, float, float]] = []
    max_extent = 1.0
    cos_y = math.cos(rotation_y)
    sin_y = math.sin(rotation_y)
    cos_x = math.cos(rotation_x)
    sin_x = math.sin(rotation_x)
    for atom in scene.atoms:
        x = atom.x - cx
        y = atom.y - cy
        z = atom.z - cz
        x1 = x * cos_y + z * sin_y
        z1 = -x * sin_y + z * cos_y
        y1 = y * cos_x - z1 * sin_x
        z2 = y * sin_x + z1 * cos_x
        rotated.append((x1, y1, z2))
        max_extent = max(max_extent, math.sqrt(x1 * x1 + y1 * y1 + z2 * z2))

    available = max(40.0, min(content_rect.width(), content_rect.height()))
    scale = (available * 0.36) / max_extent
    center_x = content_rect.center().x()
    center_y = content_rect.top() + content_rect.height() * 0.55
    projected = []
    for atom, (x, y, z) in zip(scene.atoms, rotated, strict=False):
        depth = 7.0 / max(1.5, 7.0 - z)
        px = x * scale * depth
        py = -y * scale * depth
        base_radius = 6.0 if atom.symbol == "H" else 9.0
        radius = max(3.0, base_radius * depth)
        projected.append((px, py, z, radius))
    # Fit the depth-magnified footprint at zoom=1, including the existing
    # renderer's atom shadows and the widest bond's round shadow cap. Keep the
    # original framing whenever it already fits. Shrinking the radii as well
    # lets shallow, wide panels fit near-camera atoms without cutting them off.
    paint_margin = max(
        3.0,
        max(
            ((1.4 + max(0, bond.order - 1) + 1.8) / 2.0 + 2.2 for bond in scene.bonds),
            default=0.0,
        ),
    )
    fit = min(
        1.0,
        max(0.0, content_rect.width() * 0.5 - paint_margin)
        / max(abs(x) + radius * 1.04 for x, _y, _z, radius in projected),
        max(0.0, content_rect.height() * 0.45 - paint_margin)
        / max(abs(y) + radius * 1.04 for _x, y, _z, radius in projected),
    )
    # User zoom follows the fit: it can intentionally crop the molecule, but
    # must not be cancelled by another fit or change the atom radii with zoom.
    return [
        (center_x + x * fit * zoom, center_y + y * fit * zoom, z, radius * fit)
        for x, y, z, radius in projected
    ]


def project_preview_scene(
    scene: Molecule3DScene,
    *,
    rotation_x: float,
    rotation_y: float,
    zoom: float,
    widget_rect: QRectF,
    footer_height: float = 0.0,
    viewport_rect: QRectF | None = None,
) -> list[ProjectedAtom]:
    return project_3d_scene(
        scene,
        rotation_x=rotation_x,
        rotation_y=rotation_y,
        zoom=zoom,
        content_rect=preview_projection_rect(
            widget_rect,
            footer_height=footer_height,
            viewport_rect=viewport_rect,
        ),
    )


__all__ = [
    "ProjectedAtom",
    "preview_projection_rect",
    "project_3d_scene",
    "project_preview_scene",
]
