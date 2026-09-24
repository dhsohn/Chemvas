import unittest

from chemvas.domain.document import Atom, Bond, MoleculeModel


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


class MoleculeModelAccessTest(unittest.TestCase):
    def test_lookups_tolerate_missing_ids(self) -> None:
        atom = Atom("O", 3.0, 4.0)
        bond = Bond(1, 2)
        model = MoleculeModel(atoms={1: atom}, bonds=[None, bond])

        self.assertIs(model.atom_for_id(1), atom)
        self.assertIsNone(model.atom_for_id(99))
        self.assertIsNone(model.atom_for_id(None))
        self.assertIs(model.bond_for_id(1), bond)
        self.assertIsNone(model.bond_for_id(0))
        self.assertIsNone(model.bond_for_id(-1))
        self.assertIsNone(model.bond_for_id(None))
        self.assertIsNone(model.bond_for_id(99))
        self.assertEqual(list(model.bond_ids_from(0)), [0, 1])
        self.assertTrue(model.has_bond_slot(1))
        self.assertFalse(model.has_bond_slot(2))

    def test_bond_slots_pad_clear_and_trim_without_renumbering(self) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)})

        bond_id = model.add_bond(1, 2, 2)
        model.set_bond(3, Bond(4, 5, 1))
        self.assertEqual(bond_id, 0)
        self.assertEqual(model.bonds, [Bond(1, 2, 2), None, None, Bond(4, 5, 1)])

        model.clear_bond(0)
        model.clear_bond(99)
        model.trim_bonds(2)
        self.assertEqual(model.bonds, [None, None])

    def test_atom_slots_and_next_id(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", 1.0, 2.0)
        model.set_atom(5, Atom("O", 5.0, 6.0))
        model.ensure_next_atom_id_after(5)
        self.assertEqual(model.next_atom_id, 6)
        self.assertEqual(model.created_atom_ids_from(1), [5])

        model.pop_atom(5)
        model.pop_atom(99)
        self.assertEqual(set(model.atoms), {0})

    def test_atom_annotations_keep_only_non_zero_known_integers(self) -> None:
        model = MoleculeModel(atoms={1: Atom("N", 0.0, 0.0)})

        model.set_atom_annotation(
            1, {"formal_charge": 1, "radical_electrons": 0, "other": 3}
        )
        self.assertEqual(model.atom_annotation_for(1), {"formal_charge": 1})

        model.set_atom_annotation(1, {"formal_charge": 0})
        self.assertIsNone(model.atom_annotation_for(1))
        self.assertNotIn(1, model.atom_annotations)

        model.set_atom_annotation(1, {"radical_electrons": 2})
        model.set_atom(1, Atom("C", 0.0, 0.0))
        self.assertIsNone(model.atom_annotation_for(1))

    def test_center_and_scale_about(self) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 4.0, 2.0)})

        self.assertEqual(model.center(), (2.0, 1.0))
        model.scale_about(2.0, 1.0, 2.0)
        self.assertEqual((model.atoms[1].x, model.atoms[1].y), (-2.0, -1.0))
        self.assertEqual((model.atoms[2].x, model.atoms[2].y), (6.0, 3.0))
