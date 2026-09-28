import math
import subprocess
import sys
import unittest
from pathlib import Path

from chemvas.ui.canvas.canvas_geometry_logic import (
    glyph_contour_clip_t,
    glyph_convex_hull,
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

    def test_glyph_hull_closes_gaps_and_discards_duplicate_interior_points(self):
        points = [(0, 0), (4, 0), (4, 2), (0, 2), (1, 1), (2, 1), (4, 0)]
        self.assertEqual(glyph_convex_hull(points), [(0, 0), (4, 0), (4, 2), (0, 2)])
        self.assertEqual(glyph_convex_hull([]), [])
        self.assertEqual(glyph_convex_hull([(1, 1), (1, 1)]), [])

    def test_glyph_contours_include_the_whole_parallel_band(self):
        contour = ((2, 1), (4, 1), (4, 2), (2, 2), (2, 1))
        self.assertIsNone(glyph_contour_clip_t((0, 0), (10, 0), [contour]))
        # Neither edge crosses the ink: the full band still clears it.
        self.assertEqual(
            glyph_contour_clip_t((0, 0), (10, 0), [contour], ((0, -3), (0, 3))),
            (0.2, 0.4),
        )
        self.assertEqual(
            glyph_contour_clip_t((0, 0), (10, 0), [contour], ((-1, -3), (2, 3))),
            (0.0, 0.5),
        )

    def test_glyph_contours_keep_outermost_crossings_and_containment(self):
        left = ((2, -1), (4, -1), (4, 1), (2, 1), (2, -1))
        right = tuple((x + 4, y) for x, y in left)
        self.assertEqual(
            glyph_contour_clip_t((0, 0), (10, 0), [left, right]), (0.2, 0.8)
        )
        self.assertEqual(
            glyph_contour_clip_t((10, 0), (0, 0), [left, right]), (0.2, 0.8)
        )
        self.assertEqual(
            glyph_contour_clip_t((3, 0), (10, 0), [left], start_inside=True),
            (0.0, 1 / 7),
        )
        self.assertEqual(
            glyph_contour_clip_t(
                (3, 0), (3.5, 0), [left], start_inside=True, end_inside=True
            ),
            (0.0, 1.0),
        )
        self.assertIsNone(glyph_contour_clip_t((0, 0), (0, 0), [left]))

    def test_glyph_math_executes_without_qt_or_site_packages(self):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                (
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "from chemvas.ui.canvas.canvas_geometry_logic import glyph_convex_hull, glyph_contour_clip_t; "
                    "hull = glyph_convex_hull([(2,-1),(4,-1),(4,1),(2,1),(3,0)]); "
                    "assert glyph_contour_clip_t((0,0),(10,0),[hull+[hull[0]]]) == (.2,.4); "
                    "assert not any(n.split('.')[0] == 'PyQt6' for n in sys.modules)"
                ),
                str(Path(__file__).resolve().parents[1] / "app"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
