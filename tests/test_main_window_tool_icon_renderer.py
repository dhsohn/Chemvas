from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_tool_icon_renderer import MainWindowToolIconRenderer


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


def _icon_brush(color=None) -> QBrush:
    return QBrush(QColor("#2f2f2c" if color is None else color))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tool icon renderer tests")
class MainWindowToolIconRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.renderer = MainWindowToolIconRenderer(
            icon_pen=_icon_pen,
            icon_brush=_icon_brush,
            stroke_fine=1.2,
            stroke_thin=1.6,
            stroke_regular=1.8,
            stroke_molecule=2.0,
            stroke_active=2.2,
            icon_content_min=5,
            icon_content_max=25,
            icon_center=15,
            pale_fill_color="#ededeb",
            accent_fill_color="#d3d3ce",
        )

    def _render(self, draw) -> tuple[int, int, int, int] | None:
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw(painter)
        painter.end()
        return _opaque_bounds(pixmap.toImage())

    def test_tool_icon_matrix_renders_non_empty_bounds(self) -> None:
        draw_methods = (
            self.renderer.draw_select,
            self.renderer.draw_mark_plus,
            self.renderer.draw_mark_minus,
            self.renderer.draw_mark_radical,
            self.renderer.draw_text,
            self.renderer.draw_ring_fill,
            self.renderer.draw_flip_h,
            self.renderer.draw_flip_v,
            self.renderer.draw_ts_bracket,
            self.renderer.draw_orbital,
            self.renderer.draw_move,
            self.renderer.draw_color,
            self.renderer.draw_perspective,
        )
        for draw in draw_methods:
            with self.subTest(draw=draw.__name__):
                self.assertIsNotNone(self._render(draw))

    def test_orbital_preview_matrix_renders_distinct_families(self) -> None:
        for kind in ("s", "p", "sp", "sp2", "sp3", "d", "dz2"):
            with self.subTest(kind=kind):
                self.assertIsNotNone(
                    self._render(lambda painter, kind=kind: self.renderer.draw_orbital_preview(painter, kind))
                )


if __name__ == "__main__":
    unittest.main()
