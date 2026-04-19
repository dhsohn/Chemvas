import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom
    from ui.canvas_view import CanvasView


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewCenterTransformHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_center_helpers_average_and_bounding_box_skip_missing_atoms(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 1.0),
                    2: Atom("C", 6.0, 5.0),
                    3: Atom("C", 3.0, 11.0),
                }
            )
        )

        centroid = CanvasView._center_for_atoms(view, {1, 2, 3, 99})
        bbox_center = CanvasView._bounding_box_center_for_atoms(view, {1, 2, 3, 99})

        self.assertEqual(centroid, QPointF(3.0, 17.0 / 3.0))
        self.assertEqual(bbox_center, QPointF(3.0, 6.0))
        self.assertIsNone(CanvasView._center_for_atoms(view, {99}))
        self.assertIsNone(CanvasView._bounding_box_center_for_atoms(view, {99}))

    def test_update_view_transform_applies_shear_and_scale_over_base_transform(self) -> None:
        plain_view = SimpleNamespace(
            _base_transform=QTransform().translate(2.0, 3.0),
            _perspective_shear=0.0,
            _perspective_scale_y=1.0,
            setTransform=mock.Mock(),
        )

        CanvasView._update_view_transform(plain_view)

        plain_transform = plain_view.setTransform.call_args.args[0]
        self.assertAlmostEqual(plain_transform.dx(), 2.0)
        self.assertAlmostEqual(plain_transform.dy(), 3.0)
        self.assertAlmostEqual(plain_transform.m12(), 0.0)
        self.assertAlmostEqual(plain_transform.m22(), 1.0)

        skewed_view = SimpleNamespace(
            _base_transform=QTransform().translate(2.0, 3.0),
            _perspective_shear=0.25,
            _perspective_scale_y=1.5,
            setTransform=mock.Mock(),
        )

        CanvasView._update_view_transform(skewed_view)

        skewed_transform = skewed_view.setTransform.call_args.args[0]
        self.assertAlmostEqual(skewed_transform.dx(), 2.0)
        self.assertAlmostEqual(skewed_transform.dy(), 3.0)
        self.assertAlmostEqual(skewed_transform.m21(), 0.375)
        self.assertAlmostEqual(skewed_transform.m22(), 1.5)

    def test_bounds_for_atoms_includes_labels_and_dots_or_falls_back_to_model_bounds(self) -> None:
        label = QGraphicsTextItem("O")
        label.setPos(6.0, 8.0)
        dot = QGraphicsEllipseItem(-1.0, -1.0, 2.0, 2.0)
        dot.setPos(14.0, 18.0)
        ring = QGraphicsPolygonItem()
        scene = QGraphicsScene()
        for item in (label, dot, ring):
            scene.addItem(item)

        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 10.0, 20.0),
                    2: Atom("O", 30.0, 40.0),
                },
                bounds=mock.Mock(return_value=(-5.0, -6.0, 7.0, 8.0)),
            ),
            atom_items={1: label},
            atom_dots={1: dot},
            _extend_bounds_with_item_rect=CanvasView._extend_bounds_with_item_rect,
        )

        self.assertEqual(CanvasView._bounds_for_atoms(view, {1, 99}), (10.0, 20.0, 10.0, 20.0))

        bounds_with_labels = CanvasView._bounds_for_atoms(view, {1, 99}, include_labels=True)
        self.assertLess(bounds_with_labels[0], 10.0)
        self.assertLess(bounds_with_labels[1], 20.0)
        self.assertGreater(bounds_with_labels[2], 14.0)
        self.assertGreater(bounds_with_labels[3], 18.0)

        self.assertEqual(CanvasView._bounds_for_atoms(view, {99}, include_labels=True), (-5.0, -6.0, 7.0, 8.0))
        view.model.bounds.assert_called_once_with()

    def test_set_ring_polygons_and_tool_variant_setters_update_canvas_state(self) -> None:
        ring = QGraphicsPolygonItem()
        view = SimpleNamespace(
            active_bond_style="single",
            active_bond_order=1,
            active_arrow_type="reaction",
            active_orbital_type="p",
            tools=SimpleNamespace(set_active=mock.Mock()),
            _update_selection_outline=mock.Mock(),
            _notify_tool_change=mock.Mock(),
            _refresh_hover_from_cursor=mock.Mock(),
            _curved_snap=False,
            _curved_snap_step=0.25,
        )
        view._activate_tool_variant = lambda tool_name, **state: CanvasView._activate_tool_variant(
            view,
            tool_name,
            **state,
        )

        CanvasView.set_ring_polygons(SimpleNamespace(), [ring, None], [[(1.0, 2.0), (3.0, 4.0)], [(9.0, 9.0)]])
        polygon = ring.polygon()
        self.assertEqual(polygon.count(), 2)
        self.assertEqual((polygon[0].x(), polygon[0].y(), polygon[1].x(), polygon[1].y()), (1.0, 2.0, 3.0, 4.0))

        CanvasView.set_bond_style(view, "double", 2)
        CanvasView.set_arrow_type(view, "curved")
        CanvasView.set_orbital_type(view, "sp2")
        CanvasView.set_curved_snap(view, 1)
        CanvasView.set_curved_snap_step(view, 0.01)

        self.assertEqual((view.active_bond_style, view.active_bond_order), ("double", 2))
        self.assertEqual(view.active_arrow_type, "curved")
        self.assertEqual(view.active_orbital_type, "sp2")
        self.assertTrue(CanvasView.get_curved_snap(view))
        self.assertEqual(CanvasView.get_curved_snap_step(view), 0.05)
        self.assertEqual(view.tools.set_active.call_args_list, [mock.call("bond"), mock.call("arrow"), mock.call("orbital")])
        self.assertEqual(view._update_selection_outline.call_count, 3)
        self.assertEqual(view._notify_tool_change.call_count, 3)
        self.assertEqual(view._refresh_hover_from_cursor.call_count, 3)

    def test_scene_center_and_point_pair_helpers_cover_add_geometry_paths(self) -> None:
        center_point = QPointF(9.0, 11.0)
        view = SimpleNamespace(
            viewport=lambda: SimpleNamespace(rect=lambda: SimpleNamespace(center=lambda: QPointF(3.0, 4.0))),
            mapToScene=mock.Mock(return_value=center_point),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )

        self.assertIs(CanvasView._viewport_scene_center(view), center_point)
        view.mapToScene.assert_called_once()

        pointfs = CanvasView._qpoints_from_pairs([(1.0, 2.0), (3.5, 4.5)])
        self.assertEqual([(point.x(), point.y()) for point in pointfs], [(1.0, 2.0), (3.5, 4.5)])

        chair_points = CanvasView._cyclohexane_chair_points(view, QPointF(0.0, 0.0))
        boat_points = CanvasView._cyclohexane_boat_points(view, QPointF(0.0, 0.0))
        ring_points = CanvasView._ring_points(view, QPointF(0.0, 0.0), 6)
        scaled_points = CanvasView._scale_points_to_bond_length(
            [QPointF(0.0, 0.0), QPointF(10.0, 0.0)],
            QPointF(5.0, 0.0),
            20.0,
        )

        self.assertTrue(all(isinstance(point, QPointF) for point in chair_points))
        self.assertTrue(all(isinstance(point, QPointF) for point in boat_points))
        self.assertEqual(len(ring_points), 6)
        self.assertEqual([(point.x(), point.y()) for point in scaled_points], [(-5.0, 0.0), (15.0, 0.0)])

    def test_template_geometry_helpers_cover_none_result_and_pair_conversions(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 10.0, 0.0),
                },
                bonds=[],
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=14.0)),
            _ring_polygon_points_for_bond=mock.Mock(return_value=[(1.0, 1.0)]),
        )

        self.assertEqual(CanvasView._point_pairs([QPointF(1.0, 2.0), QPointF(3.0, 4.0)]), [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(CanvasView._point_pair(QPointF(5.0, 6.0)), (5.0, 6.0))
        self.assertIsNone(CanvasView._point_pair(None))
        self.assertEqual(
            [(point.x(), point.y()) for point in CanvasView._template_points_from_pairs(view, [(7.0, 8.0)])],
            [(7.0, 8.0)],
        )
        self.assertIsNone(CanvasView._template_points_from_pairs(view, None))
        self.assertEqual(
            CanvasView._template_geometry_result(([(9.0, 10.0)], [(1, 0.0, 0.0)]))[1],
            [(1, 0.0, 0.0)],
        )
        self.assertIsNone(CanvasView._template_geometry_result(None))
        self.assertAlmostEqual(CanvasView._regular_ring_radius(view, 6), 14.0)
        self.assertAlmostEqual(CanvasView._regular_ring_radius(view, 6, bond_length=20.0), 20.0)

        geometry_fn = mock.Mock(side_effect=[None, ([(11.0, 12.0)], [(2, 3.0, 4.0)])])

        self.assertIsNone(
            CanvasView._compute_bond_template_geometry(
                view,
                geometry_fn,
                [(0.0, 1.0)],
                7,
                center_hint=QPointF(2.0, 3.0),
            )
        )
        result = CanvasView._compute_bond_template_geometry(
            view,
            geometry_fn,
            6,
            8,
            center_hint=None,
        )

        self.assertEqual([(point.x(), point.y()) for point in result[0]], [(11.0, 12.0)])
        self.assertEqual(result[1], [(2, 3.0, 4.0)])
        self.assertEqual(
            geometry_fn.call_args_list,
            [
                mock.call(
                    [(0.0, 1.0)],
                    7,
                    atoms=view.model.atoms,
                    bonds=view.model.bonds,
                    center_hint=(2.0, 3.0),
                    occupied_polygon=[(1.0, 1.0)],
                ),
                mock.call(
                    6,
                    8,
                    atoms=view.model.atoms,
                    bonds=view.model.bonds,
                    center_hint=None,
                    occupied_polygon=[(1.0, 1.0)],
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
