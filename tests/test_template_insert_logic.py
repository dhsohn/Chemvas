import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.template_insert_logic import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplatePointResolvers,
    plan_template_commit,
    plan_template_preview,
    resolve_template_insert,
)


def _make_resolvers(**overrides) -> TemplatePointResolvers:
    resolvers = TemplatePointResolvers(
        regular_ring_radius=Mock(return_value=12.5),
        ring_points=Mock(return_value=[(1.0, 2.0), (3.0, 4.0)]),
        regular_ring_points_for_bond=Mock(return_value=[(5.0, 6.0), (7.0, 8.0)]),
        chair_points=Mock(return_value=[(-1.0, -1.0), (1.0, 1.0)]),
        boat_points=Mock(return_value=[(-2.0, -2.0), (2.0, 2.0)]),
        template_points_for_bond=Mock(return_value=[(9.0, 10.0), (11.0, 12.0)]),
    )
    for name, value in overrides.items():
        object.__setattr__(resolvers, name, value)
    return resolvers


class TemplateInsertLogicTest(unittest.TestCase):
    def test_plan_commit_defaults_missing_style_to_regular(self) -> None:
        plan = plan_template_commit(
            TemplateInsertRequest(ring_size=5, cursor_pos=(10.0, 20.0), ring_style=None)
        )

        assert plan is not None
        self.assertEqual(plan.generator, "free_regular_ring")
        self.assertEqual(plan.ring_style, "regular")
        self.assertEqual(plan.radius_mode, "regular_polygon")

    def test_plan_commit_rejects_invalid_requests(self) -> None:
        self.assertIsNone(
            plan_template_commit(TemplateInsertRequest(ring_size=2, cursor_pos=(0.0, 0.0), ring_style="regular"))
        )
        self.assertIsNone(
            plan_template_commit(TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), ring_style="weird")))

    def test_plan_commit_routes_hexagonal_benzene_to_special_flow(self) -> None:
        plan = plan_template_commit(
            TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), bond_id=7, ring_style="benzene")
        )

        assert plan is not None
        self.assertEqual(plan.generator, "benzene")
        self.assertEqual(plan.bond_id, 7)
        self.assertEqual(plan.ring_style, "benzene")

    def test_plan_preview_keeps_benzene_on_generic_ring_paths(self) -> None:
        free_plan = plan_template_preview(
            TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), ring_style="benzene")
        )
        bond_plan = plan_template_preview(
            TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), bond_id=3, ring_style="benzene")
        )

        assert free_plan is not None
        assert bond_plan is not None
        self.assertEqual(free_plan.generator, "free_regular_ring")
        self.assertEqual(free_plan.radius_mode, "bond_length")
        self.assertEqual(bond_plan.generator, "bond_regular_ring")

    def test_plan_commit_routes_template_shapes_by_bond_presence(self) -> None:
        chair_plan = plan_template_commit(
            TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), bond_id=2, ring_style="chair")
        )
        boat_plan = plan_template_commit(
            TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), ring_style="boat")
        )

        assert chair_plan is not None
        assert boat_plan is not None
        self.assertEqual(chair_plan.generator, "bond_template_shape")
        self.assertEqual(chair_plan.template_shape, "chair")
        self.assertEqual(boat_plan.generator, "free_template_shape")
        self.assertEqual(boat_plan.template_shape, "boat")

    def test_resolve_free_regular_ring_uses_regular_radius(self) -> None:
        request = TemplateInsertRequest(ring_size=5, cursor_pos=(4.0, 5.0), ring_style="regular")
        plan = plan_template_commit(request)
        resolvers = _make_resolvers()

        assert plan is not None
        resolution = resolve_template_insert(request, plan, resolvers)

        assert resolution is not None
        self.assertEqual(resolution.points, [(1.0, 2.0), (3.0, 4.0)])
        resolvers.regular_ring_radius.assert_called_once_with(5)
        resolvers.ring_points.assert_called_once_with((4.0, 5.0), 5, 12.5)

    def test_resolve_free_non_regular_ring_uses_default_radius(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(1.0, 2.0), ring_style="benzene")
        plan = plan_template_preview(request)
        resolvers = _make_resolvers()

        assert plan is not None
        resolution = resolve_template_insert(request, plan, resolvers)

        assert resolution is not None
        resolvers.regular_ring_radius.assert_not_called()
        resolvers.ring_points.assert_called_once_with((1.0, 2.0), 6, None)

    def test_resolve_bond_template_shape_builds_local_points_before_projection(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(15.0, -3.0), bond_id=4, ring_style="chair")
        plan = plan_template_commit(request)
        chair_points = Mock(return_value=[(-1.0, 0.0), (1.0, 0.0)])
        template_points_for_bond = Mock(return_value=[(8.0, 9.0), (10.0, 11.0)])
        resolvers = _make_resolvers(
            chair_points=chair_points,
            template_points_for_bond=template_points_for_bond,
        )

        assert plan is not None
        resolution = resolve_template_insert(request, plan, resolvers)

        assert resolution is not None
        self.assertEqual(resolution.points, [(8.0, 9.0), (10.0, 11.0)])
        chair_points.assert_called_once_with((0.0, 0.0))
        template_points_for_bond.assert_called_once_with([(-1.0, 0.0), (1.0, 0.0)], 4, (15.0, -3.0))

    def test_resolve_free_template_shape_uses_cursor_position_as_center(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(-2.0, 7.0), ring_style="boat")
        plan = plan_template_commit(request)
        boat_points = Mock(return_value=[(20.0, 21.0), (22.0, 23.0)])
        resolvers = _make_resolvers(boat_points=boat_points)

        assert plan is not None
        resolution = resolve_template_insert(request, plan, resolvers)

        assert resolution is not None
        self.assertEqual(resolution.points, [(20.0, 21.0), (22.0, 23.0)])
        boat_points.assert_called_once_with((-2.0, 7.0))

    def test_resolve_bond_regular_ring_delegates_to_bond_resolver(self) -> None:
        request = TemplateInsertRequest(ring_size=7, cursor_pos=(3.0, 4.0), bond_id=8, ring_style="regular")
        plan = plan_template_commit(request)
        regular_ring_points_for_bond = Mock(return_value=[(30.0, 31.0), (32.0, 33.0)])
        resolvers = _make_resolvers(regular_ring_points_for_bond=regular_ring_points_for_bond)

        assert plan is not None
        resolution = resolve_template_insert(request, plan, resolvers)

        assert resolution is not None
        self.assertEqual(resolution.points, [(30.0, 31.0), (32.0, 33.0)])
        regular_ring_points_for_bond.assert_called_once_with(7, 8, (3.0, 4.0))

    def test_resolve_returns_none_when_bond_projection_fails(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), bond_id=5, ring_style="boat")
        plan = plan_template_commit(request)
        resolvers = _make_resolvers(template_points_for_bond=Mock(return_value=None))

        assert plan is not None
        self.assertIsNone(resolve_template_insert(request, plan, resolvers))

    def test_resolve_rejects_invalid_internal_bond_plans(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), ring_style="regular")
        resolvers = _make_resolvers()

        self.assertIsNone(
            resolve_template_insert(
                request,
                TemplateInsertPlan(
                    generator="bond_regular_ring",
                    ring_size=6,
                    ring_style="regular",
                    bond_id=None,
                ),
                resolvers,
            )
        )
        self.assertIsNone(
            resolve_template_insert(
                request,
                TemplateInsertPlan(
                    generator="bond_template_shape",
                    ring_size=6,
                    ring_style="chair",
                    bond_id=None,
                    template_shape="chair",
                ),
                resolvers,
            )
        )

    def test_resolve_rejects_unknown_generator_and_missing_template_shape(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), ring_style="regular")
        resolvers = _make_resolvers()

        self.assertIsNone(
            resolve_template_insert(
                request,
                TemplateInsertPlan(
                    generator="unknown",
                    ring_size=6,
                    ring_style="regular",
                    bond_id=None,
                ),
                resolvers,
            )
        )
        with self.assertRaises(ValueError):
            resolve_template_insert(
                request,
                TemplateInsertPlan(
                    generator="free_template_shape",
                    ring_size=6,
                    ring_style="chair",
                    bond_id=None,
                    template_shape=None,
                ),
                resolvers,
            )

    def test_resolve_benzene_returns_special_resolution_without_point_generation(self) -> None:
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(0.0, 0.0), bond_id=9, ring_style="benzene")
        plan = plan_template_commit(request)
        resolvers = _make_resolvers()

        assert plan is not None
        resolution = resolve_template_insert(request, plan, resolvers)

        assert resolution is not None
        self.assertIsNone(resolution.points)
        resolvers.regular_ring_radius.assert_not_called()
        resolvers.ring_points.assert_not_called()
        resolvers.regular_ring_points_for_bond.assert_not_called()
        resolvers.chair_points.assert_not_called()
        resolvers.boat_points.assert_not_called()
        resolvers.template_points_for_bond.assert_not_called()


if __name__ == "__main__":
    unittest.main()
