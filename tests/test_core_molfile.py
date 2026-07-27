import math
import unittest

from chemvas.core.molfile import (
    MolfileError,
    MolfileLimitError,
    MolfileParseError,
    fit_molfile_model,
    parse_molfile,
    write_molfile,
)
from chemvas.domain.document import MoleculeModel

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
        model.add_atom(
            "C",
            40 * math.cos(math.radians(60 * i)),
            40 * math.sin(math.radians(60 * i)),
        )
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

    @unittest.skipUnless(
        _RealChem is not None, "RDKit is required for round-trip tests"
    )
    def test_benzene_round_trips_through_rdkit(self) -> None:
        mol = _RealChem.MolFromMolBlock(write_molfile(_benzene()))
        self.assertIsNotNone(mol)
        self.assertEqual(mol.GetNumAtoms(), 6)
        self.assertEqual(mol.GetNumBonds(), 6)
        self.assertEqual(_RealChem.MolToSmiles(mol), "c1ccccc1")

    @unittest.skipUnless(
        _RealChem is not None, "RDKit is required for round-trip tests"
    )
    def test_ethanol_round_trips_through_rdkit(self) -> None:
        mol = _RealChem.MolFromMolBlock(write_molfile(_ethanol()))
        self.assertIsNotNone(mol)
        self.assertEqual(_RealChem.MolToSmiles(mol), "CCO")

    @unittest.skipUnless(
        _RealChem is not None, "RDKit is required for round-trip tests"
    )
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

    def test_radical_count_above_two_raises_instead_of_being_collapsed(self) -> None:
        model = _ethanol()

        with self.assertRaisesRegex(MolfileLimitError, "without data loss"):
            write_molfile(model, atom_annotations={0: {"radical_electrons": 3}})

    def test_negative_radical_count_raises_instead_of_being_reinterpreted(self) -> None:
        model = _ethanol()

        with self.assertRaisesRegex(MolfileLimitError, "without data loss"):
            write_molfile(model, atom_annotations={0: {"radical_electrons": -1}})

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


def _annotated_stereo_model() -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
    """A molecule exercising every construct the writer emits: bond orders
    1/2/3, wedge/hash stereo, formal charges, and radicals."""
    model = MoleculeModel()
    a = model.add_atom("C", 0.0, 0.0)
    b = model.add_atom("N", 30.0, 0.0)
    c = model.add_atom("O", 60.0, 15.0)
    d = model.add_atom("C", 30.0, -30.0)
    e = model.add_atom("C", 0.0, -30.0)
    model.add_bond(a, b, 1)
    model.add_bond(b, c, 1)
    model.add_bond(b, d, 2)
    model.add_bond(a, e, 3)
    model.bonds[0].style = "wedge"
    model.bonds[1].style = "hash"
    model.bonds[2].style = "double"
    model.bonds[3].style = "triple"
    annotations = {
        b: {"formal_charge": 1},
        c: {"formal_charge": -1},
        d: {"radical_electrons": 1},
        e: {"radical_electrons": 2},
    }
    return model, annotations


def _average_bond_length(model: MoleculeModel) -> float:
    lengths = [
        math.hypot(
            model.atoms[bond.a].x - model.atoms[bond.b].x,
            model.atoms[bond.a].y - model.atoms[bond.b].y,
        )
        for bond in model.bonds
        if bond is not None
    ]
    return sum(lengths) / len(lengths)


def _bounds_center(model: MoleculeModel) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = model.bounds()
    return (min_x + (max_x - min_x) / 2.0, min_y + (max_y - min_y) / 2.0)


def _replaced_line(block: str, index: int, line: str) -> str:
    lines = block.splitlines()
    lines[index] = line
    return "\n".join(lines) + "\n"


class MolfileParserRoundTripTest(unittest.TestCase):
    def test_graph_charges_stereo_and_coordinates_survive_round_trip(self) -> None:
        model, annotations = _annotated_stereo_model()

        parsed = parse_molfile(write_molfile(model, atom_annotations=annotations))

        # Undo the writer's normalisation with the original scale/placement so
        # the coordinates can be compared directly.
        fit_molfile_model(
            parsed,
            bond_length=_average_bond_length(model),
            center=_bounds_center(model),
        )
        self.assertEqual(set(parsed.atoms), set(model.atoms))
        for atom_id, atom in model.atoms.items():
            self.assertEqual(parsed.atoms[atom_id].element, atom.element)
            self.assertAlmostEqual(parsed.atoms[atom_id].x, atom.x, delta=0.01)
            self.assertAlmostEqual(parsed.atoms[atom_id].y, atom.y, delta=0.01)
        self.assertEqual(
            [(bond.a, bond.b, bond.order, bond.style) for bond in parsed.bonds],
            [(bond.a, bond.b, bond.order, bond.style) for bond in model.bonds],
        )
        self.assertEqual(parsed.atom_annotations, annotations)

    def test_fit_centers_the_structure_and_applies_the_bond_length(self) -> None:
        parsed = parse_molfile(write_molfile(_far_offset_ethanol()))

        fit_molfile_model(parsed, bond_length=48.0)

        self.assertAlmostEqual(_average_bond_length(parsed), 48.0, delta=0.01)
        center_x, center_y = _bounds_center(parsed)
        self.assertAlmostEqual(center_x, 0.0, delta=0.01)
        self.assertAlmostEqual(center_y, 0.0, delta=0.01)

    def test_single_atom_without_bonds_lands_on_the_center(self) -> None:
        model = MoleculeModel()
        model.add_atom("Fe", 123.0, -456.0)

        parsed = parse_molfile(write_molfile(model))
        fit_molfile_model(parsed, bond_length=48.0, center=(10.0, 20.0))

        self.assertEqual(parsed.atoms[0].element, "Fe")
        self.assertAlmostEqual(parsed.atoms[0].x, 10.0, delta=0.01)
        self.assertAlmostEqual(parsed.atoms[0].y, 20.0, delta=0.01)


class MolfileParserErrorTest(unittest.TestCase):
    def test_v3000_counts_line_raises(self) -> None:
        block = write_molfile(_ethanol()).replace("V2000", "V3000")

        with self.assertRaisesRegex(MolfileParseError, "V3000"):
            parse_molfile(block)

    def test_junk_counts_line_raises(self) -> None:
        block = _replaced_line(write_molfile(_ethanol()), 3, "not a counts line")

        with self.assertRaisesRegex(MolfileParseError, "V2000"):
            parse_molfile(block)

    def test_malformed_atom_count_raises(self) -> None:
        block = write_molfile(_ethanol())
        counts_line = block.splitlines()[3]
        block = _replaced_line(block, 3, "  x" + counts_line[3:])

        with self.assertRaisesRegex(MolfileParseError, "malformed atom count"):
            parse_molfile(block)

    def test_every_unsupported_counts_field_rejects_non_zero_data(self) -> None:
        field_ranges = (
            (6, 9),
            (9, 12),
            (12, 15),
            (15, 18),
            (18, 21),
            (21, 24),
            (24, 27),
            (27, 30),
        )
        original = write_molfile(_ethanol())
        counts_line = original.splitlines()[3]

        for start, end in field_ranges:
            with self.subTest(field=(start, end)):
                block = _replaced_line(
                    original,
                    3,
                    counts_line[:start] + "  1" + counts_line[end:],
                )
                with self.assertRaisesRegex(MolfileParseError, "unsupported"):
                    parse_molfile(block)

    def test_exact_counts_property_line_count_is_accepted(self) -> None:
        original = write_molfile(_ethanol())
        counts_line = original.splitlines()[3]
        block = _replaced_line(original, 3, counts_line[:30] + "  1" + counts_line[33:])

        parsed = parse_molfile(block)

        self.assertEqual(len(parsed.atoms), 3)

    def test_exact_counts_multiple_property_line_count_is_accepted(self) -> None:
        annotations = {
            0: {"formal_charge": 1},
            1: {"radical_electrons": 1},
        }
        original = write_molfile(_ethanol(), atom_annotations=annotations)
        counts_line = original.splitlines()[3]
        block = _replaced_line(original, 3, counts_line[:30] + "  3" + counts_line[33:])

        parsed = parse_molfile(block)

        self.assertEqual(parsed.atom_annotations, annotations)

    def test_incorrect_counts_property_line_count_raises(self) -> None:
        original = write_molfile(_ethanol())
        counts_line = original.splitlines()[3]
        block = _replaced_line(original, 3, counts_line[:30] + "  2" + counts_line[33:])

        with self.assertRaisesRegex(MolfileParseError, "declares 2 property lines"):
            parse_molfile(block)

    def test_truncated_file_raises(self) -> None:
        block = write_molfile(_ethanol())

        with self.assertRaisesRegex(MolfileParseError, "ends before"):
            parse_molfile("\n".join(block.splitlines()[:5]) + "\n")

    def test_missing_end_terminator_raises(self) -> None:
        lines = write_molfile(_ethanol()).splitlines()

        with self.assertRaisesRegex(MolfileParseError, "'M  END'"):
            parse_molfile("\n".join(lines[:-1]) + "\n")

    def test_content_after_end_terminator_raises(self) -> None:
        block = write_molfile(_ethanol()) + "$$$$\n"

        with self.assertRaisesRegex(MolfileParseError, "after 'M  END'"):
            parse_molfile(block)

    def test_unknown_element_symbol_raises(self) -> None:
        block = write_molfile(_ethanol())
        atom_line = block.splitlines()[4]
        block = _replaced_line(block, 4, atom_line[:31] + "Xx " + atom_line[34:])

        with self.assertRaisesRegex(MolfileParseError, "'Xx'"):
            parse_molfile(block)

    def test_non_zero_z_coordinate_raises(self) -> None:
        block = write_molfile(_ethanol())
        atom_line = block.splitlines()[4]
        block = _replaced_line(block, 4, atom_line[:20] + "    1.0000" + atom_line[30:])

        with self.assertRaisesRegex(MolfileParseError, "z"):
            parse_molfile(block)

    def test_atom_block_charge_code_raises_instead_of_being_discarded(self) -> None:
        block = write_molfile(_ethanol())
        atom_line = block.splitlines()[4]
        block = _replaced_line(block, 4, atom_line[:36] + "  3" + atom_line[39:])

        with self.assertRaisesRegex(MolfileParseError, "atom-block charge code 3"):
            parse_molfile(block)

    def test_every_unsupported_atom_field_rejects_non_zero_data(self) -> None:
        field_ranges = (
            (34, 36),
            (36, 39),
            (39, 42),
            (42, 45),
            (45, 48),
            (48, 51),
            (51, 54),
            (54, 57),
            (57, 60),
            (60, 63),
            (63, 66),
            (66, 69),
        )
        original = write_molfile(_ethanol())
        atom_line = original.splitlines()[4]

        for start, end in field_ranges:
            with self.subTest(field=(start, end)):
                value = f"{1:>{end - start}}"
                block = _replaced_line(
                    original, 4, atom_line[:start] + value + atom_line[end:]
                )
                with self.assertRaisesRegex(MolfileParseError, "unsupported"):
                    parse_molfile(block)

    def test_unsupported_bond_order_raises(self) -> None:
        block = _replaced_line(write_molfile(_ethanol()), 7, "  1  2  4  0  0  0  0")

        with self.assertRaisesRegex(MolfileParseError, "order 4"):
            parse_molfile(block)

    def test_unsupported_stereo_flag_raises(self) -> None:
        block = _replaced_line(write_molfile(_ethanol()), 7, "  1  2  1  4  0  0  0")

        with self.assertRaisesRegex(MolfileParseError, "stereo flag 4"):
            parse_molfile(block)

    def test_every_unsupported_bond_field_rejects_non_zero_data(self) -> None:
        original = write_molfile(_ethanol())
        bond_line = original.splitlines()[7]

        for start, end in ((12, 15), (15, 18), (18, 21)):
            with self.subTest(field=(start, end)):
                block = _replaced_line(
                    original,
                    7,
                    bond_line[:start] + "  1" + bond_line[end:],
                )
                with self.assertRaisesRegex(MolfileParseError, "unsupported"):
                    parse_molfile(block)

    def test_bond_data_after_supported_fields_raises(self) -> None:
        original = write_molfile(_ethanol())
        bond_line = original.splitlines()[7]
        block = _replaced_line(original, 7, bond_line + "  1")

        with self.assertRaisesRegex(MolfileParseError, "after the V2000 bond fields"):
            parse_molfile(block)

    def test_bond_atom_index_outside_atom_block_raises(self) -> None:
        block = _replaced_line(write_molfile(_ethanol()), 7, "  1  9  1  0  0  0  0")

        with self.assertRaisesRegex(MolfileParseError, "atom 9"):
            parse_molfile(block)

    def test_duplicate_bond_raises(self) -> None:
        block = write_molfile(_ethanol())
        lines = block.splitlines()
        lines.insert(8, lines[7])
        counts_line = lines[3]
        lines[3] = counts_line[:3] + "  3" + counts_line[6:]

        with self.assertRaisesRegex(MolfileParseError, "invalid"):
            parse_molfile("\n".join(lines) + "\n")

    def test_charge_outside_mdl_range_raises(self) -> None:
        lines = write_molfile(_ethanol()).splitlines()
        lines.insert(-1, "M  CHG  1   1  16")

        with self.assertRaisesRegex(MolfileParseError, "outside the MDL range"):
            parse_molfile("\n".join(lines) + "\n")

    def test_singlet_radical_code_raises_instead_of_changing_multiplicity(self) -> None:
        lines = write_molfile(_ethanol()).splitlines()
        lines.insert(-1, "M  RAD  1   1   1")

        with self.assertRaisesRegex(MolfileParseError, "singlet spin multiplicity"):
            parse_molfile("\n".join(lines) + "\n")

    def test_unsupported_property_line_raises(self) -> None:
        lines = write_molfile(_ethanol()).splitlines()
        lines.insert(-1, "M  ISO  1   1   2")

        with self.assertRaisesRegex(MolfileParseError, "unsupported line"):
            parse_molfile("\n".join(lines) + "\n")

    def test_parse_error_is_a_molfile_error(self) -> None:
        # Callers that already surface MolfileError for export failures can
        # reuse the same handling for import failures.
        self.assertTrue(issubclass(MolfileParseError, MolfileError))


if __name__ == "__main__":
    unittest.main()
