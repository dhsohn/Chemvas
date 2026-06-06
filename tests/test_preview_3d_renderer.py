from __future__ import annotations

from core.rdkit_types import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication
from ui.preview_3d_molecule_renderer import (
    draw_projected_scene,
    preview_element_color,
)
from ui.preview_3d_renderer import draw_panel


def _has_non_background_pixel(image: QImage, background: QColor) -> bool:
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y) != background:
                return True
    return False


def test_preview_element_color_uses_known_palette_and_fallback() -> None:
    assert preview_element_color("O").name() == "#cc584d"
    assert preview_element_color("Cl").name() == "#5f955e"
    assert preview_element_color("Xe").name() == "#cfcfca"


def test_preview_renderer_draws_panel_and_projected_scene_to_image() -> None:
    app = QApplication.instance() or QApplication([])
    background = QColor("#ffffff")
    image = QImage(160, 120, QImage.Format.Format_ARGB32)
    image.fill(background)
    painter = QPainter(image)
    try:
        draw_panel(painter, QRectF(image.rect()))
        draw_projected_scene(
            painter,
            Molecule3DScene(
                atoms=(
                    Molecule3DAtom("C", 0.0, 0.0, 0.0),
                    Molecule3DAtom("O", 1.0, 0.0, 0.0),
                ),
                bonds=(Molecule3DBond(0, 1, 2),),
            ),
            [(55.0, 60.0, 0.0, 9.0), (95.0, 60.0, 0.4, 9.0)],
        )
    finally:
        painter.end()

    assert _has_non_background_pixel(image, background)
    assert app is not None
