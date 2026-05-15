import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsScene = None
    Qt = None

if QApplication is not None:
    from ui.handle_interaction_logic import (
        clamp_curved_midpoint,
        clear_handle_items,
        control_from_midpoint,
        create_handle_item,
        curved_midpoint,
        default_curved_control,
        orbital_handle_positions,
        orbital_rotation_angle,
        orbital_scale_factor,
    )


class _BrokenHandle:
    def scene(self):
        raise RuntimeError("wrapped C/C++ object has been deleted")


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for handle interaction tests")
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
        self.assertAlmostEqual(handle.rect().center().x(), 12.0)
        self.assertAlmostEqual(handle.rect().center().y(), -4.0)
        self.assertEqual(handle.zValue(), 30)
        self.assertEqual(handle.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(handle.pen().color().name(), "#d32f2f")
        self.assertEqual(handle.pen().style(), Qt.PenStyle.DashLine)

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

    def test_clear_handle_items_ignores_off_scene_and_runtime_error_handles(self) -> None:
        scene = QGraphicsScene()
        other_scene = QGraphicsScene()
        off_scene_handle = create_handle_item(QPointF(4.0, 0.0), "orbital_scale", object())
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
        self.assertAlmostEqual(orbital_scale_factor(center, QPointF(35.0, -3.0), 20.0), 1.5)
        self.assertAlmostEqual(
            orbital_rotation_angle(center, QPointF(5.0, 17.0), snap_enabled=False, snap_step=15),
            90.0,
        )
        self.assertAlmostEqual(
            orbital_rotation_angle(center, QPointF(16.0, 8.0), snap_enabled=True, snap_step=15),
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


if __name__ == "__main__":
    unittest.main()
