from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_bond_icon_renderer import MainWindowBondIconRenderer
    from ui.main_window_icon_geometry import benzene_icon_polygon


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


class _FakeStyle:
    def bond_length_px(self) -> float:
        return 20.0

    def bond_pen(self) -> QPen:
        pen = QPen()
        pen.setWidthF(1.5)
        return pen

    def bold_bond_pen(self) -> QPen:
        pen = QPen()
        pen.setWidthF(5.0)
        return pen

    def dotted_bond_pen(self) -> QPen:
        pen = QPen()
        pen.setWidthF(2.0)
        pen.setStyle(Qt.PenStyle.DotLine)
        return pen

    def hash_spacing_px(self) -> float:
        return 4.0

    def ring_double_inner_segment(self, start: QPointF, end: QPointF, center: QPointF):
        return (start.x() + 1.0, start.y(), end.x() + 1.0, end.y())


def _icon_pen(width: float | None = None, *, color=None, style=None) -> QPen:
    pen = QPen(QColor("#2f2f2c" if color is None else color))
    pen.setWidthF(1.6 if width is None else width)
    if style is not None:
        pen.setStyle(style)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _renderer_icon_pen(pen: QPen) -> QPen:
    icon_pen = QPen(pen)
    icon_pen.setColor(QColor("#2f2f2c"))
    icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    icon_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return icon_pen


def _icon_brush(color=None) -> QBrush:
    return QBrush(QColor("#2f2f2c" if color is None else color))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window bond icon renderer tests")
class MainWindowBondIconRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.renderer = MainWindowBondIconRenderer(
            canvas_style=_FakeStyle(),
            icon_pen=_icon_pen,
            renderer_icon_pen=_renderer_icon_pen,
            icon_brush=_icon_brush,
            stroke_active=2.2,
            stroke_thin=1.6,
            stroke_regular=1.8,
            stroke_molecule=2.0,
            icon_size=30,
        )

    def _render(self, draw) -> tuple[int, int, int, int] | None:
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw(painter)
        painter.end()
        return _opaque_bounds(pixmap.toImage())

    def test_draw_methods_render_non_empty_shapes(self) -> None:
        for draw in (
            self.renderer.draw_bond,
            self.renderer.draw_bold_bond,
            self.renderer.draw_ring,
            self.renderer.draw_double_bond,
            self.renderer.draw_triple_bond,
            self.renderer.draw_wedge_bond,
            self.renderer.draw_hash_bond,
            self.renderer.draw_dotted_bond,
            self.renderer.draw_bond_length,
        ):
            self.assertIsNotNone(self._render(draw), draw.__name__)

    def test_benzene_inner_segments_handles_spacing_and_empty_inputs(self) -> None:
        center = QPointF(15.0, 15.0)
        polygon = benzene_icon_polygon(center, 10.0)

        base_segments = self.renderer.benzene_icon_inner_segments(polygon, center)
        pulled_segments = self.renderer.benzene_icon_inner_segments(polygon, center, spacing_scale=0.8)

        self.assertEqual(len(base_segments), 3)
        self.assertEqual(len(pulled_segments), 3)
        self.assertEqual(
            self.renderer.benzene_icon_inner_segments(QPolygonF([center]), center),
            [],
        )
        self.assertEqual(
            self.renderer.benzene_icon_inner_segments(QPolygonF([center, center]), center),
            [],
        )
        self.assertNotEqual(base_segments[0][0], pulled_segments[0][0])


if __name__ == "__main__":
    unittest.main()
