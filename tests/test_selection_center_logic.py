import unittest

from PyQt6.QtCore import QPointF

from chemvas.domain.document import Atom
from chemvas.ui.selection.selection_center import bounding_box_center_for_atoms


class SelectionCenterLogicTest(unittest.TestCase):
    def test_bounding_box_center_skips_missing_atoms(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 1.0),
            2: Atom("C", 6.0, 5.0),
            3: Atom("C", 3.0, 11.0),
        }

        bbox_center = bounding_box_center_for_atoms({1, 2, 3, 99}, atoms=atoms)

        self.assertEqual(bbox_center, QPointF(3.0, 6.0))
        self.assertIsNone(bounding_box_center_for_atoms({99}, atoms=atoms))
