from __future__ import annotations

import math

from core.rdkit_types import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from PyQt6.QtCore import QRectF
from ui.preview_3d_projection import (
    preview_projection_rect,
    project_3d_scene,
    project_preview_scene,
)


def _scene() -> Molecule3DScene:
    return Molecule3DScene(
        atoms=(
            Molecule3DAtom("C", 0.0, 0.0, 0.0),
            Molecule3DAtom("H", 1.0, 0.5, 0.25),
            Molecule3DAtom("O", -0.8, 0.2, -0.4),
        ),
        bonds=(Molecule3DBond(0, 1, 1), Molecule3DBond(0, 2, 2)),
    )


def test_project_3d_scene_returns_empty_for_empty_scene() -> None:
    assert project_3d_scene(
        Molecule3DScene(atoms=(), bonds=()),
        rotation_x=0.0,
        rotation_y=0.0,
        zoom=1.0,
        content_rect=QRectF(0.0, 0.0, 100.0, 100.0),
    ) == []


def test_preview_projection_rect_uses_viewport_override_and_footer_space() -> None:
    widget_rect = QRectF(0.0, 0.0, 240.0, 180.0)
    viewport_rect = QRectF(20.0, 30.0, 120.0, 90.0)

    assert preview_projection_rect(widget_rect, viewport_rect=viewport_rect) == viewport_rect

    without_footer = preview_projection_rect(widget_rect)
    with_footer = preview_projection_rect(widget_rect, footer_height=60.0)

    assert with_footer.top() == without_footer.top()
    assert with_footer.bottom() < without_footer.bottom()
    assert with_footer.height() >= 40.0


def test_project_preview_scene_keeps_atoms_inside_content_rect_and_scales_with_zoom() -> None:
    content_rect = QRectF(40.0, 70.0, 220.0, 120.0)

    projected = project_preview_scene(
        _scene(),
        rotation_x=math.radians(-18.0),
        rotation_y=math.radians(22.0),
        zoom=1.0,
        widget_rect=QRectF(0.0, 0.0, 320.0, 260.0),
        viewport_rect=content_rect,
    )
    zoomed = project_preview_scene(
        _scene(),
        rotation_x=math.radians(-18.0),
        rotation_y=math.radians(22.0),
        zoom=1.8,
        widget_rect=QRectF(0.0, 0.0, 320.0, 260.0),
        viewport_rect=content_rect,
    )

    assert len(projected) == 3
    assert all(content_rect.left() <= atom[0] <= content_rect.right() for atom in projected)
    assert all(content_rect.top() <= atom[1] <= content_rect.bottom() for atom in projected)
    assert zoomed[0][3] == projected[0][3]
    assert max(abs(atom[0] - content_rect.center().x()) for atom in zoomed) > max(
        abs(atom[0] - content_rect.center().x()) for atom in projected
    )
