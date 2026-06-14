import unittest

from core.model import Atom, MoleculeModel


class MoleculeModelTest(unittest.TestCase):
    def test_post_init_sets_next_atom_id_from_existing_atoms(self) -> None:
        model = MoleculeModel(atoms={2: Atom("C", 0.0, 0.0), 7: Atom("O", 1.0, 1.0)})
        self.assertEqual(model.next_atom_id, 8)

    def test_add_atom_and_bond_update_model_state(self) -> None:
        model = MoleculeModel()

        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 2.0, 3.0)
        bond_id = model.add_bond(a0, a1, 2)

        self.assertEqual(a0, 0)
        self.assertEqual(a1, 1)
        self.assertEqual(model.next_atom_id, 2)
        self.assertEqual(model.atoms[a0].element, "C")
        self.assertEqual(model.atoms[a1].element, "O")
        self.assertEqual(bond_id, 0)
        self.assertEqual(len(model.bonds), 1)
        self.assertEqual(model.bonds[0].a, a0)
        self.assertEqual(model.bonds[0].b, a1)
        self.assertEqual(model.bonds[0].order, 2)

    def test_add_bond_rejects_invalid_endpoints_and_orders(self) -> None:
        model = MoleculeModel()
        a0 = model.add_atom("C", 0.0, 0.0)
        a1 = model.add_atom("O", 2.0, 0.0)

        cases = [
            (float(a0), a1, 1),
            (True, a1, 1),
            (a0, 99, 1),
            (99, a1, 1),
            (a0, a0, 1),
            (a0, a1, 0),
            (a0, a1, 4),
            (a0, a1, "1"),
        ]

        for a, b, order in cases:
            with self.subTest(a=a, b=b, order=order):
                with self.assertRaises(ValueError):
                    model.add_bond(a, b, order)
                self.assertEqual(model.bonds, [])

    def test_bounds_returns_zeroes_for_empty_model(self) -> None:
        model = MoleculeModel()
        self.assertEqual(model.bounds(), (0.0, 0.0, 0.0, 0.0))

    def test_bounds_returns_extrema_for_existing_atoms(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", -1.5, 4.0)
        model.add_atom("N", 3.0, -2.0)
        model.add_atom("O", 0.5, 1.0)

        self.assertEqual(model.bounds(), (-1.5, -2.0, 3.0, 4.0))

    def test_find_atom_near_returns_nearest_match_within_threshold(self) -> None:
        model = MoleculeModel()
        near_id = model.add_atom("C", 1.0, 1.0)
        model.add_atom("O", 4.0, 4.0)

        found = model.find_atom_near(1.4, 1.2, max_dist=1.0)

        self.assertEqual(found, near_id)

    def test_find_atom_near_returns_none_outside_threshold(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", 0.0, 0.0)

        found = model.find_atom_near(10.0, 10.0, max_dist=1.0)

        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
