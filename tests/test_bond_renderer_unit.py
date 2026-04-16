import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None
    Qt = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.bond_renderer import BondRenderer
    from ui.graphics_items import NoSelectLineItem, NoSelectPathItem, NoSelectPolygonItem


class _FakeStyle:
    bond_spacing_px = 4.0
    bond_line_width = 1.2
    bold_bond_width = 2.4
    hash_spacing_px = 4.0
    bond_length_px = 20.0
    bond_color = "#224466"


class _FakeRenderer:
    def __init__(self) -> None:
        self.style = _FakeStyle()

    def bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.style.bond_line_width)
        return pen

    def bold_bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.style.bold_bond_width)
        return pen

    def dotted_bond_pen(self) -> QPen:
        pen = self.bond_pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        return pen


class _FakeCanvas:
    def __init__(self) -> None:
        self.renderer = _FakeRenderer()
        self.model = SimpleNamespace(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
                2: Atom("C", 0.0, 10.0),
            },
            bonds=[],
        )
        self.bond_items: dict[int, list] = {}
        self._trim = (0.0, 1.0)
        self._offset_unit = None
        self._coords_3d: dict[int, tuple[float, float, float] | None] = {}
        self._labels: dict[int, object] = {}
        self._ring_center = None
        self._ring_center_3d = None
        self._normal = (0.0, 1.0)
        self._atom_bond_ids: dict[int, set[int]] = {}
        self._scene = QGraphicsScene()
        self.selectable_items: list = []
        self.colored_items: list[tuple[object, QColor]] = []
        self.offset_targets: list[tuple[int, int, object]] = []

    def scene(self) -> QGraphicsScene:
        return self._scene

    def _trim_line_for_labels(self, a_id, b_id, x1, y1, x2, y2):
        return self._trim

    def _bond_offset_unit_3d(self, a_id, b_id, target=None):
        self.offset_targets.append((a_id, b_id, target))
        return self._offset_unit

    def _current_atom_coords_3d(self, atom_id: int):
        return self._coords_3d.get(atom_id)

    def _project_point_3d(self, point):
        return point[0], point[1]

    def _label_rect_for_atom(self, atom_id: int):
        return self._labels.get(atom_id)

    def _ring_center_for_bond(self, bond):
        return self._ring_center

    def _ring_center_3d_for_bond(self, bond):
        return self._ring_center_3d

    def _line_normal(self, x1, y1, x2, y2, ring_center):
        return self._normal

    def _make_selectable(self, item) -> None:
        self.selectable_items.append(item)

    def _apply_color_to_bond_item(self, item, color: QColor) -> None:
        self.colored_items.append((item, QColor(color)))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for bond renderer tests")
class BondRendererUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = _FakeCanvas()
        self.renderer = BondRenderer(self.canvas)

    def _set_bond(self, bond: Bond | None) -> None:
        self.canvas.model.bonds = [bond]
        self.canvas.bond_items = {}

    def test_reset_item_origin_and_basic_segment_helpers(self) -> None:
        line = NoSelectLineItem(0.0, 0.0, 1.0, 0.0)
        line.setPos(3.0, -2.0)
        self.renderer._reset_item_origin(None)
        self.renderer._reset_item_origin(line)

        self.assertEqual((line.pos().x(), line.pos().y()), (0.0, 0.0))
        self.assertIsNone(self.renderer._normalize_3d(0.0, 0.0, 0.0))
        self.assertEqual(self.renderer._normalize_3d(0.0, 3.0, 4.0), (0.0, 0.6, 0.8))
        self.assertEqual(self.renderer._scale_segment(0.0, 0.0, 10.0, 0.0, 1.0), (0.0, 0.0, 10.0, 0.0))
        scaled = self.renderer._scale_segment(0.0, 0.0, 10.0, 0.0, 1.2)
        self.assertAlmostEqual(scaled[0], -1.0)
        self.assertEqual(scaled[1:], (0.0, 11.0, 0.0))
        self.assertEqual(self.renderer._extend_segment(0.0, 0.0, 10.0, 0.0, 0.0), (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(self.renderer._extend_segment(0.0, 0.0, 10.0, 0.0, 2.0), (-2.0, 0.0, 12.0, 0.0))
        self.assertEqual(self.renderer._bold_out_scale(False, QPointF()), 1.0)
        self.assertEqual(self.renderer._bold_out_scale(True, None), 1.0)
        self.assertEqual(self.renderer._bold_out_scale(True, QPointF(1.0, 1.0)), 1.1)

    def test_wedge_polygon_and_parallel_segments_use_trim_and_offset(self) -> None:
        self.canvas._trim = (0.2, 0.8)
        polygon = self.renderer.wedge_polygon(0.0, 0.0, 10.0, 0.0, 0, 1)

        self.assertEqual(len(polygon), 3)
        self.assertAlmostEqual(polygon[0].x(), 2.6)
        self.assertAlmostEqual(polygon[0].y(), 0.0)
        self.assertAlmostEqual((polygon[1].y() + polygon[2].y()) / 2.0, 0.0)

        self.canvas._offset_unit = (0.0, 1.0, 0.0)
        segments = self.renderer.parallel_bond_segments(0.0, 0.0, 10.0, 0.0, 2, 0, 1)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], (2.0, -2.0, 8.0, -2.0))
        self.assertEqual(segments[1], (2.0, 2.0, 8.0, 2.0))

    def test_hash_segments_and_strip_polygon_cover_single_and_multiple_counts(self) -> None:
        self.canvas._trim = (0.1, 0.9)
        single = self.renderer.hash_segments(0.0, 0.0, 10.0, 0.0, 1, 0, 1)
        multiple = self.renderer.hash_segments(0.0, 0.0, 10.0, 0.0, 4, 0, 1)
        polygon = self.renderer.strip_polygon(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 1.0, 3.0)

        self.assertEqual(len(single), 1)
        self.assertEqual(single[0], (5.0, -1.2, 5.0, 1.2))
        self.assertEqual(len(multiple), 4)
        self.assertLess(multiple[0][3] - multiple[0][1], multiple[-1][3] - multiple[-1][1])
        self.assertEqual(
            [(point.x(), point.y()) for point in polygon],
            [(0.0, -0.5), (10.0, -0.5), (10.0, 2.5), (0.0, 2.5)],
        )

    def test_plain_double_segments_switch_which_side_is_shortened(self) -> None:
        outer_default, inner_default, normal = self.renderer.plain_double_segments(
            0.0,
            0.0,
            10.0,
            0.0,
            style="double",
            a_id=0,
            b_id=1,
        )
        outer_center, inner_center, _ = self.renderer.plain_double_segments(
            0.0,
            0.0,
            10.0,
            0.0,
            style="double_center",
            a_id=0,
            b_id=1,
        )
        outer_outer, inner_outer, _ = self.renderer.plain_double_segments(
            0.0,
            0.0,
            10.0,
            0.0,
            style="double_outer",
            a_id=0,
            b_id=1,
        )

        self.assertEqual(normal, (0.0, 1.0))
        self.assertEqual(outer_default, (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(inner_default, (1.2, 4.4, 8.8, 4.4))
        self.assertEqual(outer_center, (0.0, -2.2, 10.0, -2.2))
        self.assertEqual(inner_center, (0.0, 2.2, 10.0, 2.2))
        self.assertEqual(outer_outer, (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(inner_outer, (1.2, -4.4, 8.8, -4.4))

    def test_ring_double_segments_prefers_3d_projection_when_available(self) -> None:
        self.canvas._coords_3d = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        outer, inner, normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(5.0, 5.0, 0.0),
        )

        self.assertEqual(outer, (0.0, 0.0, 10.0, 0.0))
        self.assertGreater(inner[1], 0.0)
        self.assertGreater(inner[3], 0.0)
        self.assertAlmostEqual(normal[0], 0.0)
        self.assertAlmostEqual(normal[1], 1.0)

    def test_ring_double_segments_falls_back_to_2d_and_flips_toward_center(self) -> None:
        outer, inner, normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, -5.0),
            0,
            1,
        )

        self.assertEqual(outer, (0.0, 0.0, 10.0, 0.0))
        self.assertLess(inner[1], 0.0)
        self.assertLess(inner[3], 0.0)
        self.assertEqual(normal, (0.0, -1.0))

    def test_ring_double_segments_uses_offset_unit_and_label_trim_in_2d_fallback(self) -> None:
        self.canvas._offset_unit = (0.0, 1.0, 0.0)
        self.canvas._labels = {0: object(), 1: object()}

        outer, inner, normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 2.0),
            0,
            1,
            center_3d=(0.0, 0.0, 0.0),
        )

        self.assertEqual(outer, (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(normal, (0.0, 1.0))
        self.assertAlmostEqual(inner[0], 0.8)
        self.assertAlmostEqual(inner[2], 9.2)
        self.assertEqual(self.canvas.offset_targets[-1], (0, 1, (0.0, 0.0, 0.0)))

    def test_draw_helpers_create_expected_graphics_items(self) -> None:
        line_item = self.renderer.one_sided_bond_strip(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 2.0, 2.0)
        polygon_item = self.renderer.one_sided_bond_strip(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 1.0, 3.0)
        self.canvas._offset_unit = None
        parallel = self.renderer.draw_parallel_bonds(0.0, 0.0, 10.0, 0.0, 3, 0, 1)
        dotted = self.renderer.draw_dotted_bond(0.0, 0.0, 10.0, 0.0, 0, 1)
        wedge = self.renderer.draw_wedge_bond(0.0, 0.0, 10.0, 0.0, 0, 1)
        hashed = self.renderer.draw_hash_bond(0.0, 0.0, 10.0, 0.0, 0, 1)

        self.assertIsInstance(line_item, NoSelectLineItem)
        self.assertIsInstance(polygon_item, NoSelectPolygonItem)
        self.assertEqual(polygon_item.brush().color().name(), "#224466")
        self.assertEqual(len(parallel), 3)
        self.assertTrue(all(isinstance(item, NoSelectLineItem) for item in parallel))
        self.assertEqual(len(dotted), 1)
        self.assertIsInstance(dotted[0], NoSelectPathItem)
        self.assertFalse(dotted[0].path().isEmpty())
        self.assertEqual(dotted[0].pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(len(wedge), 1)
        self.assertIsInstance(wedge[0], NoSelectPolygonItem)
        self.assertGreaterEqual(len(hashed), 3)
        self.assertTrue(all(isinstance(item, NoSelectLineItem) for item in hashed))

    def test_draw_dotted_double_bond_dots_only_short_variant_segment(self) -> None:
        items = self.renderer.draw_dotted_double_bond(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            style="dotted_double",
            a_id=0,
            b_id=1,
        )

        self.assertEqual(len(items), 2)
        self.assertIsInstance(items[0], NoSelectLineItem)
        self.assertIsInstance(items[1], NoSelectPathItem)

    def test_draw_ring_double_bond_switches_outer_style(self) -> None:
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 2.0, 9.0, 2.0), (0.0, 1.0)),
        ):
            normal_items = self.renderer.draw_ring_double_bond(
                self.canvas.model.atoms[0],
                self.canvas.model.atoms[1],
                QPointF(5.0, 5.0),
            )
            bold_items = self.renderer.draw_ring_double_bond(
                self.canvas.model.atoms[0],
                self.canvas.model.atoms[1],
                QPointF(5.0, 5.0),
                outer_style="bold_outward",
            )

        self.assertIsInstance(normal_items[0], NoSelectLineItem)
        self.assertIsInstance(normal_items[1], NoSelectLineItem)
        self.assertIsInstance(bold_items[0], NoSelectPolygonItem)
        self.assertIsInstance(bold_items[1], NoSelectLineItem)

    def test_update_bond_geometry_returns_early_for_invalid_missing_or_empty_cases(self) -> None:
        self.canvas.model.bonds = []
        self.renderer.update_bond_geometry(0)
        self.canvas.model.bonds = [None]
        self.renderer.update_bond_geometry(0)
        self.canvas.model.bonds = [Bond(0, 1, 1)]
        self.renderer.update_bond_geometry(0)
        self.canvas.bond_items[0] = [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)]
        del self.canvas.model.atoms[1]
        self.renderer.update_bond_geometry(0)

    def test_update_bond_geometry_updates_wedge_hash_and_single_lines(self) -> None:
        wedge = QGraphicsPolygonItem(QPolygonF())
        self._set_bond(Bond(0, 1, 1, style="wedge"))
        self.canvas.bond_items[0] = [wedge]
        self.renderer.update_bond_geometry(0)
        self.assertEqual(len(wedge.polygon()), 3)

        hashed = [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0) for _ in range(3)]
        self._set_bond(Bond(0, 1, 1, style="hash"))
        self.canvas.bond_items[0] = hashed
        self.renderer.update_bond_geometry(0)
        self.assertNotEqual(hashed[0].line().length(), 0.0)

        dotted = QGraphicsPathItem()
        self._set_bond(Bond(0, 1, 1, style="dotted"))
        self.canvas.bond_items[0] = [dotted]
        self.renderer.update_bond_geometry(0)
        self.assertFalse(dotted.path().isEmpty())

        single = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        single.setPos(2.0, 3.0)
        self._set_bond(Bond(0, 1, 1, style="single"))
        self.canvas._trim = (0.1, 0.9)
        self.canvas.bond_items[0] = [single]
        self.renderer.update_bond_geometry(0)
        self.assertEqual((single.pos().x(), single.pos().y()), (0.0, 0.0))
        self.assertEqual((single.line().x1(), single.line().x2()), (1.0, 9.0))

    def test_update_bond_geometry_updates_bold_ring_parallel_and_single_paths(self) -> None:
        outer_polygon = QGraphicsPolygonItem(QPolygonF())
        inner_line = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 2, style="bold_out"))
        self.canvas._ring_center = QPointF(5.0, 5.0)
        self.canvas.bond_items[0] = [outer_polygon, inner_line]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual(len(outer_polygon.polygon()), 4)
        self.assertEqual((inner_line.line().x1(), inner_line.line().y1()), (1.0, 1.0))

        first = QGraphicsPolygonItem(QPolygonF())
        second = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 3, style="bold"))
        self.canvas._ring_center = None
        self.canvas.bond_items[0] = [first, second]
        self.renderer.update_bond_geometry(0)
        self.assertEqual(len(first.polygon()), 4)
        self.assertNotEqual(second.line().length(), 0.0)

        single = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 1, style="bold"))
        self.canvas.bond_items[0] = [single]
        self.renderer.update_bond_geometry(0)
        self.assertGreater(single.line().length(), 10.0)

    def test_update_bond_geometry_updates_double_and_higher_order_nonbold_paths(self) -> None:
        outer = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        inner = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 2, style="single"))
        self.canvas._ring_center = QPointF(5.0, 5.0)
        self.canvas.bond_items[0] = [outer, inner]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual((outer.line().x1(), outer.line().x2()), (0.0, 10.0))
        self.assertEqual((inner.line().x1(), inner.line().x2()), (1.0, 9.0))

        lines = [QGraphicsLineItem(0.0, 0.0, 1.0, 0.0) for _ in range(3)]
        self._set_bond(Bond(0, 1, 3, style="single"))
        self.canvas._ring_center = None
        self.canvas.bond_items[0] = lines
        self.renderer.update_bond_geometry(0)
        self.assertTrue(all(line.line().length() > 0.0 for line in lines))

    def test_add_bond_graphics_returns_early_for_none_bond(self) -> None:
        self._set_bond(None)
        self.renderer.add_bond_graphics(0)
        self.assertEqual(self.canvas.bond_items, {})

    def test_add_bond_graphics_covers_wedge_hash_single_and_dotted_paths(self) -> None:
        for style in ("wedge", "hash", "single", "dotted"):
            self.canvas._scene.clear()
            self._set_bond(Bond(0, 1, 1, style=style, color="#AA5500"))
            self.renderer.add_bond_graphics(0)
            items = self.canvas.bond_items[0]
            self.assertTrue(items)
            self.assertTrue(all(item.data(0) == "bond" and item.data(1) == 0 for item in items))
            if style == "dotted":
                self.assertIsInstance(items[0], NoSelectPathItem)
        self.assertTrue(self.canvas.selectable_items)
        self.assertTrue(self.canvas.colored_items)

    def test_add_bond_graphics_covers_dotted_double_paths(self) -> None:
        self._set_bond(Bond(0, 1, 2, style="dotted_double"))
        self.renderer.add_bond_graphics(0)
        items = self.canvas.bond_items[0]

        self.assertEqual(len(items), 2)
        self.assertIsInstance(items[0], NoSelectLineItem)
        self.assertIsInstance(items[1], NoSelectPathItem)

    def test_add_bond_graphics_covers_bold_paths(self) -> None:
        self.canvas._ring_center = QPointF(5.0, 5.0)
        self._set_bond(Bond(0, 1, 2, style="bold_out"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 2)
        self.assertIsInstance(self.canvas.bond_items[0][0], (NoSelectPolygonItem, NoSelectLineItem))

        self.canvas._scene.clear()
        self.canvas._ring_center = None
        self._set_bond(Bond(0, 1, 2, style="bold"))
        self.renderer.add_bond_graphics(0)
        self.assertIsInstance(self.canvas.bond_items[0][0], (NoSelectPolygonItem, NoSelectLineItem))

        self.canvas._scene.clear()
        self._set_bond(Bond(0, 1, 1, style="bold_out"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 1)
        self.assertIsInstance(self.canvas.bond_items[0][0], (NoSelectPolygonItem, NoSelectLineItem))

    def test_add_bond_graphics_covers_double_and_higher_order_nonbold_paths(self) -> None:
        self.canvas._ring_center = QPointF(5.0, 5.0)
        self._set_bond(Bond(0, 1, 2, style="single"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 2)

        self.canvas._scene.clear()
        self.canvas._ring_center = None
        self._set_bond(Bond(0, 1, 3, style="single"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 3)


if __name__ == "__main__":
    unittest.main()
