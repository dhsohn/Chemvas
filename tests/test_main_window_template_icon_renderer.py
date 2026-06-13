from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_template_icon_renderer import MainWindowTemplateIconRenderer


def _opaque_bounds(image) -> tuple[int, int, int, int] | None:
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _icon_pen(width: float | None = None, *, color=None, style=None) -> QPen:
    pen = QPen(QColor("#2f2f2c" if color is None else color))
    pen.setWidthF(1.6 if width is None else width)
    if style is not None:
        pen.setStyle(style)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


class _FakePainter:
    def __init__(self) -> None:
        self.polygons = 0
        self.lines = 0

    def setPen(self, _pen) -> None:
        pass

    def drawPolygon(self, _polygon) -> None:
        self.polygons += 1

    def drawLine(self, *_args) -> None:
        self.lines += 1


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window template icon renderer tests")
class MainWindowTemplateIconRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.renderer = MainWindowTemplateIconRenderer(
            icon_pen=_icon_pen,
            stroke_regular=1.8,
            stroke_thin=1.6,
        )

    def _render(self, draw) -> tuple[int, int, int, int] | None:
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw(painter)
        painter.end()
        return _opaque_bounds(pixmap.toImage())

    def test_template_preview_matrix_covers_ring_fragment_and_text_variants(self) -> None:
        labels = (
            "Benzene",
            "Naphthalene",
            "Cycloheptane",
            "Cyclooctane",
            "18-Crown-6",
            "Me",
            "Vinyl",
            "Carboxyl",
            "Nitro",
            "Unknown Template",
        )
        for label in labels:
            with self.subTest(label=label):
                bounds = self._render(lambda painter, label=label: self.renderer.draw_template_preview(painter, label))
                self.assertIsNotNone(bounds)

    def test_benzene_preview_icon_draws_aromatic_inner_bonds(self) -> None:
        benzene = _FakePainter()
        cyclopentane = _FakePainter()

        self.renderer.draw_template_preview(benzene, "Benzene")
        self.renderer.draw_template_preview(cyclopentane, "Cyclopentane")

        self.assertEqual(benzene.polygons, 1)
        self.assertEqual(benzene.lines, 3)
        self.assertEqual(cyclopentane.polygons, 1)
        self.assertEqual(cyclopentane.lines, 0)

    def test_templates_and_chair_preview_tolerate_empty_chair_geometry(self) -> None:
        with mock.patch("ui.main_window_template_icon_renderer.chair_icon_points", return_value=QPolygonF()):
            self.assertIsNone(self._render(self.renderer.draw_templates))
            self.assertIsNone(
                self._render(
                    lambda painter: self.renderer.draw_template_preview(
                        painter,
                        "Cyclohexane (Chair)",
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
