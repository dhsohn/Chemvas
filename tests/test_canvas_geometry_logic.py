import math
import unittest

from chemvas.ui.canvas.canvas_geometry_logic import (
    line_rect_clip_t,
    ray_rect_exit_distance,
    segment_intersection_t,
)


class CanvasGeometryLogicTest(unittest.TestCase):
    def test_line_rect_clip_t_handles_crossing_parallel_and_disjoint_cases(
        self,
    ) -> None:
        rect = (0.0, 0.0, 2.0, 2.0)

        self.assertEqual(
            line_rect_clip_t((-1.0, 1.0), (3.0, 1.0), rect),
            (0.25, 0.75),
        )
        self.assertEqual(
            line_rect_clip_t((0.5, 0.5), (1.5, 1.5), rect),
            (0.0, 1.0),
        )
        self.assertIsNone(line_rect_clip_t((-1.0, 3.0), (3.0, 3.0), rect))
        self.assertIsNone(line_rect_clip_t((-1.0, 3.0), (1.0, 5.0), rect))

    def test_segment_intersection_t_covers_hits_and_misses(self) -> None:
        self.assertAlmostEqual(
            segment_intersection_t(
                (-1.0, 1.0),
                (3.0, 1.0),
                (0.0, 0.0),
                (0.0, 2.0),
            ),
            0.25,
        )
        self.assertIsNone(
            segment_intersection_t(
                (0.0, 0.0),
                (1.0, 0.0),
                (0.0, 1.0),
                (1.0, 1.0),
            )
        )

    def test_ray_rect_exit_distance_handles_inside_outside_and_zero_direction(
        self,
    ) -> None:
        rect = (-2.0, -1.0, 2.0, 1.0)

        self.assertAlmostEqual(
            ray_rect_exit_distance((0.0, 0.0), (1.0, 0.0), rect),
            2.0,
        )
        self.assertAlmostEqual(
            ray_rect_exit_distance((0.0, 0.0), (0.0, -1.0), rect),
            1.0,
        )
        self.assertIsNone(ray_rect_exit_distance((3.0, 0.0), (0.0, 1.0), rect))
        self.assertIsNone(ray_rect_exit_distance((-3.0, 3.0), (1.0, 1.0), rect))
        self.assertIsNone(ray_rect_exit_distance((3.0, 0.0), (1.0, 0.0), rect))
        self.assertTrue(
            math.isinf(ray_rect_exit_distance((0.0, 0.0), (0.0, 0.0), rect))
        )
