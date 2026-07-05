import math
import unittest

from core.model import Atom, Bond
from PyQt6.QtCore import QPointF
from ui.structure_growth_logic import (
    alternating_ring_bond_specs,
    crown_ether_elements,
    fused_benzene_centers,
    mirrored_local_points,
    other_atom_id_from_bond_result,
    resolve_bond_placement_context,
)


class StructureGrowthLogicTest(unittest.TestCase):
    def test_fused_benzene_centers_cover_count_and_mode_variants(self) -> None:
        center = QPointF(10.0, 20.0)

        count_two = fused_benzene_centers(center, 30.0, 2)
        angled = fused_benzene_centers(center, 30.0, 3, mode="angled")
        linear = fused_benzene_centers(center, 30.0, 3, mode="linear")

        self.assertEqual([(point.x(), point.y()) for point in count_two], [(-5.0, 20.0), (25.0, 20.0)])
        self.assertEqual([(point.x(), point.y()) for point in angled[:2]], [(-20.0, 20.0), (10.0, 20.0)])
        self.assertAlmostEqual(angled[2].x(), 25.0)
        self.assertAlmostEqual(angled[2].y(), 20.0 + 30.0 * math.sqrt(3.0) / 2.0)
        self.assertEqual([(point.x(), point.y()) for point in linear], [(-20.0, 20.0), (10.0, 20.0), (40.0, 20.0)])

    def test_crown_ether_elements_marks_oxygen_stride(self) -> None:
        self.assertEqual(
            crown_ether_elements(12, 4),
            ["O", "C", "C", "O", "C", "C", "O", "C", "C", "O", "C", "C"],
        )

    def test_other_atom_id_from_bond_result_handles_missing_and_non_matching_anchor(self) -> None:
        self.assertEqual(other_atom_id_from_bond_result(1, (1, 2)), 2)
        self.assertEqual(other_atom_id_from_bond_result(2, (1, 2)), 1)
        self.assertIsNone(other_atom_id_from_bond_result(3, (1, 2)))
        self.assertIsNone(other_atom_id_from_bond_result(1, None))

    def test_resolve_bond_placement_context_validates_bond_and_atoms(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 4.0),
        }
        bonds = [Bond(1, 2, 1), None]

        placement = resolve_bond_placement_context(0, bonds=bonds, atoms=atoms)

        self.assertIsNotNone(placement)
        assert placement is not None
        self.assertEqual((placement.midpoint.x(), placement.midpoint.y()), (5.0, 2.0))
        self.assertIsNone(resolve_bond_placement_context(1, bonds=bonds, atoms=atoms))
        self.assertIsNone(resolve_bond_placement_context(5, bonds=bonds, atoms=atoms))
        self.assertIsNone(resolve_bond_placement_context(0, bonds=bonds, atoms={1: atoms[1]}))

    def test_mirrored_points_and_alternating_ring_specs(self) -> None:
        points = [QPointF(1.0, 2.0), QPointF(3.0, -4.0)]

        self.assertEqual(
            [(point.x(), point.y()) for point in mirrored_local_points(points, mirrored=False)],
            [(1.0, 2.0), (3.0, -4.0)],
        )
        self.assertEqual(
            [(point.x(), point.y()) for point in mirrored_local_points(points, mirrored=True)],
            [(1.0, -2.0), (3.0, 4.0)],
        )
        self.assertEqual(
            alternating_ring_bond_specs([0, 1, 2, 3]),
            [(0, 1, 2), (1, 2, 1), (2, 3, 2), (3, 0, 1)],
        )
        self.assertEqual(
            alternating_ring_bond_specs([0, 1, 2, 3], first_order=1),
            [(0, 1, 1), (1, 2, 2), (2, 3, 1), (3, 0, 2)],
        )


if __name__ == "__main__":
    unittest.main()
