import unittest
from unittest import mock

from PyQt6.QtCore import QPointF

from core.model import Atom, Bond
from ui.structure_benzene_logic import plan_benzene_ring_points


class _FakePolygon:
    def __init__(self, contains: bool) -> None:
        self._contains = contains

    def containsPoint(self, point: QPointF, fill_rule) -> bool:
        return self._contains


class _FakeRingItem:
    def __init__(self, contains: bool) -> None:
        self._polygon = _FakePolygon(contains)

    def polygon(self):
        return self._polygon


class StructureBenzeneLogicTest(unittest.TestCase):
    def test_plan_benzene_ring_points_prefers_bond_then_atom_then_free(self) -> None:
        center = QPointF(5.0, 6.0)
        bonds = [Bond(1, 2, 1)]
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        }
        regular_ring_points_for_bond = mock.Mock(return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        regular_ring_points_for_atom = mock.Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        compute_free_points = mock.Mock(return_value=[(7.0, 8.0)])

        bond_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=bonds,
            atoms=atoms,
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_points,
        )
        atom_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=9,
            bonds=bonds,
            atoms=atoms,
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_points,
        )
        free_result = plan_benzene_ring_points(
            center,
            attach_atom_id=None,
            attach_bond_id=None,
            bonds=bonds,
            atoms=atoms,
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=regular_ring_points_for_bond,
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=compute_free_points,
        )

        self.assertEqual(bond_result, ([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(atom_result, ([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(free_result, ([QPointF(7.0, 8.0)], []))
        regular_ring_points_for_bond.assert_called_once_with(6, 0, center)
        regular_ring_points_for_atom.assert_called_once_with(6, 1)
        compute_free_points.assert_called_once_with((5.0, 6.0), bond_length=20.0)

    def test_plan_benzene_ring_points_treats_failed_bond_geometry_as_terminal(self) -> None:
        result = plan_benzene_ring_points(
            QPointF(5.0, 6.0),
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=[Bond(1, 2, 1)],
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)},
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=mock.Mock(return_value=None),
            regular_ring_points_for_atom=mock.Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)])),
            compute_free_points=mock.Mock(return_value=[(7.0, 8.0)]),
        )

        self.assertIsNone(result)

    def test_plan_benzene_ring_points_skips_invalid_bond_to_atom_fallback_paths(self) -> None:
        center = QPointF(5.0, 6.0)
        atom_result = ([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)])
        regular_ring_points_for_atom = mock.Mock(return_value=atom_result)

        none_bond_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=[None],
            atoms={1: Atom("C", 0.0, 0.0)},
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=mock.Mock(),
        )
        missing_endpoint_result = plan_benzene_ring_points(
            center,
            attach_atom_id=1,
            attach_bond_id=0,
            bonds=[Bond(1, 2, 1)],
            atoms={1: Atom("C", 0.0, 0.0)},
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=regular_ring_points_for_atom,
            compute_free_points=mock.Mock(),
        )

        self.assertEqual(none_bond_result, atom_result)
        self.assertEqual(missing_endpoint_result, atom_result)
        self.assertEqual(regular_ring_points_for_atom.call_count, 2)

    def test_plan_benzene_ring_points_treats_failed_atom_geometry_as_terminal(self) -> None:
        compute_free_points = mock.Mock(return_value=[(7.0, 8.0)])

        result = plan_benzene_ring_points(
            QPointF(5.0, 6.0),
            attach_atom_id=1,
            attach_bond_id=None,
            bonds=[],
            atoms={1: Atom("C", 0.0, 0.0)},
            ring_items=[],
            bond_length=20.0,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=mock.Mock(return_value=None),
            compute_free_points=compute_free_points,
        )

        self.assertIsNone(result)
        compute_free_points.assert_not_called()

    def test_plan_benzene_ring_points_blocks_free_center_inside_existing_ring(self) -> None:
        result = plan_benzene_ring_points(
            QPointF(5.0, 6.0),
            attach_atom_id=None,
            attach_bond_id=None,
            bonds=[],
            atoms={},
            ring_items=[_FakeRingItem(True)],
            bond_length=20.0,
            regular_ring_points_for_bond=mock.Mock(),
            regular_ring_points_for_atom=mock.Mock(),
            compute_free_points=mock.Mock(return_value=[(7.0, 8.0)]),
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
