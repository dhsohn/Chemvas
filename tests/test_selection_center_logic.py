import unittest

from chemvas.domain.document import Atom
from chemvas.features.selection import (
    bounding_box_center_for_atoms,
    center_for_atoms,
)
from PyQt6.QtCore import QPointF


class SelectionCenterLogicTest(unittest.TestCase):
    def test_center_helpers_average_and_bounding_box_skip_missing_atoms(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 1.0),
            2: Atom("C", 6.0, 5.0),
            3: Atom("C", 3.0, 11.0),
        }

        centroid = center_for_atoms({1, 2, 3, 99}, atoms=atoms)
        bbox_center = bounding_box_center_for_atoms({1, 2, 3, 99}, atoms=atoms)

        self.assertEqual(centroid, QPointF(3.0, 17.0 / 3.0))
        self.assertEqual(bbox_center, QPointF(3.0, 6.0))
        self.assertIsNone(center_for_atoms({99}, atoms=atoms))
        self.assertIsNone(bounding_box_center_for_atoms({99}, atoms=atoms))


if __name__ == "__main__":
    unittest.main()
