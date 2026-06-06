from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon, QPainter
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_icon_pixmap_factory import MainWindowIconPixmapFactory


def _opaque_pixel_count(image) -> int:
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window icon pixmap factory tests")
class MainWindowIconPixmapFactoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_make_icon_uses_default_size_and_hidpi_backing_store(self) -> None:
        factory = MainWindowIconPixmapFactory(default_size=30, device_pixel_ratio=lambda: 2.0)

        def draw(painter: QPainter) -> None:
            painter.setPen(Qt.GlobalColor.black)
            painter.drawLine(5, 5, 25, 25)

        icon = factory.make_icon(draw)
        pixmap = icon.pixmap(30, 30)

        self.assertIn((60, 60), [(size.width(), size.height()) for size in icon.availableSizes()])
        self.assertFalse(pixmap.isNull())
        self.assertGreater(_opaque_pixel_count(pixmap.toImage()), 0)

    def test_make_icon_accepts_size_override(self) -> None:
        factory = MainWindowIconPixmapFactory(default_size=30, device_pixel_ratio=lambda: 1.0)

        icon = factory.make_icon(lambda painter: painter.drawPoint(5, 5), size=18)

        self.assertIn((18, 18), [(size.width(), size.height()) for size in icon.availableSizes()])

    def test_make_icon_registers_visible_checked_and_active_states(self) -> None:
        factory = MainWindowIconPixmapFactory(default_size=30, device_pixel_ratio=lambda: 1.0)

        def draw(painter: QPainter) -> None:
            painter.setPen(Qt.GlobalColor.black)
            painter.drawLine(5, 5, 25, 25)

        icon = factory.make_icon(draw)

        for mode in (
            QIcon.Mode.Normal,
            QIcon.Mode.Active,
            QIcon.Mode.Selected,
        ):
            for state in (QIcon.State.Off, QIcon.State.On):
                with self.subTest(mode=mode.name, state=state.name):
                    pixmap = icon.pixmap(20, 20, mode, state)
                    self.assertFalse(pixmap.isNull())
                    self.assertGreater(_opaque_pixel_count(pixmap.toImage()), 0)


if __name__ == "__main__":
    unittest.main()
