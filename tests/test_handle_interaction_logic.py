import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene

from chemvas.features.selection import (
    EDGE_HANDLE_SCREEN_PX,
    HANDLE_ACCENT_COLOR,
    HANDLE_SCREEN_PX,
    ROTATION_HANDLE_STEM_PX,
    ROTATION_HANDLE_TYPE,
    clamp_curved_midpoint,
    clear_handle_items,
    control_from_midpoint,
    create_handle_item,
    create_rotation_handle_item,
    curved_midpoint,
    default_curved_control,
    orbital_handle_positions,
    orbital_rotation_angle,
    orbital_scale_factor,
    rotation_drag_angle,
    selection_frame_applies,
)


class _BrokenHandle:
    def scene(self):
        raise RuntimeError("wrapped C/C++ object has been deleted")


class HandleInteractionLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_create_handle_item_sets_expected_metadata(self) -> None:
        target = object()
        handle = create_handle_item(QPointF(12.0, -4.0), "orbital_scale", target)

        self.assertEqual(handle.data(0), "handle")
        self.assertEqual(handle.data(1), "orbital_scale")
        self.assertIs(handle.data(2), target)
        self.assertAlmostEqual(handle.pos().x(), 12.0)
        self.assertAlmostEqual(handle.pos().y(), -4.0)
        self.assertEqual(handle.zValue(), 30)
        # A hollow circle, centred on its origin, that keeps its size on screen.
        self.assertEqual(handle.rect().center(), QPointF(0.0, 0.0))
        self.assertEqual(handle.rect().width(), HANDLE_SCREEN_PX)
        self.assertTrue(
            handle.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        self.assertEqual(handle.brush().style(), Qt.BrushStyle.SolidPattern)
        self.assertEqual(handle.brush().color().name(), "#ffffff")
        self.assertEqual(handle.pen().color().name(), HANDLE_ACCENT_COLOR)
        self.assertEqual(handle.pen().style(), Qt.PenStyle.SolidLine)
        self.assertTrue(handle.pen().isCosmetic())

    def test_edge_resize_handles_are_smaller_than_corner_handles(self) -> None:
        corner = create_handle_item(QPointF(0.0, 0.0), "shape_nw", object())
        edge = create_handle_item(QPointF(0.0, 0.0), "shape_n", object())

        self.assertEqual(corner.rect().width(), HANDLE_SCREEN_PX)
        self.assertEqual(edge.rect().width(), EDGE_HANDLE_SCREEN_PX)
        self.assertLess(edge.rect().width(), corner.rect().width())

    def test_handle_keeps_its_screen_size_when_the_view_zooms(self) -> None:
        handle = create_handle_item(QPointF(10.0, 10.0), "arrow_end", object())
        scene = QGraphicsScene()
        scene.addItem(handle)
        zoomed = QTransform().scale(3.0, 3.0)

        # Picked through the view transform, the grip is 8 px wide on screen
        # (2.67 scene units at 300 %), not 8 scene units.
        near = QPointF(10.0 + 1.0, 10.0)
        far = QPointF(10.0 + 3.0, 10.0)
        self.assertIn(
            handle,
            scene.items(
                near,
                Qt.ItemSelectionMode.IntersectsItemShape,
                Qt.SortOrder.DescendingOrder,
                zoomed,
            ),
        )
        self.assertNotIn(
            handle,
            scene.items(
                far,
                Qt.ItemSelectionMode.IntersectsItemShape,
                Qt.SortOrder.DescendingOrder,
                zoomed,
            ),
        )

    def test_rotation_handle_sits_on_a_stem_above_its_anchor(self) -> None:
        handle = create_rotation_handle_item(QPointF(30.0, -20.0))

        self.assertEqual(handle.data(0), "handle")
        self.assertEqual(handle.data(1), ROTATION_HANDLE_TYPE)
        self.assertIsNone(handle.data(2))
        self.assertEqual(handle.pos(), QPointF(30.0, -20.0))
        self.assertTrue(
            handle.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        bounds = handle.path().boundingRect()
        self.assertAlmostEqual(bounds.bottom(), 0.0)
        self.assertAlmostEqual(
            bounds.top(), -(ROTATION_HANDLE_STEM_PX + HANDLE_SCREEN_PX)
        )

    def test_rotation_drag_angle_sweeps_clockwise_and_snaps(self) -> None:
        center = QPointF(0.0, 0.0)
        start = QPointF(0.0, -10.0)

        self.assertAlmostEqual(
            rotation_drag_angle(center, start, QPointF(10.0, 0.0)), 90.0
        )
        self.assertAlmostEqual(
            rotation_drag_angle(center, start, QPointF(-10.0, 0.0)), -90.0
        )
        self.assertAlmostEqual(
            rotation_drag_angle(center, start, QPointF(10.0, -10.0), snap_step=15.0),
            45.0,
        )
        self.assertAlmostEqual(
            rotation_drag_angle(center, start, QPointF(10.0, -9.0), snap_step=15.0),
            45.0,
        )
        self.assertAlmostEqual(rotation_drag_angle(center, start, start), 0.0)

    def test_selection_frame_applies_to_what_a_rotation_can_turn(self) -> None:
        self.assertFalse(selection_frame_applies(0, 0))
        self.assertFalse(selection_frame_applies(1, 0))
        self.assertTrue(selection_frame_applies(2, 0))
        self.assertTrue(selection_frame_applies(0, 1))
        self.assertTrue(selection_frame_applies(1, 1))

    def test_clear_handle_items_removes_scene_items(self) -> None:
        scene = QGraphicsScene()
        handle_a = create_handle_item(QPointF(0.0, 0.0), "orbital_scale", object())
        handle_b = create_handle_item(QPointF(10.0, 0.0), "orbital_rotate", object())
        scene.addItem(handle_a)
        scene.addItem(handle_b)

        cleared = clear_handle_items(scene, [handle_a, handle_b])

        self.assertEqual(cleared, [])
        self.assertIsNone(handle_a.scene())
        self.assertIsNone(handle_b.scene())
        self.assertEqual(len(scene.items()), 0)

    def test_clear_handle_items_ignores_off_scene_and_runtime_error_handles(
        self,
    ) -> None:
        scene = QGraphicsScene()
        other_scene = QGraphicsScene()
        off_scene_handle = create_handle_item(
            QPointF(4.0, 0.0), "orbital_scale", object()
        )
        other_scene.addItem(off_scene_handle)

        cleared = clear_handle_items(scene, [off_scene_handle, _BrokenHandle()])

        self.assertEqual(cleared, [])
        self.assertIs(off_scene_handle.scene(), other_scene)
        self.assertEqual(len(scene.items()), 0)

    def test_orbital_helpers_compute_positions_scale_and_rotation(self) -> None:
        center = QPointF(5.0, -3.0)
        scale_pos, rotate_pos = orbital_handle_positions(center, 20.0)

        self.assertEqual((scale_pos.x(), scale_pos.y()), (25.0, -3.0))
        self.assertEqual((rotate_pos.x(), rotate_pos.y()), (5.0, -23.0))
        self.assertAlmostEqual(
            orbital_scale_factor(center, QPointF(35.0, -3.0), 20.0), 1.5
        )
        self.assertAlmostEqual(
            orbital_rotation_angle(
                center, QPointF(5.0, 17.0), snap_enabled=False, snap_step=15
            ),
            90.0,
        )
        self.assertAlmostEqual(
            orbital_rotation_angle(
                center, QPointF(16.0, 8.0), snap_enabled=True, snap_step=15
            ),
            45.0,
        )

    def test_curved_helpers_round_trip_control_and_midpoint(self) -> None:
        start = QPointF(-20.0, 0.0)
        end = QPointF(20.0, 0.0)
        control = default_curved_control(start, end)
        mid = curved_midpoint(start, control, end)
        rebuilt_control = control_from_midpoint(start, end, mid)

        self.assertAlmostEqual(rebuilt_control.x(), control.x())
        self.assertAlmostEqual(rebuilt_control.y(), control.y())

    def test_clamp_curved_midpoint_snaps_and_limits_offset(self) -> None:
        start = QPointF(-20.0, 0.0)
        end = QPointF(20.0, 0.0)
        clamped = clamp_curved_midpoint(
            start,
            end,
            QPointF(0.0, 50.0),
            snap_enabled=True,
            snap_distance=6.0,
        )

        self.assertAlmostEqual(clamped.x(), 0.0)
        self.assertAlmostEqual(clamped.y(), 32.0)

        unsnapped = clamp_curved_midpoint(
            start,
            end,
            QPointF(0.0, 17.0),
            snap_enabled=False,
            snap_distance=6.0,
        )

        self.assertAlmostEqual(unsnapped.x(), 0.0)
        self.assertAlmostEqual(unsnapped.y(), 17.0)
