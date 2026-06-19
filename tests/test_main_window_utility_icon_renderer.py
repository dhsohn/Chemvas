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
    from ui.main_window_utility_icon_renderer import MainWindowUtilityIconRenderer


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


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window utility icon renderer tests")
class MainWindowUtilityIconRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.renderer = MainWindowUtilityIconRenderer(
            icon_pen=_icon_pen,
            icon_brush=_icon_brush,
            stroke_thin=1.6,
            stroke_regular=1.8,
        )

    def _render(self, draw) -> tuple[int, int, int, int] | None:
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw(painter)
        painter.end()
        return _opaque_bounds(pixmap.toImage())

    def test_utility_icon_matrix_renders_non_empty_bounds(self) -> None:
        draw_methods = (
            self.renderer.draw_undo,
            self.renderer.draw_redo,
            self.renderer.draw_save,
            self.renderer.draw_open,
            self.renderer.draw_preview_panel,
            self.renderer.draw_add_sheet,
            self.renderer.draw_setup_sheet,
            self.renderer.draw_info,
        )
        for draw in draw_methods:
            with self.subTest(draw=draw.__name__):
                self.assertIsNotNone(self._render(draw))


if __name__ == "__main__":
    unittest.main()
