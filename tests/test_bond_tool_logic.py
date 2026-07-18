import math
import unittest

from chemvas.core.bond_tool_logic import (
    resolve_bond_endpoint_target,
    resolve_bond_press_target,
    resolve_bond_snap_target,
)
from chemvas.domain.document import Atom, Bond, MoleculeModel


class BondToolLogicTest(unittest.TestCase):
    def assertPointAlmostEqual(
        self,
        actual: tuple[float, float],
        expected: tuple[float, float],
        *,
        places: int = 7,
    ) -> None:
        self.assertAlmostEqual(actual[0], expected[0], places=places)
        self.assertAlmostEqual(actual[1], expected[1], places=places)

    def test_resolve_bond_press_target_prefers_item_then_nearby_then_hover_and_returns_none_for_atom(
        self,
    ) -> None:
        self.assertEqual(
            resolve_bond_press_target(
                atom_id=None,
                item_kind="bond",
                item_bond_id=3,
                nearby_bond_id=4,
                hover_bond_id=5,
            ),
            3,
        )
        self.assertEqual(
            resolve_bond_press_target(
                atom_id=None,
                item_kind="atom",
                item_bond_id=3,
                nearby_bond_id=4,
                hover_bond_id=5,
            ),
            4,
        )
        self.assertEqual(
            resolve_bond_press_target(
                atom_id=None,
                item_kind="note",
                item_bond_id=None,
                nearby_bond_id=None,
                hover_bond_id=5,
            ),
            5,
        )
        self.assertIsNone(
            resolve_bond_press_target(
                atom_id=9,
                item_kind="bond",
                item_bond_id=3,
                nearby_bond_id=4,
                hover_bond_id=5,
            )
        )

    def test_resolve_bond_snap_target_returns_original_pos_when_no_atom_and_no_bond(
        self,
    ) -> None:
        model = MoleculeModel()

        target = resolve_bond_snap_target(
            model,
            pos=(4.0, 5.0),
            atom_id=None,
            bond_id=None,
            start_atom_id=7,
            ignore_start=False,
        )

        self.assertEqual(target.pos, (4.0, 5.0))
        self.assertEqual(target.start_atom_id, 7)

    def test_resolve_bond_snap_target_snaps_to_atom_and_updates_start_atom_id_when_not_ignoring_start(
        self,
    ) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 10.0, 20.0)})

        target = resolve_bond_snap_target(
            model,
            pos=(1.0, 2.0),
            atom_id=1,
            bond_id=None,
            start_atom_id=None,
            ignore_start=False,
        )

        self.assertEqual(target.pos, (10.0, 20.0))
        self.assertEqual(target.start_atom_id, 1)

    def test_resolve_bond_snap_target_returns_original_pos_when_atom_matches_start_and_ignore_start_is_true(
        self,
    ) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 10.0, 20.0)})

        target = resolve_bond_snap_target(
            model,
            pos=(1.0, 2.0),
            atom_id=1,
            bond_id=None,
            start_atom_id=1,
            ignore_start=True,
        )

        self.assertEqual(target.pos, (1.0, 2.0))
        self.assertEqual(target.start_atom_id, 1)

    def test_resolve_bond_snap_target_returns_original_pos_for_missing_atom_id(
        self,
    ) -> None:
        model = MoleculeModel(atoms={})

        target = resolve_bond_snap_target(
            model,
            pos=(1.0, 2.0),
            atom_id=7,
            bond_id=None,
            start_atom_id=3,
            ignore_start=False,
        )

        self.assertEqual(target.pos, (1.0, 2.0))
        self.assertEqual(target.start_atom_id, 3)

    def test_resolve_bond_snap_target_snaps_to_nearer_bond_endpoint(self) -> None:
        model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )

        target = resolve_bond_snap_target(
            model,
            pos=(8.0, 1.0),
            atom_id=None,
            bond_id=0,
            start_atom_id=3,
            ignore_start=True,
        )

        self.assertEqual(target.pos, (10.0, 0.0))
        self.assertEqual(target.start_atom_id, 3)

    def test_resolve_bond_snap_target_returns_original_pos_for_invalid_or_missing_bond(
        self,
    ) -> None:
        pos = (8.0, 1.0)
        start_atom_id = 4

        invalid_id_model = MoleculeModel(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 10.0, 0.0)},
            bonds=[Bond(1, 2, 1)],
        )
        invalid_id_target = resolve_bond_snap_target(
            invalid_id_model,
            pos=pos,
            atom_id=None,
            bond_id=99,
            start_atom_id=start_atom_id,
            ignore_start=False,
        )
        self.assertEqual(invalid_id_target.pos, pos)
        self.assertEqual(invalid_id_target.start_atom_id, start_atom_id)

        missing_bond_model = MoleculeModel(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 10.0, 0.0)},
            bonds=[None],
        )
        missing_bond_target = resolve_bond_snap_target(
            missing_bond_model,
            pos=pos,
            atom_id=None,
            bond_id=0,
            start_atom_id=start_atom_id,
            ignore_start=False,
        )
        self.assertEqual(missing_bond_target.pos, pos)
        self.assertEqual(missing_bond_target.start_atom_id, start_atom_id)

        missing_endpoint_model = MoleculeModel(
            atoms={1: Atom("C", 0.0, 0.0)},
            bonds=[Bond(1, 2, 1)],
        )
        missing_endpoint_target = resolve_bond_snap_target(
            missing_endpoint_model,
            pos=pos,
            atom_id=None,
            bond_id=0,
            start_atom_id=start_atom_id,
            ignore_start=False,
        )
        self.assertEqual(missing_endpoint_target.pos, pos)
        self.assertEqual(missing_endpoint_target.start_atom_id, start_atom_id)

    def test_resolve_bond_endpoint_target_snaps_to_valid_atom_different_from_start_atom(
        self,
    ) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 8.0, -3.0)})

        target = resolve_bond_endpoint_target(
            model,
            start=(0.0, 0.0),
            end=(4.0, 4.0),
            atom_id=2,
            start_atom_id=1,
            snap_angle_step=45,
            bond_length=10.0,
        )

        self.assertEqual(target, (8.0, -3.0))

    def test_resolve_bond_endpoint_target_ignores_start_atom_hit_and_falls_back_to_angle_snap(
        self,
    ) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 0.0, 0.0)})

        target = resolve_bond_endpoint_target(
            model,
            start=(0.0, 0.0),
            end=(3.0, 4.0),
            atom_id=1,
            start_atom_id=1,
            snap_angle_step=90,
            bond_length=10.0,
        )

        self.assertPointAlmostEqual(target, (0.0, 10.0))

    def test_resolve_bond_endpoint_target_falls_back_to_angle_snap_for_missing_atom(
        self,
    ) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 0.0, 0.0)})

        target = resolve_bond_endpoint_target(
            model,
            start=(0.0, 0.0),
            end=(9.0, 1.0),
            atom_id=99,
            start_atom_id=1,
            snap_angle_step=45,
            bond_length=10.0,
        )

        self.assertPointAlmostEqual(target, (10.0, 0.0))

    def test_resolve_bond_endpoint_target_returns_original_end_for_zero_length_drag(
        self,
    ) -> None:
        model = MoleculeModel()
        end = (1.25, -2.5)

        target = resolve_bond_endpoint_target(
            model,
            start=end,
            end=end,
            atom_id=None,
            start_atom_id=None,
            snap_angle_step=45,
            bond_length=10.0,
        )

        self.assertEqual(target, end)

    def test_resolve_bond_endpoint_target_uses_provided_snap_angle_step(self) -> None:
        model = MoleculeModel()

        target = resolve_bond_endpoint_target(
            model,
            start=(0.0, 0.0),
            end=(3.0, 4.0),
            atom_id=None,
            start_atom_id=None,
            snap_angle_step=45,
            bond_length=10.0,
        )

        self.assertPointAlmostEqual(target, (math.sqrt(50.0), math.sqrt(50.0)))

    def test_resolve_bond_endpoint_target_falls_back_to_thirty_degree_snaps_for_falsy_steps(
        self,
    ) -> None:
        model = MoleculeModel()
        expected = (5.0, 5.0 * math.sqrt(3.0))

        for snap_angle_step in (None, 0):
            with self.subTest(snap_angle_step=snap_angle_step):
                target = resolve_bond_endpoint_target(
                    model,
                    start=(0.0, 0.0),
                    end=(3.0, 4.0),
                    atom_id=None,
                    start_atom_id=None,
                    snap_angle_step=snap_angle_step,
                    bond_length=10.0,
                )

                self.assertPointAlmostEqual(target, expected)


if __name__ == "__main__":
    unittest.main()
