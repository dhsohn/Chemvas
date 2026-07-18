from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.main_window_arrow_icon_renderer import MainWindowArrowIconRenderer


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


@unittest.skipUnless(
    QApplication is not None,
    "PyQt6 is required for main window arrow icon renderer tests",
)
class MainWindowArrowIconRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.renderer = MainWindowArrowIconRenderer(
            icon_pen=_icon_pen,
            stroke_thin=1.6,
            stroke_active=2.2,
            icon_content_min=5,
            icon_center=15,
        )

    def _render(self, draw) -> tuple[int, int, int, int] | None:
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw(painter)
        painter.end()
        return _opaque_bounds(pixmap.toImage())

    def test_arrow_preview_matrix_renders_special_cases(self) -> None:
        for kind in (
            "reaction",
            "dotted",
            "curved_single",
            "curved_double",
            "equilibrium",
            "resonance",
            "inhibit",
        ):
            with self.subTest(kind=kind):
                bounds = self._render(
                    lambda painter, kind=kind: self.renderer.draw_arrow_preview(
                        painter, kind
                    )
                )
                self.assertIsNotNone(bounds)

    def test_arrow_head_and_basic_arrow_render_non_empty_shapes(self) -> None:
        self.assertIsNotNone(self._render(self.renderer.draw_arrow))
        self.assertIsNotNone(
            self._render(
                lambda painter: self.renderer.draw_arrow_preset(painter, "Default")
            )
        )
        self.assertIsNotNone(
            self._render(
                lambda painter: self.renderer.draw_arrow_preset(painter, "Bold")
            )
        )
        self.assertIsNotNone(
            self._render(
                lambda painter: self.renderer.draw_arrow_preset(painter, "Fine")
            )
        )
        self.assertIsNotNone(self._render(self.renderer.draw_arrow_width_control))
        self.assertIsNotNone(self._render(self.renderer.draw_arrow_head_control))
        self.assertIsNotNone(
            self._render(
                lambda painter: self.renderer.draw_arrow_head(
                    painter,
                    QPointF(5.0, 15.0),
                    QPointF(23.0, 15.0),
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
