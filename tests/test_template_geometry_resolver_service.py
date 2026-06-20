from __future__ import annotations

from unittest import mock

from PyQt6.QtCore import QPointF
from ui.template_geometry_resolver_service import TemplateGeometryResolverService
from ui.template_insert_logic import TemplateInsertRequest, plan_template_preview


def test_template_geometry_resolver_service_builds_template_resolvers() -> None:
    canvas = object()
    service = TemplateGeometryResolverService(canvas)

    with (
        mock.patch("ui.template_geometry_resolver_service.regular_ring_radius_for", return_value=12.0)
        as regular_radius,
        mock.patch(
            "ui.template_geometry_resolver_service.ring_points_for",
            return_value=[QPointF(1.0, 2.0), QPointF(3.0, 4.0)],
        ) as ring_points,
        mock.patch(
            "ui.template_geometry_resolver_service.regular_ring_points_for_atom_for",
            return_value=([QPointF(13.0, 14.0)], "unused"),
        ) as ring_points_for_atom,
        mock.patch(
            "ui.template_geometry_resolver_service.regular_ring_points_for_bond_for",
            return_value=([QPointF(5.0, 6.0)], "unused"),
        ) as ring_points_for_bond,
        mock.patch(
            "ui.template_geometry_resolver_service.cyclohexane_chair_points_for",
            return_value=[QPointF(7.0, 8.0)],
        ) as chair_points,
        mock.patch(
            "ui.template_geometry_resolver_service.cyclohexane_boat_points_for",
            return_value=[QPointF(9.0, 10.0)],
        ) as boat_points,
        mock.patch(
            "ui.template_geometry_resolver_service.template_points_for_bond_for",
            return_value=([QPointF(11.0, 12.0)], "unused"),
        ) as template_points_for_bond,
    ):
        resolvers = service.point_resolvers()

        assert resolvers.regular_ring_radius(6) == 12.0
        assert list(resolvers.ring_points((1.0, 2.0), 6, 12.0)) == [(1.0, 2.0), (3.0, 4.0)]
        assert list(resolvers.regular_ring_points_for_atom(6, 7) or []) == [(13.0, 14.0)]
        assert list(resolvers.regular_ring_points_for_bond(6, 3, (4.0, 5.0)) or []) == [(5.0, 6.0)]
        assert list(resolvers.chair_points((0.0, 0.0))) == [(7.0, 8.0)]
        assert list(resolvers.boat_points((0.0, 0.0))) == [(9.0, 10.0)]
        assert list(resolvers.template_points_for_bond([(0.0, 0.0)], 4, (2.0, 3.0)) or []) == [
            (11.0, 12.0)
        ]

    regular_radius.assert_called_once_with(canvas, 6)
    ring_points.assert_called_once()
    ring_points_for_atom.assert_called_once_with(canvas, 6, 7)
    ring_points_for_bond.assert_called_once()
    chair_points.assert_called_once()
    boat_points.assert_called_once()
    template_points_for_bond.assert_called_once()


def test_template_geometry_resolver_service_resolves_planned_insert_and_pair_points() -> None:
    canvas = object()
    service = TemplateGeometryResolverService(canvas)
    request = TemplateInsertRequest(5, (1.0, 2.0), ring_style="regular")
    plan = plan_template_preview(request)
    assert plan is not None

    with mock.patch("ui.template_geometry_resolver_service.resolve_template_insert") as resolve:
        resolve.return_value = "resolution"

        assert service.resolve_insert(request, plan) == "resolution"

    resolve.assert_called_once()
    assert service.points_from_pairs(None) is None
    assert [(point.x(), point.y()) for point in service.points_from_pairs([(3.0, 4.0)])] == [(3.0, 4.0)]
