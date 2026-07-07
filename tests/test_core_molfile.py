import math
import unittest

from core.model import MoleculeModel
from core.molfile import MolfileError, MolfileLimitError, write_molfile

try:
    from rdkit import Chem as _RealChem
except ModuleNotFoundError:
    _RealChem = None


def _ethanol() -> MoleculeModel:
    model = MoleculeModel()
    a = model.add_atom("C", 0.0, 0.0)
    b = model.add_atom("C", 30.0, 0.0)
    c = model.add_atom("O", 60.0, 0.0)
    model.add_bond(a, b, 1)
    model.add_bond(b, c, 1)
    return model


def _far_offset_ethanol() -> MoleculeModel:
    model = MoleculeModel()
    a = model.add_atom("C", 1_000_000.0, -2_000_000.0)
    b = model.add_atom("C", 1_000_030.0, -2_000_000.0)
    c = model.add_atom("O", 1_000_060.0, -2_000_000.0)
    model.add_bond(a, b, 1)
    model.add_bond(b, c, 1)
    return model


def _benzene() -> MoleculeModel:
    model = MoleculeModel()
    ids = [
        model.add_atom("C", 40 * math.cos(math.radians(60 * i)), 40 * math.sin(math.radians(60 * i)))
        for i in range(6)
    ]
    for i in range(6):
        model.add_bond(ids[i], ids[(i + 1) % 6], 2 if i % 2 == 0 else 1)
    return model


class MolfileWriterTest(unittest.TestCase):
    def test_counts_line_and_terminator(self) -> None:
        block = write_molfile(_ethanol())
        lines = block.splitlines()
        self.assertEqual(lines[3], "  3  2  0  0  0  0  0  0  0  0999 V2000")
        self.assertTrue(block.endswith("M  END\n"))

    def test_y_axis_is_flipped_for_mdl_orientation(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", 0.0, 0.0)
        model.add_atom("C", 0.0, 10.0)  # drawn lower on screen (canvas y grows down)
        model.add_bond(0, 1, 1)
        atom_lines = write_molfile(model).splitlines()[4:6]
        y_first = float(atom_lines[0].split()[1])
        y_second = float(atom_lines[1].split()[1])
        self.assertGreater(y_first, y_second)

    def test_far_offset_coordinates_stay_in_v2000_atom_fields(self) -> None:
        block = write_molfile(_far_offset_ethanol())
        if _RealChem is not None:
            mol = _RealChem.MolFromMolBlock(block)
            self.assertIsNotNone(mol)
            self.assertEqual(_RealChem.MolToSmiles(mol), "CCO")
            return

        for line, element in zip(block.splitlines()[4:7], ("C", "C", "O"), strict=True):
            self.assertLessEqual(len(line[0:10]), 10)
            self.assertLessEqual(len(line[10:20]), 10)
            self.assertLessEqual(len(line[20:30]), 10)
            self.assertEqual(line[31:34], f"{element:<3}")

    def test_huge_same_sign_coordinate_center_does_not_emit_infinity(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", 1e308, 1e308)

        block = write_molfile(model)

        self.assertNotIn("inf", block.lower())
        self.assertEqual(block.splitlines()[4][0:30], "    0.0000    0.0000    0.0000")

    def test_wedge_and_hash_styles_become_stereo_flags(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", 0.0, 0.0)
        model.add_atom("C", 30.0, 0.0)
        model.add_atom("C", 60.0, 0.0)
        model.add_bond(0, 1, 1)
        model.add_bond(1, 2, 1)
        model.bonds[0].style = "wedge"
        model.bonds[1].style = "hash"
        bond_lines = write_molfile(model).splitlines()[7:9]
        self.assertEqual(int(bond_lines[0][9:12]), 1)  # wedge -> up
        self.assertEqual(int(bond_lines[1][9:12]), 6)  # hash -> down

    def test_unsupported_label_raises(self) -> None:
        model = MoleculeModel()
        model.add_atom("Me", 0.0, 0.0)
        model.add_atom("O", 30.0, 0.0)
        model.add_bond(0, 1, 1)
        with self.assertRaises(MolfileError) as ctx:
            write_molfile(model)
        self.assertIn("Me", str(ctx.exception))

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for round-trip tests")
    def test_benzene_round_trips_through_rdkit(self) -> None:
        mol = _RealChem.MolFromMolBlock(write_molfile(_benzene()))
        self.assertIsNotNone(mol)
        self.assertEqual(mol.GetNumAtoms(), 6)
        self.assertEqual(mol.GetNumBonds(), 6)
        self.assertEqual(_RealChem.MolToSmiles(mol), "c1ccccc1")

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for round-trip tests")
    def test_ethanol_round_trips_through_rdkit(self) -> None:
        mol = _RealChem.MolFromMolBlock(write_molfile(_ethanol()))
        self.assertIsNotNone(mol)
        self.assertEqual(_RealChem.MolToSmiles(mol), "CCO")

    @unittest.skipUnless(_RealChem is not None, "RDKit is required for round-trip tests")
    def test_formal_charge_survives_round_trip(self) -> None:
        model = MoleculeModel()
        model.add_atom("N", 0.0, 0.0)
        block = write_molfile(model, atom_annotations={0: {"formal_charge": 1}})
        self.assertIn("M  CHG", block)
        mol = _RealChem.MolFromMolBlock(block)
        self.assertIsNotNone(mol)
        self.assertEqual(mol.GetAtomWithIdx(0).GetFormalCharge(), 1)


class MolfileLimitsTest(unittest.TestCase):
    def test_atom_count_over_v2000_limit_raises(self) -> None:
        model = MoleculeModel()
        for index in range(1000):
            model.add_atom("C", float(index), 0.0)

        with self.assertRaisesRegex(MolfileLimitError, "at most 999 atoms"):
            write_molfile(model)

    def test_limit_raises_before_alias_rejection(self) -> None:
        # A too-large drawing containing an abbreviation must surface the hard
        # limit, not the alias error that callers retry through RDKit.
        model = MoleculeModel()
        model.add_atom("Ph", 0.0, 0.0)
        for index in range(1000):
            model.add_atom("C", float(index + 1), 0.0)

        with self.assertRaisesRegex(MolfileLimitError, "at most 999 atoms"):
            write_molfile(model)

    def test_charge_outside_mdl_range_raises(self) -> None:
        model = _ethanol()

        with self.assertRaisesRegex(MolfileLimitError, "outside the MDL range"):
            write_molfile(model, atom_annotations={0: {"formal_charge": 16}})

    def test_charge_at_mdl_range_boundary_is_written(self) -> None:
        model = _ethanol()

        block = write_molfile(model, atom_annotations={0: {"formal_charge": -15}})

        self.assertIn("M  CHG  1   1 -15", block)

    def test_coordinate_span_outside_v2000_field_raises(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", -100_000_000.0, 0.0)
        model.add_atom("C", 100_000_000.0, 0.0)

        with self.assertRaisesRegex(MolfileLimitError, "10-character atom-field"):
            write_molfile(model)

    def test_coordinate_center_overflow_raises_limit_error(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", -1e308, 0.0)
        model.add_atom("C", 1e308, 0.0)

        with self.assertRaisesRegex(MolfileLimitError, "finite V2000"):
            write_molfile(model)

    def test_coordinate_scale_overflow_raises_limit_error(self) -> None:
        model = MoleculeModel()
        atom_1 = model.add_atom("C", 0.0, 0.0)
        atom_2 = model.add_atom("C", 1.4e308, 1.4e308)
        model.add_bond(atom_1, atom_2, 1)

        with self.assertRaisesRegex(MolfileLimitError, "finite V2000"):
            write_molfile(model)


if __name__ == "__main__":
    unittest.main()
