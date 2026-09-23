from __future__ import annotations

import math

from PyQt6.QtCore import QRectF

from chemvas.features.insertion import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from chemvas.ui.preview_3d_layout import preview_layout_rects
from chemvas.ui.preview_3d_projection import project_3d_scene


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
    assert (
        project_3d_scene(
            Molecule3DScene(atoms=(), bonds=()),
            rotation_x=0.0,
            rotation_y=0.0,
            zoom=1.0,
            content_rect=QRectF(0.0, 0.0, 100.0, 100.0),
        )
        == []
    )


def test_preview_layout_reserves_footer_space_outside_molecular_content() -> None:
    widget_rect = QRectF(0.0, 0.0, 320.0, 420.0)
    plain_layout = preview_layout_rects(widget_rect, footer_height=0.0)
    footer_layout = preview_layout_rects(widget_rect, footer_height=60.0)
    without_footer = plain_layout["molecule"]
    with_footer = footer_layout["molecule"]

    assert with_footer.top() == without_footer.top()
    assert with_footer.bottom() < without_footer.bottom()
    assert with_footer.height() >= 40.0
    assert plain_layout["footer"].isNull()
    assert footer_layout["footer"].height() == 60.0
    assert footer_layout["viewport"].contains(with_footer)
    assert with_footer.bottom() < footer_layout["footer"].top()


def test_project_3d_scene_keeps_atoms_inside_content_rect_and_scales_with_zoom() -> (
    None
):
    content_rect = QRectF(40.0, 70.0, 220.0, 120.0)

    projected = project_3d_scene(
        _scene(),
        rotation_x=math.radians(-18.0),
        rotation_y=math.radians(22.0),
        zoom=1.0,
        content_rect=content_rect,
    )
    zoomed = project_3d_scene(
        _scene(),
        rotation_x=math.radians(-18.0),
        rotation_y=math.radians(22.0),
        zoom=1.8,
        content_rect=content_rect,
    )

    assert len(projected) == 3
    assert all(
        content_rect.left() <= atom[0] <= content_rect.right() for atom in projected
    )
    assert all(
        content_rect.top() <= atom[1] <= content_rect.bottom() for atom in projected
    )
    assert zoomed[0][3] == projected[0][3]
    assert max(abs(atom[0] - content_rect.center().x()) for atom in zoomed) > max(
        abs(atom[0] - content_rect.center().x()) for atom in projected
    )
