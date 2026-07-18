import math
import unittest

from chemvas.ui.canvas_geometry_logic import (
    line_rect_clip_t,
    line_rect_intersections,
    ray_rect_exit_distance,
    segment_intersection_t,
)
from PyQt6.QtCore import QPointF, QRectF


class CanvasGeometryLogicTest(unittest.TestCase):
    def test_line_rect_clip_t_handles_crossing_parallel_and_disjoint_cases(
        self,
    ) -> None:
        rect = QRectF(0.0, 0.0, 2.0, 2.0)

        self.assertEqual(
            line_rect_clip_t(QPointF(-1.0, 1.0), QPointF(3.0, 1.0), rect),
            (0.25, 0.75),
        )
        self.assertEqual(
            line_rect_clip_t(QPointF(0.5, 0.5), QPointF(1.5, 1.5), rect),
            (0.0, 1.0),
        )
        self.assertIsNone(line_rect_clip_t(QPointF(-1.0, 3.0), QPointF(3.0, 3.0), rect))
        self.assertIsNone(line_rect_clip_t(QPointF(-1.0, 3.0), QPointF(1.0, 5.0), rect))

    def test_segment_intersection_t_and_line_rect_intersections_cover_hits_and_misses(
        self,
    ) -> None:
        self.assertAlmostEqual(
            segment_intersection_t(
                QPointF(-1.0, 1.0),
                QPointF(3.0, 1.0),
                QPointF(0.0, 0.0),
                QPointF(0.0, 2.0),
            ),
            0.25,
        )
        self.assertIsNone(
            segment_intersection_t(
                QPointF(0.0, 0.0),
                QPointF(1.0, 0.0),
                QPointF(0.0, 1.0),
                QPointF(1.0, 1.0),
            )
        )
        self.assertCountEqual(
            line_rect_intersections(
                QPointF(-1.0, 1.0),
                QPointF(3.0, 1.0),
                QRectF(0.0, 0.0, 2.0, 2.0),
            ),
            [0.25, 0.75],
        )
        self.assertEqual(
            line_rect_intersections(
                QPointF(-1.0, 3.0),
                QPointF(3.0, 3.0),
                QRectF(0.0, 0.0, 2.0, 2.0),
            ),
            [],
        )

    def test_ray_rect_exit_distance_handles_inside_outside_and_zero_direction(
        self,
    ) -> None:
        rect = QRectF(-2.0, -1.0, 4.0, 2.0)

        self.assertAlmostEqual(
            ray_rect_exit_distance(QPointF(0.0, 0.0), QPointF(1.0, 0.0), rect),
            2.0,
        )
        self.assertAlmostEqual(
            ray_rect_exit_distance(QPointF(0.0, 0.0), QPointF(0.0, -1.0), rect),
            1.0,
        )
        self.assertIsNone(
            ray_rect_exit_distance(QPointF(3.0, 0.0), QPointF(0.0, 1.0), rect)
        )
        self.assertIsNone(
            ray_rect_exit_distance(QPointF(-3.0, 3.0), QPointF(1.0, 1.0), rect)
        )
        self.assertIsNone(
            ray_rect_exit_distance(QPointF(3.0, 0.0), QPointF(1.0, 0.0), rect)
        )
        self.assertTrue(
            math.isinf(
                ray_rect_exit_distance(QPointF(0.0, 0.0), QPointF(0.0, 0.0), rect)
            )
        )


if __name__ == "__main__":
    unittest.main()
