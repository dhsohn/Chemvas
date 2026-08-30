import unittest
from unittest import mock

from chemvas.domain.document import Atom, Bond
from chemvas.ui.structure_benzene_logic import plan_benzene_ring_points


def _make_point(x: float, y: float) -> tuple[float, float]:
    return (x, y)


class StructureBenzeneLogicTest(unittest.TestCase):
    def test_plan_benzene_ring_points_prefers_bond_then_atom_then_free(self) -> None:
        center = (5.0, 6.0)
        bonds = [Bond(1, 2, 1)]
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        }
        regular_ring_points_for_bond = mock.Mock(
            return_value=([(1.0, 2.0)], [(1, 0.0, 0.0)])
        )
        regular_ring_points_for_atom = mock.Mock(
            return_value=([(3.0, 4.0)], [(1, 0.0, 0.0)])
        )
        compute_free_points = mock.Mock(return_value=[(7.0, 8.0)])

        bond_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=bonds,
            atoms=atoms,
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_points,
            make_point=_make_point,
        )
        atom_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=9,
            bonds=bonds,
            atoms=atoms,
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_points,
            make_point=_make_point,
        )
        free_result = plan_benzene_ring_points(
            center,
            attach_atom_id=None,
            attach_bond_id=None,
            bonds=bonds,
            atoms=atoms,
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_points,
            make_point=_make_point,
        )

        self.assertEqual(bond_result, ([(1.0, 2.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(atom_result, ([(3.0, 4.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(free_result, ([(7.0, 8.0)], []))
        regular_ring_points_for_bond.assert_called_once_with(6, 0, center)
        regular_ring_points_for_atom.assert_called_once_with(6, 1)
        compute_free_points.assert_called_once_with((5.0, 6.0), bond_length=20.0)

    def test_plan_benzene_ring_points_treats_failed_bond_geometry_as_terminal(
        self,
    ) -> None:
        result = plan_benzene_ring_points(
            (5.0, 6.0),
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=[Bond(1, 2, 1)],
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)},
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=mock.Mock(return_value=None),
            regular_ring_points_for_atom=mock.Mock(
                return_value=([(3.0, 4.0)], [(1, 0.0, 0.0)])
            ),
            compute_free_points=mock.Mock(return_value=[(7.0, 8.0)]),
            make_point=_make_point,
        )

        self.assertIsNone(result)

    def test_plan_benzene_ring_points_skips_invalid_bond_to_atom_fallback_paths(
        self,
    ) -> None:
        center = (5.0, 6.0)
        atom_result = ([(3.0, 4.0)], [(1, 0.0, 0.0)])
        regular_ring_points_for_atom = mock.Mock(return_value=atom_result)

        none_bond_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=[None],
            atoms={1: Atom("C", 0.0, 0.0)},
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=mock.Mock(),
            make_point=_make_point,
        )
        missing_endpoint_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=[Bond(1, 2, 1)],
            atoms={1: Atom("C", 0.0, 0.0)},
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=mock.Mock(),
            make_point=_make_point,
        )

        self.assertEqual(none_bond_result, atom_result)
        self.assertEqual(missing_endpoint_result, atom_result)
        self.assertEqual(regular_ring_points_for_atom.call_count, 2)

    def test_plan_benzene_ring_points_treats_failed_atom_geometry_as_terminal(
        self,
    ) -> None:
        compute_free_points = mock.Mock(return_value=[(7.0, 8.0)])

        result = plan_benzene_ring_points(
            (5.0, 6.0),
            attach_atom_id=1,
            attach_bond_id=None,
            bonds=[],
            atoms={1: Atom("C", 0.0, 0.0)},
            bond_length=20.0,
            center_inside_existing_ring=lambda: False,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=mock.Mock(return_value=None),
            compute_free_points=compute_free_points,
            make_point=_make_point,
        )

        self.assertIsNone(result)
        compute_free_points.assert_not_called()

    def test_plan_benzene_ring_points_blocks_free_center_inside_existing_ring(
        self,
    ) -> None:
        ring_check = mock.Mock(return_value=True)

        result = plan_benzene_ring_points(
            (5.0, 6.0),
            attach_atom_id=None,
            attach_bond_id=None,
            bonds=[],
            atoms={},
            bond_length=20.0,
            center_inside_existing_ring=ring_check,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=mock.Mock(),
            compute_free_points=mock.Mock(return_value=[(7.0, 8.0)]),
            make_point=_make_point,
        )

        self.assertIsNone(result)
        ring_check.assert_called_once_with()

    def test_plan_benzene_ring_points_skips_ring_check_when_attaching(self) -> None:
        ring_check = mock.Mock(return_value=True)

        result = plan_benzene_ring_points(
            (5.0, 6.0),
            attach_atom_id=1,
            attach_bond_id=None,
            bonds=[],
            atoms={1: Atom("C", 0.0, 0.0)},
            bond_length=20.0,
            center_inside_existing_ring=ring_check,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=mock.Mock(
                return_value=([(3.0, 4.0)], [(1, 0.0, 0.0)])
            ),
            compute_free_points=mock.Mock(),
            make_point=_make_point,
        )

        self.assertEqual(result, ([(3.0, 4.0)], [(1, 0.0, 0.0)]))
        ring_check.assert_not_called()

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
                    "import chemvas.ui.structure_benzene_logic; "
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
