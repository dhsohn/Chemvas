import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom
    from ui.canvas_atom_graphics_state import set_atom_dots_for, set_atom_items_for
    from ui.canvas_callback_state import CanvasCallbackState
    from ui.canvas_insert_state import CanvasInsertState
    from ui.canvas_tool_mode_controller import CanvasToolModeController
    from ui.canvas_tool_settings_state import CanvasToolSettingsState
    from ui.history_canvas_access import set_ring_polygons_for_history
    from ui.input_view_access import update_view_transform_for
    from ui.input_view_state import InputViewState
    from ui.selection_center_logic import (
        bounding_box_center_for_atoms,
        center_for_atoms,
    )
    from ui.selection_geometry_access import bounds_for_atoms_for
    from ui.structure_geometry_access import (
        _compute_bond_template_geometry_for,
        cyclohexane_boat_points_for,
        cyclohexane_chair_points_for,
        point_pair,
        point_pairs,
        qpoints_from_pairs,
        regular_ring_radius_for,
        ring_points_for,
        scale_qpoints_to_bond_length,
        template_geometry_result,
    )


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

        centroid = center_for_atoms({1, 2, 3, 99}, atoms=view.model.atoms)
        bbox_center = bounding_box_center_for_atoms({1, 2, 3, 99}, atoms=view.model.atoms)

        self.assertEqual(centroid, QPointF(3.0, 17.0 / 3.0))
        self.assertEqual(bbox_center, QPointF(3.0, 6.0))
        self.assertIsNone(center_for_atoms({99}, atoms=view.model.atoms))
        self.assertIsNone(bounding_box_center_for_atoms({99}, atoms=view.model.atoms))

    def test_update_view_transform_applies_shear_and_scale_over_base_transform(self) -> None:
        plain_view = SimpleNamespace(
            input_view_state=InputViewState(base_transform=QTransform().translate(2.0, 3.0)),
            setTransform=mock.Mock(),
        )

        update_view_transform_for(plain_view)

        plain_transform = plain_view.setTransform.call_args.args[0]
        self.assertAlmostEqual(plain_transform.dx(), 2.0)
        self.assertAlmostEqual(plain_transform.dy(), 3.0)
        self.assertAlmostEqual(plain_transform.m12(), 0.0)
        self.assertAlmostEqual(plain_transform.m22(), 1.0)

        skewed_view = SimpleNamespace(
            input_view_state=InputViewState(
                base_transform=QTransform().translate(2.0, 3.0),
                perspective_shear=0.25,
                perspective_scale_y=1.5,
            ),
            setTransform=mock.Mock(),
        )

        update_view_transform_for(skewed_view)

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
        )
        set_atom_items_for(view, {1: label})
        set_atom_dots_for(view, {1: dot})

        self.assertEqual(bounds_for_atoms_for(view, {1, 99}), (10.0, 20.0, 10.0, 20.0))

        bounds_with_labels = bounds_for_atoms_for(view, {1, 99}, include_labels=True)
        self.assertLess(bounds_with_labels[0], 10.0)
        self.assertLess(bounds_with_labels[1], 20.0)
        self.assertGreater(bounds_with_labels[2], 14.0)
        self.assertGreater(bounds_with_labels[3], 18.0)

        self.assertEqual(bounds_for_atoms_for(view, {99}, include_labels=True), (-5.0, -6.0, 7.0, 8.0))
        view.model.bounds.assert_called_once_with()

    def test_set_ring_polygons_and_tool_variant_setters_update_canvas_state(self) -> None:
        ring = QGraphicsPolygonItem()
        view = SimpleNamespace(
            insert_state=CanvasInsertState(template_active=True),
            refresh_selection_outline=mock.Mock(),
            callback_state=CanvasCallbackState(tool_change=mock.Mock()),
            tool_settings_state=CanvasToolSettingsState(
                active_bond_style="single",
                active_bond_order=1,
                active_arrow_type="reaction",
                active_orbital_type="p",
                curved_snap_step=0.25,
            ),
        )
        view.services = SimpleNamespace(
            selection_controller=SimpleNamespace(update_selection_outline=view.refresh_selection_outline),
            hover_scene_service=SimpleNamespace(clear_hover_highlight=mock.Mock()),
            tools=SimpleNamespace(set_active=mock.Mock()),
        )

        set_ring_polygons_for_history(
            SimpleNamespace(),
            [ring, None],
            [[(1.0, 2.0), (3.0, 4.0)], [(9.0, 9.0)]],
        )
        polygon = ring.polygon()
        self.assertEqual(polygon.count(), 2)
        self.assertEqual((polygon[0].x(), polygon[0].y(), polygon[1].x(), polygon[1].y()), (1.0, 2.0, 3.0, 4.0))

        tool_mode_controller = CanvasToolModeController(
            view,
            hover_refresh=view.services.hover_scene_service.clear_hover_highlight,
            set_active_tool=view.services.tools.set_active,
        )
        tool_mode_controller.set_bond_style("double", 2)
        tool_mode_controller.set_arrow_type("curved")
        tool_mode_controller.set_orbital_type("sp2")
        tool_mode_controller.set_curved_snap(1)
        tool_mode_controller.set_curved_snap_step(0.01)

        settings = view.tool_settings_state
        self.assertEqual((settings.active_bond_style, settings.active_bond_order), ("double", 2))
        self.assertEqual(settings.active_arrow_type, "curved")
        self.assertEqual(settings.active_orbital_type, "sp2")
        self.assertTrue(tool_mode_controller.get_curved_snap())
        self.assertEqual(tool_mode_controller.get_curved_snap_step(), 0.05)
        self.assertEqual(
            view.services.tools.set_active.call_args_list,
            [mock.call("bond"), mock.call("arrow"), mock.call("orbital")],
        )
        self.assertEqual(view.refresh_selection_outline.call_count, 3)
        self.assertEqual(view.callback_state.tool_change.call_count, 3)
        self.assertEqual(view.services.hover_scene_service.clear_hover_highlight.call_count, 3)

    def test_point_pair_helpers_cover_add_geometry_paths(self) -> None:
        view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )

        pointfs = qpoints_from_pairs([(1.0, 2.0), (3.5, 4.5)])
        self.assertEqual([(point.x(), point.y()) for point in pointfs], [(1.0, 2.0), (3.5, 4.5)])

        chair_points = cyclohexane_chair_points_for(view, QPointF(0.0, 0.0))
        boat_points = cyclohexane_boat_points_for(view, QPointF(0.0, 0.0))
        ring_points = ring_points_for(view, QPointF(0.0, 0.0), 6)
        scaled_points = scale_qpoints_to_bond_length(
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
        )

        self.assertEqual(point_pairs([QPointF(1.0, 2.0), QPointF(3.0, 4.0)]), [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(point_pair(QPointF(5.0, 6.0)), (5.0, 6.0))
        self.assertIsNone(point_pair(None))
        self.assertEqual(
            [(point.x(), point.y()) for point in qpoints_from_pairs([(7.0, 8.0)])],
            [(7.0, 8.0)],
        )
        self.assertEqual(
            template_geometry_result(([(9.0, 10.0)], [(1, 0.0, 0.0)]))[1],
            [(1, 0.0, 0.0)],
        )
        self.assertIsNone(template_geometry_result(None))
        self.assertAlmostEqual(regular_ring_radius_for(view, 6), 14.0)
        self.assertAlmostEqual(regular_ring_radius_for(view, 6, bond_length=20.0), 20.0)

        geometry_fn = mock.Mock(side_effect=[None, ([(11.0, 12.0)], [(2, 3.0, 4.0)])])

        with mock.patch(
            "ui.structure_geometry_access.ring_polygon_points_for_bond",
            return_value=[(1.0, 1.0)],
        ):
            self.assertIsNone(
                _compute_bond_template_geometry_for(
                    view,
                    geometry_fn,
                    [(0.0, 1.0)],
                    7,
                    center_hint=QPointF(2.0, 3.0),
                )
            )
            result = _compute_bond_template_geometry_for(
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
