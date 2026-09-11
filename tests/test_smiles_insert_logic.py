import math
import unittest

from chemvas.domain.document import Bond, MoleculeModel
from chemvas.features.insertion import (
    plan_smiles_commit,
    smiles_preview_center,
    smiles_preview_offset,
)


def _build_model(*, include_dangling_bond: bool = False) -> MoleculeModel:
    model = MoleculeModel()
    left = model.add_atom("C", -10.0, 0.0)
    right = model.add_atom("N", 10.0, 0.0)
    model.atoms[right].color = "#336699"
    model.atoms[right].explicit_label = True
    model.add_bond(left, right, 2)
    model.bonds[0].style = "double"
    model.bonds[0].color = "#123456"
    if include_dangling_bond:
        model.bonds.append(Bond(right, 999, 1))
    return model


def _build_single_bond_model_with_sparse_prefix() -> MoleculeModel:
    model = MoleculeModel()
    left = model.add_atom("C", -5.0, 0.0)
    right = model.add_atom("O", 5.0, 0.0)
    model.add_bond(left, right, 1)
    model.bonds.insert(0, None)
    return model


class SmilesInsertLogicTest(unittest.TestCase):
    def test_smiles_preview_center_returns_bounds_center(self) -> None:
        model = _build_model()

        self.assertEqual(smiles_preview_center(model), (0.0, 0.0))
        self.assertIsNone(smiles_preview_center(MoleculeModel()))
        self.assertIsNone(smiles_preview_center(None))

    def test_plan_smiles_commit_returns_none_without_model_or_center(self) -> None:
        self.assertIsNone(plan_smiles_commit(None, (0.0, 0.0), (1.0, 2.0)))
        self.assertIsNone(plan_smiles_commit(MoleculeModel(), (0.0, 0.0), (1.0, 2.0)))
        self.assertIsNone(plan_smiles_commit(_build_model(), None, (1.0, 2.0)))

    def test_plan_smiles_commit_translates_atoms_and_preserves_bond_metadata(
        self,
    ) -> None:
        model = _build_model()

        plan = plan_smiles_commit(model, (0.0, 0.0), (25.0, -5.0))

        assert plan is not None
        self.assertEqual(plan.offset, (25.0, -5.0))
        self.assertEqual(
            [
                (
                    atom.source_atom_id,
                    atom.element,
                    atom.x,
                    atom.y,
                    atom.color,
                    atom.explicit_label,
                )
                for atom in plan.atoms
            ],
            [
                (0, "C", 15.0, -5.0, "#000000", False),
                (1, "N", 35.0, -5.0, "#336699", True),
            ],
        )
        self.assertEqual(len(plan.bonds), 1)
        self.assertEqual(
            (
                plan.bonds[0].source_bond_id,
                plan.bonds[0].source_a,
                plan.bonds[0].source_b,
                plan.bonds[0].order,
                plan.bonds[0].style,
                plan.bonds[0].color,
            ),
            (0, 0, 1, 2, "double", "#123456"),
        )

    def test_plan_smiles_commit_preserves_atom_annotations_and_mark_placements(
        self,
    ) -> None:
        model = _build_model()
        model.atom_annotations = {
            1: {"formal_charge": 1, "radical_electrons": 2},
            99: {"formal_charge": -1},
        }

        plan = plan_smiles_commit(model, (0.0, 0.0), (25.0, -5.0))

        assert plan is not None
        self.assertEqual(
            plan.annotations, {1: {"formal_charge": 1, "radical_electrons": 2}}
        )
        self.assertEqual(
            [(mark.source_atom_id, mark.kind, mark.x, mark.y) for mark in plan.marks],
            [
                (1, "plus", 35.0 + math.sqrt(2.0), -5.0),
                (1, "radical", 35.0, -5.0 - math.sqrt(2.0)),
                (1, "radical", 35.0, -5.0 + math.sqrt(2.0)),
            ],
        )

    def test_plan_smiles_commit_rejects_dangling_bond_endpoint(self) -> None:
        self.assertIsNone(
            plan_smiles_commit(
                _build_model(include_dangling_bond=True), (0.0, 0.0), (0.0, 0.0)
            )
        )

    def test_plan_smiles_commit_skips_none_bonds(self) -> None:
        model = _build_single_bond_model_with_sparse_prefix()

        plan = plan_smiles_commit(model, (0.0, 0.0), (3.0, 4.0))

        assert plan is not None
        self.assertEqual(len(plan.bonds), 1)
        self.assertEqual(plan.bonds[0].source_bond_id, 1)
        self.assertEqual(plan.bonds[0].order, 1)

    def test_smiles_preview_offset_carries_the_center_to_the_cursor(self) -> None:
        self.assertEqual(smiles_preview_offset((5.0, -2.0), (25.0, 8.0)), (20.0, 10.0))
        self.assertEqual(smiles_preview_offset((3.0, 3.0), (3.0, 3.0)), (0.0, 0.0))
