from copy import deepcopy

import pytest

from chemvas.domain.document import MoleculeModel
from chemvas.features.rendering import overvalent_atom_ids, snapped_to_hex_grid


def _star(element, count, charge=0):
    model = MoleculeModel()
    center = model.add_atom(element, 0, 0)
    model.atom_annotations[center] = {"formal_charge": charge}
    for index in range(count):
        neighbor = model.add_atom("H", index + 1, 0)
        model.add_bond(center, neighbor)
    return model


@pytest.mark.parametrize(
    "element,charge,limit",
    [
        ("H", 0, 1),
        ("B", 0, 3),
        ("B", -1, 4),
        ("C", 0, 4),
        ("C", 1, 3),
        ("C", -1, 3),
        ("N", 0, 3),
        ("N", 1, 4),
        ("N", -1, 2),
        ("O", 0, 2),
        ("O", 1, 3),
        ("O", -1, 1),
        ("F", 0, 1),
        ("F", -1, 0),
    ],
)
def test_warning_boundary_and_no_model_mutation(element, charge, limit):
    allowed = _star(element, limit, charge)
    assert overvalent_atom_ids(allowed) == set()
    excess = _star(element, limit + 1, charge)
    before = deepcopy(excess)
    assert overvalent_atom_ids(excess) == {0}
    assert excess == before


def test_supported_warning_decisions_match_independent_rdkit_valence_checks():
    pytest.importorskip("rdkit")
    from rdkit import Chem, rdBase

    with rdBase.BlockLogs():
        for element, charges in (
            ("C", (-1, 0, 1)),
            ("N", (-1, 0, 1)),
            ("O", (-1, 0, 1)),
            ("B", (-1, 0)),
            ("H", (0,)),
            ("F", (-1, 0)),
        ):
            for charge in charges:
                for count in range(7):
                    model = _star(element, count, charge)
                    mol = Chem.RWMol()
                    for atom_id, atom in model.atoms.items():
                        rd_atom = Chem.Atom(atom.element)
                        rd_atom.SetNoImplicit(True)
                        rd_atom.SetFormalCharge(charge if atom_id == 0 else 0)
                        mol.AddAtom(rd_atom)
                    for bond in model.bonds:
                        mol.AddBond(bond.a, bond.b, Chem.BondType.SINGLE)
                    problems = Chem.DetectChemistryProblems(mol)
                    expected = {
                        p.GetAtomIdx()
                        for p in problems
                        if p.GetType() == "AtomValenceException"
                    }
                    assert overvalent_atom_ids(model) == expected, (
                        element,
                        charge,
                        count,
                    )


def test_ambiguous_drawing_conventions_are_not_declared_invalid():
    for element in ("P", "S", "Fe", "NH2", "Ph"):
        assert not overvalent_atom_ids(_star(element, 6))
    radical = _star("C", 5)
    radical.atom_annotations[0]["radical_electrons"] = 1
    assert not overvalent_atom_ids(radical)
    partial = _star("C", 5)
    partial.bonds[0].style = "dotted"
    assert not overvalent_atom_ids(partial)
    coordinated = _star("N", 4)
    coordinated.atoms[1].element = "Zn"
    assert not overvalent_atom_ids(coordinated)


def test_multiple_bond_orders_are_counted():
    model = _star("C", 3)
    model.bonds[0].order = 3
    assert overvalent_atom_ids(model) == {0, 1}


@pytest.mark.parametrize(
    "point,expected",
    [((12, 1), (10, 0)), ((-12, -1), (-10, 0)), ((4, 9), (5, 8.660254037844386))],
)
def test_hex_snap_lands_on_honeycomb_vertices(point, expected):
    assert snapped_to_hex_grid(point, step=10) == pytest.approx(expected)
    assert snapped_to_hex_grid(expected, step=10) == pytest.approx(expected)
