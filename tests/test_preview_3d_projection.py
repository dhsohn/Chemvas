from __future__ import annotations

from PyQt6.QtCore import QRectF

from chemvas.domain.chemistry_types import Molecule3DScene
from chemvas.ui.preview3d.preview_3d_layout import preview_layout_rects
from chemvas.ui.preview3d.preview_3d_projection import project_3d_scene


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
