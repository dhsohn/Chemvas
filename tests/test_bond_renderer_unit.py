import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainterPath, QPen, QPolygonF
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

if QApplication is not None:
    import ui.bond_graphics_build_service as bond_graphics_build_module
    import ui.bond_renderer as bond_renderer_module
    from core.model import Atom, Bond
    from core.renderer import Renderer
    from core.style_acs1996 import ACS1996Style
    from ui.bond_geometry_primitives import (
        bold_out_scale,
        extend_segment,
        normalize_3d,
        scale_segment,
        trim_segment,
    )
    from ui.bond_renderer import BondRenderer
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_graph_state import CanvasGraphState
    from ui.graphics_items import (
        NoSelectLineItem,
        NoSelectPathItem,
        NoSelectPolygonItem,
    )


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

    def bond_line_width(self) -> float:
        return self.style.bond_line_width

    def bold_bond_width(self) -> float:
        return self.style.bold_bond_width

    def bond_spacing(self) -> float:
        return self.style.bond_spacing_px

    def hash_spacing(self) -> float:
        return self.style.hash_spacing_px

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
        set_bond_items_for(self, {})
        self._trim = (0.0, 1.0)
        self.atom_coords_3d: dict[int, tuple[float, float, float]] = {}
        self._labels: dict[int, object] = {}
        self._ring_center = None
        self._ring_center_3d = None
        self._normal = (0.0, 1.0)
        self.graph_state = CanvasGraphState()
        self._scene = QGraphicsScene()
        self.selectable_items: list = []
        self.services = SimpleNamespace(
            geometry_controller=SimpleNamespace(
                trim_line_for_labels=self.trim_line_for_labels,
                label_rect_for_atom=self.label_rect_for_atom,
                ring_center_for_bond=lambda bond: self._ring_center,
                ring_center_3d_for_bond=lambda bond: self._ring_center_3d,
            )
        )

    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)

    def trim_line_for_labels(self, a_id, b_id, x1, y1, x2, y2):
        return self._trim

    def label_rect_for_atom(self, atom_id: int):
        return self._labels.get(atom_id)

    def _line_normal(self, x1, y1, x2, y2, ring_center):
        return self._normal

    def _make_selectable(self, item) -> None:
        self.selectable_items.append(item)

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
        set_bond_items_for(self.canvas, {})

    def test_reset_item_origin_and_basic_segment_helpers(self) -> None:
        line = NoSelectLineItem(0.0, 0.0, 1.0, 0.0)
        line.setPos(3.0, -2.0)
        self.renderer._reset_item_origin(None)
        self.renderer._reset_item_origin(line)

        self.assertEqual((line.pos().x(), line.pos().y()), (0.0, 0.0))
        self.assertIsNone(normalize_3d(0.0, 0.0, 0.0))
        self.assertEqual(normalize_3d(0.0, 3.0, 4.0), (0.0, 0.6, 0.8))
        self.assertEqual(scale_segment(0.0, 0.0, 10.0, 0.0, 1.0), (0.0, 0.0, 10.0, 0.0))
        scaled = scale_segment(0.0, 0.0, 10.0, 0.0, 1.2)
        self.assertAlmostEqual(scaled[0], -1.0)
        self.assertEqual(scaled[1:], (0.0, 11.0, 0.0))
        self.assertEqual(extend_segment(0.0, 0.0, 10.0, 0.0, 0.0), (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(extend_segment(0.0, 0.0, 10.0, 0.0, 2.0), (-2.0, 0.0, 12.0, 0.0))
        self.assertEqual(bold_out_scale(False, QPointF()), 1.0)
        self.assertEqual(bold_out_scale(True, None), 1.0)
        self.assertEqual(bold_out_scale(True, QPointF(1.0, 1.0)), 1.1)
        self.assertEqual(bold_out_scale(True, QPointF(), length_scale=1.2), 1.2)

    def test_update_bond_geometry_delegates_to_geometry_updater(self) -> None:
        updater = SimpleNamespace(update_bond_geometry=mock.Mock())
        self.renderer.geometry_updater = updater

        self.renderer.update_bond_geometry(12)

        updater.update_bond_geometry.assert_called_once_with(12)

    def test_add_bond_graphics_delegates_to_graphics_builder(self) -> None:
        builder = SimpleNamespace(add_bond_graphics=mock.Mock())
        self.renderer.graphics_builder = builder

        self.renderer.add_bond_graphics(7)

        builder.add_bond_graphics.assert_called_once_with(7)

    def test_draw_helpers_delegate_to_graphics_drawer(self) -> None:
        drawer = SimpleNamespace(
            draw_ring_double_bond=mock.Mock(return_value=["ring"]),
            one_sided_bond_strip=mock.Mock(return_value="strip"),
            draw_parallel_bonds=mock.Mock(return_value=["parallel"]),
            draw_dotted_bond=mock.Mock(return_value=["dotted"]),
            draw_dotted_double_bond=mock.Mock(return_value=["dotted-double"]),
            draw_wedge_bond=mock.Mock(return_value=["wedge"]),
            draw_hash_bond=mock.Mock(return_value=["hash"]),
        )
        self.renderer.graphics_drawer = drawer
        atom_a = self.canvas.model.atoms[0]
        atom_b = self.canvas.model.atoms[1]
        center = QPointF(5.0, 5.0)

        self.assertEqual(self.renderer.draw_ring_double_bond(atom_a, atom_b, center, 0, 1), ["ring"])
        self.assertEqual(self.renderer.one_sided_bond_strip(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), "strip")
        self.assertEqual(self.renderer.draw_parallel_bonds(1.0, 2.0, 3.0, 4.0, 2, 0, 1), ["parallel"])
        self.assertEqual(self.renderer.draw_dotted_bond(1.0, 2.0, 3.0, 4.0, 0, 1), ["dotted"])
        self.assertEqual(
            self.renderer.draw_dotted_double_bond(atom_a, atom_b, style="dotted_double", a_id=0, b_id=1),
            ["dotted-double"],
        )
        self.assertEqual(self.renderer.draw_wedge_bond(1.0, 2.0, 3.0, 4.0, 0, 1), ["wedge"])
        self.assertEqual(self.renderer.draw_hash_bond(1.0, 2.0, 3.0, 4.0, 0, 1), ["hash"])

        drawer.draw_ring_double_bond.assert_called_once_with(
            atom_a,
            atom_b,
            center,
            0,
            1,
            outer_style="normal",
            center_3d=None,
            style="double",
        )
        drawer.one_sided_bond_strip.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        drawer.draw_parallel_bonds.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 0, 1)
        drawer.draw_dotted_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0, 1)
        drawer.draw_dotted_double_bond.assert_called_once_with(
            atom_a,
            atom_b,
            style="dotted_double",
            a_id=0,
            b_id=1,
            ring_center=None,
            center_3d=None,
        )
        drawer.draw_wedge_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0, 1)
        drawer.draw_hash_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0, 1)

    def test_ring_double_segments_delegates_to_ring_geometry_service(self) -> None:
        service = SimpleNamespace(ring_double_segments=mock.Mock(return_value=("outer", "inner", "normal")))
        self.renderer.ring_double_geometry = service
        atom_a = self.canvas.model.atoms[0]
        atom_b = self.canvas.model.atoms[1]
        center = QPointF(5.0, 5.0)

        self.assertEqual(
            self.renderer.ring_double_segments(
                atom_a,
                atom_b,
                center,
                0,
                1,
                (5.0, 5.0, 0.0),
                "double_outer",
            ),
            ("outer", "inner", "normal"),
        )

        service.ring_double_segments.assert_called_once_with(
            atom_a,
            atom_b,
            center,
            0,
            1,
            (5.0, 5.0, 0.0),
            "double_outer",
        )

    def test_wedge_polygon_and_parallel_segments_use_trim_and_offset(self) -> None:
        self.canvas._trim = (0.2, 0.8)
        polygon = self.renderer.wedge_polygon(0.0, 0.0, 10.0, 0.0, 0, 1)

        self.assertEqual(len(polygon), 3)
        self.assertAlmostEqual(polygon[0].x(), 2.6)
        self.assertAlmostEqual(polygon[0].y(), 0.0)
        self.assertAlmostEqual((polygon[1].y() + polygon[2].y()) / 2.0, 0.0)

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

    def test_helper_edge_guards_cover_invalid_ids_and_label_driven_paths(self) -> None:
        self.canvas.graph_state.atom_bond_ids = {0: {0, 99}, 1: {0, 1}}
        self.canvas.model.bonds = [Bond(0, 1, 1), Bond(2, 1, 1)]
        del self.canvas.model.atoms[2]

        trim = self.renderer.line_geometry._junction_trim_for_atom(0, 1)
        self.assertGreater(trim, 0.0)
        self.assertEqual(trim_segment((0.0, 0.0, 10.0, 0.0), 0.0), (0.0, 0.0, 10.0, 0.0))
        self.assertIsNone(self.renderer.line_geometry._double_neighbor_target(0, 1))

        self.canvas.model.atoms[2] = Atom("C", 2.0, 6.0)
        self.canvas.graph_state.atom_bond_ids = {0: {0, 1}, 1: {0}}
        self.assertIsNotNone(self.renderer.line_geometry._double_neighbor_target(0, 1))
        self.assertEqual(self.renderer.line_geometry._plain_double_normal(0.0, 0.0, 10.0, 0.0, 0, 1), (0.0, 1.0))

        self.canvas._labels = {0: object(), 1: object()}
        outer, inner, _ = self.renderer.plain_double_segments(
            0.0,
            0.0,
            10.0,
            0.0,
            style="double_outer",
            a_id=0,
            b_id=1,
        )
        self.assertEqual(outer, (0.0, 0.0, 10.0, 0.0))
        self.assertAlmostEqual(inner[0], 0.8)
        self.assertAlmostEqual(inner[2], 9.2)

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
        self.canvas.atom_coords_3d = {
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

    def test_ring_double_segments_scale_spacing_with_short_bond_length(self) -> None:
        self.canvas.renderer = Renderer(ACS1996Style(bond_length_px=10.0))

        outer, inner, _ = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
        )

        self.assertEqual(outer, (0.0, 0.0, 10.0, 0.0))
        self.assertAlmostEqual(inner[1], 2.42)
        self.assertAlmostEqual(inner[3], 2.42)

    def test_ring_double_segments_cover_3d_variants_and_fallback_guards(self) -> None:
        self.canvas.atom_coords_3d = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        self.canvas._labels = {0: object(), 1: object()}
        self.renderer.project_point_3d = lambda point: (point[0], point[1] + point[2])

        default_outer, default_inner, _ = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(5.0, 5.0, 5.0),
        )
        center_outer, center_inner, _ = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(5.0, 5.0, 5.0),
            style="double_center",
        )
        outer_outer, outer_inner, _ = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(5.0, 5.0, 5.0),
            style="double_outer",
        )

        self.assertEqual(default_outer, (0.0, 0.0, 10.0, 0.0))
        self.assertAlmostEqual(default_inner[0], 0.8)
        self.assertAlmostEqual(center_outer[0], 0.0)
        self.assertAlmostEqual(center_inner[0], 0.0)
        self.assertGreater(outer_outer[0], 0.0)
        self.assertLess(outer_outer[2], 10.0)
        self.assertAlmostEqual(outer_inner[0], 0.0)
        self.assertAlmostEqual(outer_inner[2], 10.0)

        self.renderer.project_point_3d = lambda point: (point[0], point[1])
        zero_offset_outer, zero_offset_inner, zero_offset_normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(5.0, 0.0, 5.0),
        )
        self.assertEqual(zero_offset_outer, (0.0, 0.0, 10.0, 0.0))
        self.assertGreater(zero_offset_inner[1], 0.0)
        self.assertEqual(zero_offset_normal, (0.0, 1.0))

        self.canvas.atom_coords_3d = {
            0: (0.0, 0.0, 0.0),
            1: (0.0, 0.0, 0.0),
        }
        collapsed_outer, _, collapsed_normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(5.0, 5.0, 0.0),
        )
        self.assertEqual(collapsed_outer, (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(collapsed_normal, (0.0, 1.0))

        self.canvas.atom_coords_3d = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        axial_outer, _, axial_normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
            center_3d=(15.0, 0.0, 0.0),
        )
        self.assertEqual(axial_outer, (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(axial_normal, (0.0, 1.0))

        centered_outer, centered_inner, centered_normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, -5.0),
            0,
            1,
            style="double_center",
        )
        outer_outer_2d, outer_inner_2d, outer_normal_2d = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, -5.0),
            0,
            1,
            style="double_outer",
        )
        self.assertEqual(centered_normal, (0.0, -1.0))
        self.assertLess(centered_inner[1], 0.0)
        self.assertLess(outer_outer_2d[0], 1.0)
        self.assertGreater(outer_outer_2d[0], 0.0)
        self.assertLess(outer_inner_2d[1], 0.0)
        self.assertEqual(outer_normal_2d, (0.0, -1.0))

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

    def test_draw_helpers_create_expected_graphics_items(self) -> None:
        line_item = self.renderer.one_sided_bond_strip(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 2.0, 2.0)
        polygon_item = self.renderer.one_sided_bond_strip(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 1.0, 3.0)
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

    def test_draw_dotted_double_and_parallel_bonds_cover_ring_center_and_default_offsets(self) -> None:
        segments = self.renderer.parallel_bond_segments(0.0, 0.0, 10.0, 0.0, 4, 0, 1)
        items = self.renderer.draw_parallel_bonds(0.0, 0.0, 10.0, 0.0, 4, 0, 1)
        self.assertEqual(segments, [(0.0, 0.0, 10.0, 0.0)])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].line().y1(), 0.0)

        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ) as ring_segments:
            dotted_items = self.renderer.draw_dotted_double_bond(
                self.canvas.model.atoms[0],
                self.canvas.model.atoms[1],
                style="dotted_double_outer",
                a_id=0,
                b_id=1,
                ring_center=QPointF(5.0, 5.0),
                center_3d=(1.0, 2.0, 3.0),
            )
        ring_segments.assert_called_once()
        self.assertIsInstance(dotted_items[0], NoSelectPathItem)
        self.assertIsInstance(dotted_items[1], NoSelectLineItem)

    def test_junction_trim_and_dotted_bond_path_cover_guard_scaling_and_midpoint_cases(self) -> None:
        self.assertEqual(self.renderer.line_geometry._junction_trim_for_atom(None, 1), 0.0)

        self.canvas.graph_state.atom_bond_ids = {0: {0, 1, 2}}
        self.canvas.model.bonds = [Bond(0, 1, 1), None, Bond(0, 2, 1)]
        self.assertGreater(self.renderer.line_geometry._junction_trim_for_atom(0, 1), 0.0)

        self.canvas.graph_state.atom_bond_ids = {0: {0}}
        self.canvas.model.bonds = [Bond(0, 1, 1)]
        self.assertEqual(self.renderer.line_geometry._junction_trim_for_atom(0, 1), 0.0)

        zero_length_path = self.renderer.dotted_bond_path(1.0, 2.0, 1.0, 2.0)
        self.assertFalse(zero_length_path.isEmpty())

        with mock.patch.object(self.renderer.line_geometry, "_junction_trim_for_atom", side_effect=[5.0, 5.0]):
            midpoint_path = self.renderer.dotted_bond_path(0.0, 0.0, 0.000002, 0.0, 0, 1)
        self.assertFalse(midpoint_path.isEmpty())

    def test_double_neighbor_target_and_plain_double_normal_cover_invalid_and_offset_fallbacks(self) -> None:
        self.assertIsNone(self.renderer.line_geometry._double_neighbor_target(None, 1))
        self.assertIsNone(self.renderer.line_geometry._double_neighbor_target(0, None))

        self.canvas.model.atoms[3] = Atom("C", 10.0, 10.0)
        self.canvas.graph_state.atom_bond_ids = {0: {0, 1, 2, 3}, 1: {0, 4}}
        self.canvas.model.bonds = [
            Bond(0, 1, 1),
            None,
            Bond(0, 2, 1),
            Bond(3, 0, 1),
            Bond(1, 2, 1),
        ]
        target = self.renderer.line_geometry._double_neighbor_target(0, 1)
        self.assertEqual((target.x(), target.y()), (10.0 / 3.0, 10.0))

        self.canvas.graph_state.atom_bond_ids = {}
        self.canvas.model.atoms[1] = Atom("C", 8.0, -6.0)
        self.assertEqual(self.renderer.line_geometry._plain_double_normal(0.0, 0.0, 10.0, 0.0, 0, 1), (0.6, 0.8))

        self.canvas.model.atoms[1] = Atom("C", 10.0, 0.0)
        self.assertEqual(
            self.renderer.line_geometry._plain_double_normal(0.0, 0.0, 10.0, 0.0, 0, 1),
            self.canvas._normal,
        )

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

    def test_update_bond_geometry_covers_dotted_double_variants(self) -> None:
        outer_path = QGraphicsPathItem(QPainterPath())
        inner_line = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 2, style="dotted_double_outer"))
        self.canvas.bond_items[0] = [outer_path, inner_line]
        self.renderer.update_bond_geometry(0)
        self.assertFalse(outer_path.path().isEmpty())
        self.assertGreater(inner_line.line().length(), 0.0)

        outer_line = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        inner_path = QGraphicsPathItem(QPainterPath())
        self._set_bond(Bond(0, 1, 2, style="dotted_double"))
        self.canvas.bond_items[0] = [outer_line, inner_path]
        self.renderer.update_bond_geometry(0)
        self.assertGreater(outer_line.line().length(), 0.0)
        self.assertFalse(inner_path.path().isEmpty())

    def test_update_bond_geometry_covers_item_mismatch_and_remaining_variant_paths(self) -> None:
        wedge_line = QGraphicsLineItem(4.0, 5.0, 6.0, 7.0)
        self._set_bond(Bond(0, 1, 1, style="wedge"))
        self.canvas.bond_items[0] = [wedge_line]
        self.renderer.update_bond_geometry(0)
        self.assertEqual((wedge_line.line().x1(), wedge_line.line().y1()), (4.0, 5.0))

        hash_polygon = QGraphicsPolygonItem(QPolygonF())
        hash_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self._set_bond(Bond(0, 1, 1, style="hash"))
        self.canvas.bond_items[0] = [hash_polygon, hash_line]
        self.renderer.update_bond_geometry(0)
        self.assertGreater(hash_line.line().length(), 0.0)

        dotted_line = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 1, style="dotted"))
        self.canvas.bond_items[0] = [dotted_line, QGraphicsPathItem(QPainterPath())]
        self.renderer.update_bond_geometry(0)
        self.assertGreater(dotted_line.line().length(), 0.0)

        self._set_bond(Bond(0, 1, 2, style="dotted_double_outer"))
        self.canvas._ring_center = QPointF(5.0, 5.0)
        ring_outer_path = QGraphicsPathItem(QPainterPath())
        ring_inner_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self.canvas.bond_items[0] = [ring_outer_path, ring_inner_line]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertFalse(ring_outer_path.path().isEmpty())
        self.assertGreater(ring_inner_line.line().length(), 0.0)

        self._set_bond(Bond(0, 1, 2, style="dotted_double"))
        wrong_outer = QGraphicsPolygonItem(QPolygonF())
        wrong_inner = QGraphicsPolygonItem(QPolygonF())
        self.canvas.bond_items[0] = [wrong_outer, wrong_inner]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual(len(wrong_outer.polygon()), 0)
        self.assertEqual(len(wrong_inner.polygon()), 0)

        ring_outer_line = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        ring_inner_polygon = QGraphicsPolygonItem(QPolygonF())
        self._set_bond(Bond(0, 1, 2, style="bold_out"))
        self.canvas._ring_center = QPointF(5.0, 5.0)
        self.canvas.bond_items[0] = [ring_outer_line, ring_inner_polygon]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual((ring_outer_line.line().x1(), ring_outer_line.line().x2()), (0.0, 10.0))

        empty_parallel_item = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 3, style="bold"))
        self.canvas._ring_center = None
        self.canvas.bond_items[0] = [empty_parallel_item]
        with mock.patch.object(self.renderer, "parallel_bond_segments", return_value=[]):
            self.renderer.update_bond_geometry(0)
        self.assertGreater(empty_parallel_item.line().length(), 0.0)

        outward_polygon = QGraphicsPolygonItem(QPolygonF())
        self._set_bond(Bond(0, 1, 1, style="bold_out"))
        self.canvas.bond_items[0] = [outward_polygon]
        self.renderer.update_bond_geometry(0)
        self.assertEqual(len(outward_polygon.polygon()), 4)

        outward_parallel_polygon = QGraphicsPolygonItem(QPolygonF())
        outward_parallel_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        ignored_parallel_polygon = QGraphicsPolygonItem(QPolygonF())
        self._set_bond(Bond(0, 1, 3, style="bold_out"))
        self.canvas.bond_items[0] = [
            outward_parallel_polygon,
            outward_parallel_line,
            ignored_parallel_polygon,
        ]
        with mock.patch.object(
            self.renderer,
            "parallel_bond_segments",
            return_value=[
                (0.0, 0.0, 10.0, 0.0),
                (0.0, 2.0, 10.0, 2.0),
                (0.0, 4.0, 10.0, 4.0),
            ],
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual(len(outward_parallel_polygon.polygon()), 4)
        self.assertGreater(outward_parallel_line.line().length(), 0.0)
        self.assertEqual(len(ignored_parallel_polygon.polygon()), 0)

        inward_parallel_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        ignored_inner_polygon = QGraphicsPolygonItem(QPolygonF())
        self._set_bond(Bond(0, 1, 3, style="bold"))
        self.canvas.bond_items[0] = [inward_parallel_line, ignored_inner_polygon]
        with mock.patch.object(
            self.renderer,
            "parallel_bond_segments",
            return_value=[
                (1.0, 0.0, 9.0, 0.0),
                (1.0, 2.0, 9.0, 2.0),
            ],
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual((inward_parallel_line.line().x1(), inward_parallel_line.line().x2()), (1.0, 9.0))

        double_outer = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        double_inner = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 2, style="single"))
        self.canvas._ring_center = None
        self.canvas.bond_items[0] = [double_outer, double_inner]
        self.renderer.update_bond_geometry(0)
        self.assertGreater(double_outer.line().length(), 0.0)
        self.assertGreater(double_inner.line().length(), 0.0)

        single_polygon = QGraphicsPolygonItem(QPolygonF())
        self._set_bond(Bond(0, 1, 1, style="single"))
        self.canvas.bond_items[0] = [single_polygon]
        self.renderer.update_bond_geometry(0)
        self.assertEqual(len(single_polygon.polygon()), 0)

    def test_add_bond_graphics_returns_early_for_none_bond(self) -> None:
        self._set_bond(None)
        self.renderer.add_bond_graphics(0)
        self.assertEqual(self.canvas.bond_items, {})

    def test_redraw_and_add_bond_graphics_use_scene_item_access_helpers(self) -> None:
        old_item = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
        self._set_bond(Bond(0, 1, 1, style="single"))
        self.canvas.bond_items[0] = [old_item]
        removed_items = []
        added_items = []

        with (
            mock.patch.object(
                bond_renderer_module,
                "remove_item_from_canvas_scene",
                side_effect=lambda canvas, item: removed_items.append((canvas, item)),
            ),
            mock.patch.object(
                bond_graphics_build_module,
                "add_item_to_canvas_scene",
                side_effect=lambda canvas, item: added_items.append((canvas, item)),
            ),
        ):
            self.assertTrue(self.renderer.redraw_bond(0))

        self.assertEqual(removed_items, [(self.canvas, old_item)])
        self.assertTrue(added_items)
        self.assertTrue(all(canvas is self.canvas for canvas, _ in added_items))
        self.assertEqual(self.canvas.bond_items[0], [item for _, item in added_items])

    def test_add_bond_graphics_covers_wedge_hash_single_and_dotted_paths(self) -> None:
        for style in ("wedge", "hash", "single", "dotted"):
            self.canvas._scene.clear()
            self._set_bond(Bond(0, 1, 1, style=style, color="#AA5500"))
            self.renderer.add_bond_graphics(0)
            items = self.canvas.bond_items[0]
            self.assertTrue(items)
            self.assertTrue(all(item.data(0) == "bond" and item.data(1) == 0 for item in items))
            self.assertTrue(any(item.flags() & item.GraphicsItemFlag.ItemIsSelectable for item in items))
            if style == "dotted":
                self.assertIsInstance(items[0], NoSelectPathItem)

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

    def test_add_bond_graphics_covers_remaining_bold_and_plain_double_nonring_variants(self) -> None:
        self.canvas._ring_center = None
        self._set_bond(Bond(0, 1, 3, style="bold_out"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 3)
        self.assertIsInstance(self.canvas.bond_items[0][0], (NoSelectPolygonItem, NoSelectLineItem))

        self.canvas._scene.clear()
        self._set_bond(Bond(0, 1, 1, style="bold"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 1)
        self.assertIsInstance(self.canvas.bond_items[0][0], (NoSelectPolygonItem, NoSelectLineItem))

        self.canvas._scene.clear()
        self._set_bond(Bond(0, 1, 2, style="single"))
        self.renderer.add_bond_graphics(0)
        self.assertEqual(len(self.canvas.bond_items[0]), 2)
        self.assertTrue(all(isinstance(item, NoSelectLineItem) for item in self.canvas.bond_items[0]))

        self.canvas._scene.clear()
        self._set_bond(Bond(0, 1, 3, style="bold"))
        replacement = NoSelectPolygonItem(QPolygonF())
        with mock.patch.object(self.renderer.graphics_drawer, "draw_parallel_bonds", return_value=[replacement]):
            self.renderer.add_bond_graphics(0)
        self.assertIs(self.canvas.bond_items[0][0], replacement)


if __name__ == "__main__":
    unittest.main()
