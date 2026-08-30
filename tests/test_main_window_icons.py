import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.shell.icon_factory import (
    _TEMPLATE_ICON_BY_LABEL,
    MainWindowIconFactory,
)
from chemvas.ui.main_window_config import TEMPLATE_ENTRY_SPECS


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


class MainWindowIconGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.factory = MainWindowIconFactory(self.window)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_ring_icon_fills_toolbar_icon_size_more_like_canvas_preview(self) -> None:
        pixmap = self.factory.icon_ring().pixmap(26, 26)
        image = pixmap.toImage()
        bounds = _opaque_bounds(image)
        self.assertIsNotNone(bounds)
        min_x, min_y, max_x, max_y = bounds
        self.assertGreaterEqual(max_x - min_x + 1, 16)
        self.assertGreaterEqual(max_y - min_y + 1, 18)

    def test_bond_glyph_icons_render_non_empty_bounds(self) -> None:
        for icon in (
            self.factory.icon_bond(),
            self.factory.icon_bond_bold(),
            self.factory.icon_bond_wedge(),
            self.factory.icon_bond_hash(),
            self.factory.icon_bond_dotted(),
            self.factory.icon_ring(),
        ):
            self.assertIsNotNone(_opaque_bounds(icon.pixmap(30, 30).toImage()))

    def test_basic_toolbar_icons_render_non_empty_bounds(self) -> None:
        for icon in (
            self.factory.icon_select(),
            self.factory.icon_text(),
            self.factory.icon_note(),
            self.factory.icon_eraser(),
            self.factory.icon_bond_double(),
            self.factory.icon_bond_triple(),
            self.factory.icon_orbital(),
            self.factory.icon_shape(),
            self.factory.icon_perspective(),
        ):
            self.assertIsNotNone(_opaque_bounds(icon.pixmap(30, 30).toImage()))

    def test_shared_icon_size_stays_consistent(self) -> None:
        expected_size = QSize(self.factory.ICON_SIZE, self.factory.ICON_SIZE)
        for icon in (
            self.factory.icon_ring(),
            self.factory.icon_ring_fill(),
            self.factory.icon_eraser(),
            self.factory.icon_arrow(),
            self.factory.icon_color(),
            self.factory.icon_select(),
            self.factory.icon_ts_bracket(),
            self.factory.icon_perspective(),
        ):
            self.assertIn(expected_size, icon.availableSizes())

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
            bounds = _opaque_bounds(
                self.factory.icon_arrow_preview(kind).pixmap(30, 30).toImage()
            )
            self.assertIsNotNone(bounds, kind)
        for icon in (
            self.factory.icon_arrow_preset("Default"),
            self.factory.icon_arrow_preset("Bold"),
            self.factory.icon_arrow_preset("Fine"),
            self.factory.icon_arrow_width(),
            self.factory.icon_arrow_head_scale(),
        ):
            self.assertIsNotNone(_opaque_bounds(icon.pixmap(30, 30).toImage()))

    def test_orbital_preview_matrix_renders_distinct_families(self) -> None:
        for kind in ("s", "p", "sp", "sp2", "sp3", "d", "dz2"):
            bounds = _opaque_bounds(
                self.factory.icon_orbital_preview(kind).pixmap(30, 30).toImage()
            )
            self.assertIsNotNone(bounds, kind)

    def test_template_preview_mapping_covers_active_template_catalog(self) -> None:
        labels = tuple(label for label, _ring_size, _style in TEMPLATE_ENTRY_SPECS)
        self.assertEqual(set(_TEMPLATE_ICON_BY_LABEL), set(labels))
        for label in labels:
            bounds = _opaque_bounds(
                self.factory.icon_template_preview(label).pixmap(30, 30).toImage()
            )
            self.assertIsNotNone(bounds, label)
