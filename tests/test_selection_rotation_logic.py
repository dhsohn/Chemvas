import math
import unittest

from PyQt6.QtCore import QPointF

from core.model import Atom, Bond
from ui.selection_rotation_logic import rotated_atom_positions, selected_rotation_atom_ids


class SelectionRotationLogicTest(unittest.TestCase):
    def test_selected_rotation_atom_ids_expands_valid_bonds_only(self) -> None:
        atom_ids = selected_rotation_atom_ids(
            {1},
            {0, 1, 3, 9},
            bonds=[Bond(2, 3, 1), None, Bond(7, 8, 1), Bond(3, 4, 1)],
        )

        self.assertEqual(atom_ids, {1, 2, 3, 4})

    def test_rotated_atom_positions_rotates_about_center_and_skips_missing_atoms(self) -> None:
        rotated = rotated_atom_positions(
            {1, 2, 99},
            atoms={
                1: Atom("C", 1.0, 0.0),
                2: Atom("O", 0.0, 1.0),
            },
            center=QPointF(0.5, 0.5),
            angle_radians=math.pi / 2.0,
        )

        self.assertEqual(set(rotated), {1, 2})
        self.assertAlmostEqual(rotated[1][0], 1.0)
        self.assertAlmostEqual(rotated[1][1], 1.0)
        self.assertAlmostEqual(rotated[2][0], 0.0)
        self.assertAlmostEqual(rotated[2][1], 0.0)


if __name__ == "__main__":
    unittest.main()
