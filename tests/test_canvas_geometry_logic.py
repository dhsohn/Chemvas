import math
import unittest

from chemvas.ui.canvas_geometry_logic import (
    line_rect_clip_t,
    line_rect_intersections,
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

    def test_segment_intersection_t_and_line_rect_intersections_cover_hits_and_misses(
        self,
    ) -> None:
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
        self.assertCountEqual(
            line_rect_intersections(
                (-1.0, 1.0),
                (3.0, 1.0),
                (0.0, 0.0, 2.0, 2.0),
            ),
            [0.25, 0.75],
        )
        self.assertEqual(
            line_rect_intersections(
                (-1.0, 3.0),
                (3.0, 3.0),
                (0.0, 0.0, 2.0, 2.0),
            ),
            [],
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

    def test_module_is_importable_without_qt(self) -> None:
        # The *_logic role contract: pure, Qt-free helpers. Importing this
        # module in a fresh interpreter must not pull PyQt6 into sys.modules.
        import os
        import subprocess
        import sys
        from pathlib import Path

        app_root = Path(__file__).resolve().parents[1] / "app"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            path for path in (str(app_root), env.get("PYTHONPATH")) if path
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import chemvas.ui.canvas_geometry_logic; "
                    "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                    "for name in sys.modules)"
                ),
            ],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
