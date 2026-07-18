import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.core.perspective_drag_logic import (
    resolve_perspective_drag_update,  # noqa: E402
)


class PerspectiveDragLogicTest(unittest.TestCase):
    def test_resolve_perspective_drag_update_locks_x_axis_for_wider_delta(self) -> None:
        update = resolve_perspective_drag_update(
            delta_x=6.0,
            delta_y=2.0,
            axis_lock=None,
            rotation_mode="rigid",
            shift_pressed=True,
        )

        self.assertEqual(update.delta_x, 6.0)
        self.assertEqual(update.delta_y, 0.0)
        self.assertEqual(update.axis_lock, "x")
        self.assertTrue(update.should_update)

    def test_resolve_perspective_drag_update_locks_y_axis_for_taller_delta(
        self,
    ) -> None:
        update = resolve_perspective_drag_update(
            delta_x=2.0,
            delta_y=6.0,
            axis_lock=None,
            rotation_mode="rigid",
            shift_pressed=True,
        )

        self.assertEqual(update.delta_x, 0.0)
        self.assertEqual(update.delta_y, 6.0)
        self.assertEqual(update.axis_lock, "y")
        self.assertTrue(update.should_update)

    def test_resolve_perspective_drag_update_skips_zero_delta_when_lock_is_unset(
        self,
    ) -> None:
        update = resolve_perspective_drag_update(
            delta_x=0.0,
            delta_y=0.0,
            axis_lock=None,
            rotation_mode="rigid",
            shift_pressed=True,
        )

        self.assertEqual(update.delta_x, 0.0)
        self.assertEqual(update.delta_y, 0.0)
        self.assertIsNone(update.axis_lock)
        self.assertFalse(update.should_update)

    def test_resolve_perspective_drag_update_clears_lock_without_shift(self) -> None:
        update = resolve_perspective_drag_update(
            delta_x=3.0,
            delta_y=4.0,
            axis_lock="x",
            rotation_mode="rigid",
            shift_pressed=False,
        )

        self.assertEqual(update.delta_x, 3.0)
        self.assertEqual(update.delta_y, 4.0)
        self.assertIsNone(update.axis_lock)
        self.assertTrue(update.should_update)

    def test_resolve_perspective_drag_update_preserves_existing_y_lock(self) -> None:
        update = resolve_perspective_drag_update(
            delta_x=3.0,
            delta_y=4.0,
            axis_lock="y",
            rotation_mode="rigid",
            shift_pressed=True,
        )

        self.assertEqual(update.delta_x, 0.0)
        self.assertEqual(update.delta_y, 4.0)
        self.assertEqual(update.axis_lock, "y")
        self.assertTrue(update.should_update)


if __name__ == "__main__":
    unittest.main()
