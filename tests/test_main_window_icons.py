import math
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
    from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QRectF = None
    QSize = None
    Qt = None
    QColor = None
    QPainter = None
    QPen = None
    QPixmap = None
    QPolygonF = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_icon_factory import MainWindowIconFactory


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


def _render_chair_bounds(factory: "MainWindowIconFactory", rect) -> tuple[int, int, int, int] | None:
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#3d3229"))
    pen.setWidthF(1.6)
    painter.setPen(pen)
    chair = factory.chair_icon_points(rect)
    if not chair.isEmpty():
        painter.drawPolygon(chair)
    painter.end()
    return _opaque_bounds(pixmap.toImage())


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window icon tests")
class MainWindowIconGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.factory = MainWindowIconFactory(self.window)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_ring_icon_inner_bond_matches_canvas_spacing_and_orientation(self) -> None:
        center = QPointF(15.0, 15.0)
        outer = self.factory.benzene_icon_polygon(center, 10.0)
        base_segments = self.factory.benzene_icon_inner_segments(outer, center)
        inner_segments = self.factory.benzene_icon_inner_segments(outer, center, spacing_scale=0.92)

        self.assertEqual(len(base_segments), 3)
        self.assertEqual(len(inner_segments), 3)

        base_start, base_end = base_segments[0]
        start, end = inner_segments[0]
        self.assertAlmostEqual(start.x(), end.x(), places=2)
        self.assertGreater(start.y(), outer[0].y())
        self.assertLess(end.y(), outer[1].y())

        outer_mid_x = (outer[0].x() + outer[1].x()) / 2.0
        base_inner_mid_x = (base_start.x() + base_end.x()) / 2.0
        inner_mid_x = (start.x() + end.x()) / 2.0
        icon_bond_length = math.hypot(outer[1].x() - outer[0].x(), outer[1].y() - outer[0].y())
        expected_base_spacing = icon_bond_length * (
            self.window.canvas.renderer.style.bond_spacing_px * 1.1
            / self.window.canvas.renderer.style.bond_length_px
        )

        self.assertAlmostEqual(outer_mid_x - base_inner_mid_x, expected_base_spacing, places=2)
        self.assertGreater(outer_mid_x - inner_mid_x, outer_mid_x - base_inner_mid_x)
        self.assertGreater(inner_mid_x, center.x())

    def test_ring_icon_fills_toolbar_icon_size_more_like_canvas_preview(self) -> None:
        pixmap = self.factory.icon_ring().pixmap(26, 26)
        image = pixmap.toImage()
        bounds = _opaque_bounds(image)
        self.assertIsNotNone(bounds)
        min_x, min_y, max_x, max_y = bounds
        self.assertGreaterEqual(max_x - min_x + 1, 22)
        self.assertGreaterEqual(max_y - min_y + 1, 24)

    def test_chair_template_icons_use_larger_geometry(self) -> None:
        old_bounds = _render_chair_bounds(self.factory, QRectF(4.0, 7.0, 22.0, 16.0))
        toolbar_bounds = _opaque_bounds(self.factory.icon_templates().pixmap(26, 26).toImage())
        preview_bounds = _opaque_bounds(
            self.factory.icon_template_preview("Cyclohexane (Chair)").pixmap(26, 26).toImage()
        )

        self.assertIsNotNone(old_bounds)
        self.assertIsNotNone(toolbar_bounds)
        self.assertIsNotNone(preview_bounds)

        old_min_x, old_min_y, old_max_x, old_max_y = old_bounds
        toolbar_min_x, toolbar_min_y, toolbar_max_x, toolbar_max_y = toolbar_bounds
        preview_min_x, preview_min_y, preview_max_x, preview_max_y = preview_bounds

        self.assertGreater(toolbar_max_x - toolbar_min_x + 1, old_max_x - old_min_x + 1)
        self.assertGreater(preview_max_x - preview_min_x + 1, old_max_x - old_min_x + 1)
        self.assertLessEqual(toolbar_min_x, old_min_x)
        self.assertLessEqual(preview_min_x, old_min_x)
        self.assertLessEqual(toolbar_min_y, old_min_y)
        self.assertLessEqual(preview_min_y, old_min_y)

    def test_canvas_dependent_wedge_icon_renders_non_empty_bounds(self) -> None:
        bounds = _opaque_bounds(self.factory.icon_bond_wedge().pixmap(30, 30).toImage())
        self.assertIsNotNone(bounds)

    def test_benzene_inner_segments_handle_short_and_zero_length_polygons(self) -> None:
        center = QPointF(15.0, 15.0)

        self.assertEqual(self.factory.benzene_icon_inner_segments(QPolygonF([center]), center), [])
        self.assertEqual(
            self.factory.benzene_icon_inner_segments(QPolygonF([center, center]), center),
            [],
        )

    def test_basic_toolbar_icons_render_non_empty_bounds(self) -> None:
        for icon in (
            self.factory.icon_add_sheet(),
            self.factory.icon_info(),
            self.factory.icon_bond_double(),
            self.factory.icon_bond_triple(),
            self.factory.icon_orbital(),
            self.factory.icon_move(),
        ):
            self.assertIsNotNone(_opaque_bounds(icon.pixmap(30, 30).toImage()))

    def test_shared_icon_size_and_pen_helpers_stay_consistent(self) -> None:
        expected_size = QSize(self.factory.ICON_SIZE, self.factory.ICON_SIZE)
        for icon in (
            self.factory.icon_ring(),
            self.factory.icon_save(),
            self.factory.icon_setup_sheet(),
            self.factory.icon_arrow(),
            self.factory.icon_color(),
            self.factory.icon_templates(),
        ):
            self.assertIn(expected_size, icon.availableSizes())

        default_pen = self.factory._icon_pen()
        active_pen = self.factory._icon_pen(self.factory.STROKE_ACTIVE)
        self.assertEqual(default_pen.color().name(), self.factory.STROKE_COLOR)
        self.assertAlmostEqual(default_pen.widthF(), self.factory.STROKE_THIN)
        self.assertEqual(active_pen.color().name(), self.factory.STROKE_COLOR)
        self.assertAlmostEqual(active_pen.widthF(), self.factory.STROKE_ACTIVE)

    def test_arrow_preview_matrix_renders_special_cases(self) -> None:
        for kind in ("reaction", "dotted", "curved_single", "curved_double", "equilibrium", "resonance", "inhibit"):
            bounds = _opaque_bounds(self.factory.icon_arrow_preview(kind).pixmap(30, 30).toImage())
            self.assertIsNotNone(bounds, kind)

    def test_orbital_preview_matrix_renders_distinct_families(self) -> None:
        for kind in ("s", "p", "sp", "sp2", "sp3", "d", "dz2"):
            bounds = _opaque_bounds(self.factory.icon_orbital_preview(kind).pixmap(30, 30).toImage())
            self.assertIsNotNone(bounds, kind)

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
            bounds = _opaque_bounds(self.factory.icon_template_preview(label).pixmap(30, 30).toImage())
            self.assertIsNotNone(bounds, label)

        self.assertEqual(self.factory.template_preview_ring_sides("Cycloheptane"), 7)
        self.assertEqual(self.factory.template_preview_ring_sides("Cyclooctane"), 8)

    def test_template_icons_tolerate_empty_chair_geometry_and_zero_rect(self) -> None:
        with mock.patch.object(self.factory, "chair_icon_points", return_value=QPolygonF()):
            self.assertIsNone(_opaque_bounds(self.factory.icon_templates().pixmap(30, 30).toImage()))
            self.assertIsNone(
                _opaque_bounds(self.factory.icon_template_preview("Cyclohexane (Chair)").pixmap(30, 30).toImage())
            )
