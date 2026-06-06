import unittest
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QPointF
from ui.structure_growth_build_service import (
    StructureGrowthBuildActions,
    StructureGrowthBuildService,
)


class _FakeOwner:
    def __init__(self) -> None:
        self.committer = SimpleNamespace(add_atom_label=mock.Mock())
        self.atom_point = mock.Mock(side_effect=lambda atom_id: QPointF(float(atom_id), float(atom_id + 1)))
        self.sprout_bond_endpoint = mock.Mock(return_value=QPointF(20.0, 0.0))
        self.add_bond_between_points = mock.Mock(return_value=(1, 2))
        self.add_benzene_ring = mock.Mock(return_value="ring")
        self.has_atom = mock.Mock(return_value=True)
        self.default_bond_endpoint = mock.Mock(return_value=QPointF(30.0, 0.0))
        self.regular_ring_points_for_atom = mock.Mock(return_value=([QPointF(1.0, 1.0)], [(7, 1.0, 1.0)]))
        self.regular_ring_points_for_bond = mock.Mock(return_value=([QPointF(2.0, 2.0)], [(1, 2.0, 2.0)]))
        self.cyclohexane_chair_points = mock.Mock(return_value=[QPointF(1.0, 2.0), QPointF(3.0, -4.0)])
        self.template_points_for_bond = mock.Mock(return_value=([QPointF(5.0, 5.0)], [(1, 5.0, 5.0)]))
        self.add_ring_from_points = mock.Mock()
        self.bond_placement_context = mock.Mock(return_value=SimpleNamespace(midpoint=QPointF(9.0, 10.0)))
        self.recorded_actions: list[bool] = []

    def _run_recorded_additions_action(self, action):
        result = action()
        self.recorded_actions.append(result)
        return result


def _actions_for(owner: _FakeOwner) -> StructureGrowthBuildActions:
    return StructureGrowthBuildActions(
        atom_point=lambda atom_id: owner.atom_point(atom_id),
        sprout_bond_endpoint=lambda atom_id, *, cyclic=False: owner.sprout_bond_endpoint(
            atom_id,
            cyclic=cyclic,
        ),
        add_bond_between_points=lambda start, end, style, order: owner.add_bond_between_points(
            start,
            end,
            style,
            order,
        ),
        add_benzene_ring=lambda center, **kwargs: owner.add_benzene_ring(center, **kwargs),
        has_atom=lambda atom_id: owner.has_atom(atom_id),
        default_bond_endpoint=lambda start, start_atom_id: owner.default_bond_endpoint(start, start_atom_id),
        add_atom_label=lambda atom_id, element, **kwargs: owner.committer.add_atom_label(
            atom_id,
            element,
            **kwargs,
        ),
        regular_ring_points_for_atom=lambda n, atom_id: owner.regular_ring_points_for_atom(n, atom_id),
        regular_ring_points_for_bond=lambda n, bond_id, midpoint: owner.regular_ring_points_for_bond(
            n,
            bond_id,
            midpoint,
        ),
        cyclohexane_chair_points=lambda center: owner.cyclohexane_chair_points(center),
        template_points_for_bond=lambda points_local, bond_id, midpoint: owner.template_points_for_bond(
            points_local,
            bond_id,
            midpoint,
        ),
        add_ring_from_points=lambda points, **kwargs: owner.add_ring_from_points(points, **kwargs),
        bond_placement_context=lambda bond_id: owner.bond_placement_context(bond_id),
        run_recorded_additions_action=lambda action: owner._run_recorded_additions_action(action),
    )


class StructureGrowthBuildServiceTest(unittest.TestCase):
    def test_sprout_bond_and_benzene_delegate_to_owner_geometry_and_builders(self) -> None:
        owner = _FakeOwner()
        service = StructureGrowthBuildService(_actions_for(owner))

        self.assertEqual(service.sprout_bond_from_atom(7, style="double", order=2, cyclic=True), (1, 2))
        self.assertEqual(service.sprout_benzene_from_atom(7), "ring")

        owner.sprout_bond_endpoint.assert_called_once_with(7, cyclic=True)
        owner.add_bond_between_points.assert_called_once_with(QPointF(7.0, 8.0), QPointF(20.0, 0.0), "double", 2)
        owner.add_benzene_ring.assert_called_once_with(QPointF(7.0, 8.0), attach_atom_id=7)

    def test_sprout_bond_returns_none_when_endpoint_is_missing(self) -> None:
        owner = _FakeOwner()
        owner.sprout_bond_endpoint.return_value = None

        self.assertIsNone(
            StructureGrowthBuildService(_actions_for(owner)).sprout_bond_from_atom(3, style="single", order=1)
        )

        owner.add_bond_between_points.assert_not_called()

    def test_sprout_acetyl_builds_carbonyl_and_labels_oxygen(self) -> None:
        owner = _FakeOwner()
        owner.atom_point.side_effect = lambda atom_id: QPointF({1: 10.0, 2: 20.0}.get(atom_id, 0.0), 0.0)
        owner.add_bond_between_points.side_effect = [(1, 2), (2, 3), (2, 4)]

        StructureGrowthBuildService(_actions_for(owner)).sprout_acetyl_from_atom(1)

        self.assertEqual(
            owner.add_bond_between_points.call_args_list,
            [
                mock.call(QPointF(10.0, 0.0), QPointF(20.0, 0.0), "single", 1),
                mock.call(QPointF(20.0, 0.0), QPointF(30.0, 0.0), "double", 2),
                mock.call(QPointF(20.0, 0.0), QPointF(30.0, 0.0), "single", 1),
            ],
        )
        owner.committer.add_atom_label.assert_called_once_with(3, "O", show_carbon=True)

    def test_ring_growth_and_fuse_helpers_run_recorded_actions(self) -> None:
        owner = _FakeOwner()
        service = StructureGrowthBuildService(_actions_for(owner))

        service.sprout_regular_ring_from_atom(7, 6)
        service.fuse_regular_ring_to_bond(4, 5)
        service.fuse_chair_to_bond(4, mirrored=True)

        self.assertEqual(owner.recorded_actions, [True, True, True])
        owner.add_ring_from_points.assert_has_calls(
            [
                mock.call([QPointF(1.0, 1.0)], merge=[(7, 1.0, 1.0)]),
                mock.call([QPointF(2.0, 2.0)], merge=[(1, 2.0, 2.0)]),
                mock.call([QPointF(5.0, 5.0)], merge=[(1, 5.0, 5.0)]),
            ]
        )
        mirrored_points = owner.template_points_for_bond.call_args.args[0]
        self.assertEqual([(point.x(), point.y()) for point in mirrored_points], [(1.0, -2.0), (3.0, 4.0)])

    def test_fuse_benzene_to_bond_uses_placement_midpoint(self) -> None:
        owner = _FakeOwner()
        service = StructureGrowthBuildService(_actions_for(owner))

        self.assertEqual(service.fuse_benzene_to_bond(4), "ring")

        owner.add_benzene_ring.assert_called_once_with(QPointF(9.0, 10.0), attach_bond_id=4)


if __name__ == "__main__":
    unittest.main()
