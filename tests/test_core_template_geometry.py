import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.template_geometry import (
    cyclohexane_boat_points,
    cyclohexane_chair_points,
    place_template_on_bond,
    regular_ring_radius,
    regular_ring_points_for_atom,
    regular_ring_points_for_bond,
    ring_points,
    scale_points,
    scale_points_to_bond_length,
)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


class TemplateGeometryTest(unittest.TestCase):
    def assertPointsAlmostEqual(
        self,
        actual: list[tuple[float, float]],
        expected: list[tuple[float, float]],
        places: int = 6,
    ) -> None:
        self.assertEqual(len(actual), len(expected))
        for actual_point, expected_point in zip(actual, expected):
            self.assertAlmostEqual(actual_point[0], expected_point[0], places=places)
            self.assertAlmostEqual(actual_point[1], expected_point[1], places=places)

    def test_regular_ring_radius_matches_polygon_geometry(self) -> None:
        self.assertAlmostEqual(regular_ring_radius(6, 14.0), 14.0)
        self.assertAlmostEqual(regular_ring_radius(5, 12.0), 12.0 / (2.0 * math.sin(math.pi / 5)))

    def test_regular_ring_radius_falls_back_for_invalid_sizes(self) -> None:
        self.assertEqual(regular_ring_radius(0, 9.5), 9.5)
        self.assertEqual(regular_ring_radius(2, 9.5), 9.5)
        self.assertEqual(regular_ring_radius(10_000_000, 9.5), 9.5)

    def test_ring_points_start_at_top_and_rotate_clockwise(self) -> None:
        points = ring_points((10.0, 20.0), 4, 5.0)

        self.assertPointsAlmostEqual(
            points,
            [
                (10.0, 15.0),
                (15.0, 20.0),
                (10.0, 25.0),
                (5.0, 20.0),
            ],
        )

    def test_scale_points_scales_about_center(self) -> None:
        points = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)]

        scaled = scale_points(points, (1.0, 1.0), 0.5)

        self.assertPointsAlmostEqual(
            scaled,
            [
                (0.5, 0.5),
                (1.5, 0.5),
                (1.5, 1.5),
            ],
        )

    def test_scale_points_to_bond_length_scales_first_edge_to_target(self) -> None:
        points = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)]

        scaled = scale_points_to_bond_length(points, (1.0, 1.0), 1.0)

        self.assertAlmostEqual(_distance(scaled[0], scaled[1]), 1.0)
        self.assertPointsAlmostEqual(
            scaled,
            [
                (0.5, 0.5),
                (1.5, 0.5),
                (1.5, 1.5),
            ],
        )

    def test_scale_points_to_bond_length_handles_degenerate_input(self) -> None:
        self.assertEqual(scale_points_to_bond_length([(1.0, 1.0)], (0.0, 0.0), 5.0), [(1.0, 1.0)])
        self.assertEqual(
            scale_points_to_bond_length([(1.0, 1.0), (1.0, 1.0)], (0.0, 0.0), 5.0),
            [(1.0, 1.0), (1.0, 1.0)],
        )
        self.assertEqual(
            scale_points_to_bond_length([(0.0, 0.0), (1.0, 0.0)], (0.0, 0.0), 1.0),
            [(0.0, 0.0), (1.0, 0.0)],
        )

    def test_cyclohexane_chair_points_match_current_reference_shape(self) -> None:
        points = cyclohexane_chair_points((0.0, 0.0), 10.0)

        self.assertPointsAlmostEqual(
            points,
            [
                (-11.404572, 6.749011),
                (-7.658506, -2.522828),
                (2.341494, -2.522828),
                (11.404572, -6.749011),
                (7.658506, 2.522828),
                (-2.341494, 2.522828),
            ],
        )
        for index in range(len(points)):
            self.assertAlmostEqual(_distance(points[index], points[(index + 1) % len(points)]), 10.0, places=6)

    def test_cyclohexane_chair_bounds_are_centered_on_requested_center(self) -> None:
        points = cyclohexane_chair_points((25.0, -4.0), 12.0)
        xs = [x for x, _ in points]
        ys = [y for _, y in points]

        self.assertAlmostEqual((min(xs) + max(xs)) / 2.0, 25.0, places=6)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2.0, -4.0, places=6)

    def test_cyclohexane_boat_points_match_current_reference_shape(self) -> None:
        points = cyclohexane_boat_points((0.0, 0.0), 10.0)

        self.assertPointsAlmostEqual(
            points,
            [
                (-11.713032, -1.561738),
                (-3.904344, -7.808688),
                (3.904344, -7.808688),
                (11.713032, -1.561738),
                (3.904344, 10.151295),
                (-3.904344, 10.151295),
            ],
        )
        self.assertAlmostEqual(_distance(points[0], points[1]), 10.0, places=6)

    def test_cyclohexane_boat_stays_symmetric_around_center_x(self) -> None:
        center = (4.0, -3.0)
        points = cyclohexane_boat_points(center, 8.0)

        self.assertAlmostEqual(points[0][0] + points[3][0], center[0] * 2.0, places=6)
        self.assertAlmostEqual(points[1][0] + points[2][0], center[0] * 2.0, places=6)
        self.assertAlmostEqual(points[4][0] + points[5][0], center[0] * 2.0, places=6)
        self.assertAlmostEqual(points[0][1], points[3][1], places=6)
        self.assertAlmostEqual(points[1][1], points[2][1], places=6)
        self.assertAlmostEqual(points[4][1], points[5][1], places=6)

    def test_regular_ring_points_for_atom_uses_attach_point_as_first_vertex(self) -> None:
        points = regular_ring_points_for_atom(6, (0.0, 0.0), [], 10.0)

        assert points is not None
        self.assertPointsAlmostEqual([points[0]], [(0.0, 0.0)])
        self.assertAlmostEqual(_distance(points[0], points[1]), 10.0, places=6)
        self.assertLess(sum(y for _, y in points) / len(points), 0.0)

    def test_regular_ring_points_for_atom_points_away_from_neighbors(self) -> None:
        points = regular_ring_points_for_atom(6, (0.0, 0.0), [(10.0, 0.0)], 10.0)

        assert points is not None
        self.assertLess(sum(x for x, _ in points) / len(points), 0.0)

    def test_regular_ring_points_for_atom_handles_invalid_and_balanced_neighbors(self) -> None:
        self.assertIsNone(regular_ring_points_for_atom(2, (0.0, 0.0), [], 10.0))
        points = regular_ring_points_for_atom(6, (0.0, 0.0), [(10.0, 0.0), (-10.0, 0.0), (0.0, 0.0)], 10.0)

        assert points is not None
        self.assertGreater(sum(y for _, y in points) / len(points), 0.0)

    def test_place_template_on_bond_aligns_local_edge_to_target_bond(self) -> None:
        points = place_template_on_bond(
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            (2.0, 3.0),
            (5.0, 3.0),
        )

        assert points is not None
        self.assertPointsAlmostEqual(points[:2], [(2.0, 3.0), (5.0, 3.0)])
        self.assertGreater(points[2][1], 3.0)

    def test_place_template_on_bond_uses_center_hint_to_pick_mirror(self) -> None:
        points = place_template_on_bond(
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            (2.0, 3.0),
            (5.0, 3.0),
            center_hint=(2.0, 0.0),
        )

        assert points is not None
        self.assertLess(points[2][1], 3.0)

    def test_place_template_on_bond_rejects_degenerate_inputs(self) -> None:
        self.assertIsNone(place_template_on_bond([(0.0, 0.0)], (0.0, 0.0), (1.0, 0.0)))
        self.assertIsNone(place_template_on_bond([(0.0, 0.0), (0.0, 0.0)], (0.0, 0.0), (1.0, 0.0)))
        self.assertIsNone(place_template_on_bond([(0.0, 0.0), (1.0, 0.0)], (0.0, 0.0), (0.0, 0.0)))

    def test_place_template_on_bond_uses_occupied_polygon_and_can_reject_both_sides(self) -> None:
        triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]

        mirrored = place_template_on_bond(
            triangle,
            (2.0, 3.0),
            (5.0, 3.0),
            occupied_polygon=[(1.0, 3.5), (4.0, 3.5), (4.0, 6.5), (1.0, 6.5)],
        )
        assert mirrored is not None
        self.assertLess(mirrored[2][1], 3.0)

        rejected = place_template_on_bond(
            triangle,
            (2.0, 3.0),
            (5.0, 3.0),
            occupied_polygon=[(1.0, -1.0), (4.0, -1.0), (4.0, 7.0), (1.0, 7.0)],
        )
        self.assertIsNone(rejected)

    def test_place_template_on_bond_keeps_default_side_for_lower_occupied_polygon_and_short_polygon(self) -> None:
        triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]

        points = place_template_on_bond(
            triangle,
            (2.0, 3.0),
            (5.0, 3.0),
            occupied_polygon=[(1.0, -0.5), (4.0, -0.5), (4.0, 2.5), (1.0, 2.5)],
            center_hint=(2.0, 10.0),
        )
        assert points is not None
        self.assertGreater(points[2][1], 3.0)

        short_polygon = place_template_on_bond(
            triangle,
            (2.0, 3.0),
            (5.0, 3.0),
            occupied_polygon=[(0.0, 0.0), (1.0, 1.0)],
        )
        assert short_polygon is not None
        self.assertGreater(short_polygon[2][1], 3.0)

    def test_place_template_on_bond_keeps_default_side_when_center_hint_is_farther_from_mirror(self) -> None:
        points = place_template_on_bond(
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            (2.0, 3.0),
            (5.0, 3.0),
            center_hint=(2.0, 10.0),
        )

        assert points is not None
        self.assertGreater(points[2][1], 3.0)

    def test_regular_ring_points_for_bond_uses_bond_as_first_edge(self) -> None:
        points = regular_ring_points_for_bond(6, (0.0, 0.0), (10.0, 0.0))

        assert points is not None
        self.assertPointsAlmostEqual(points[:2], [(0.0, 0.0), (10.0, 0.0)])
        self.assertAlmostEqual(_distance(points[0], points[1]), 10.0, places=6)
        self.assertAlmostEqual(_distance(points[1], points[2]), 10.0, places=6)

    def test_regular_ring_points_for_bond_uses_center_hint_for_side_selection(self) -> None:
        points = regular_ring_points_for_bond(
            6,
            (0.0, 0.0),
            (10.0, 0.0),
            center_hint=(5.0, -20.0),
        )

        assert points is not None
        self.assertLess(sum(y for _, y in points) / len(points), 0.0)

    def test_regular_ring_points_for_bond_rejects_invalid_input_and_uses_occupied_polygon(self) -> None:
        self.assertIsNone(regular_ring_points_for_bond(2, (0.0, 0.0), (10.0, 0.0)))
        self.assertIsNone(regular_ring_points_for_bond(6, (0.0, 0.0), (0.0, 0.0)))

        points = regular_ring_points_for_bond(
            6,
            (0.0, 0.0),
            (10.0, 0.0),
            occupied_polygon=[(0.0, 2.0), (10.0, 2.0), (10.0, 20.0), (0.0, 20.0)],
        )
        assert points is not None
        self.assertLess(sum(y for _, y in points) / len(points), 0.0)

        self.assertIsNone(
            regular_ring_points_for_bond(
                6,
                (0.0, 0.0),
                (10.0, 0.0),
                occupied_polygon=[(-1.0, -20.0), (11.0, -20.0), (11.0, 20.0), (-1.0, 20.0)],
            )
        )

    def test_regular_ring_points_for_bond_handles_lower_and_non_intersecting_occupied_polygons(self) -> None:
        lower_blocked = regular_ring_points_for_bond(
            6,
            (0.0, 0.0),
            (10.0, 0.0),
            occupied_polygon=[(0.0, -20.0), (10.0, -20.0), (10.0, -2.0), (0.0, -2.0)],
        )
        assert lower_blocked is not None
        self.assertGreater(sum(y for _, y in lower_blocked) / len(lower_blocked), 0.0)

        far_polygon = regular_ring_points_for_bond(
            6,
            (0.0, 0.0),
            (10.0, 0.0),
            occupied_polygon=[(20.0, 20.0), (21.0, 20.0), (21.0, 21.0), (20.0, 21.0)],
        )
        assert far_polygon is not None
        self.assertGreater(sum(y for _, y in far_polygon) / len(far_polygon), 0.0)


if __name__ == "__main__":
    unittest.main()
