import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import MoleculeModel
from ui.smiles_insert_logic import (
    SmilesPreviewResolvers,
    build_smiles_preview_snapshot,
    plan_smiles_commit,
    plan_smiles_preview_update,
    smiles_preview_center,
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
        model.add_bond(right, 999, 1)
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

    def test_plan_smiles_commit_translates_atoms_and_preserves_bond_metadata(self) -> None:
        model = _build_model()

        plan = plan_smiles_commit(model, (0.0, 0.0), (25.0, -5.0))

        assert plan is not None
        self.assertEqual(plan.offset, (25.0, -5.0))
        self.assertEqual(
            [(atom.source_atom_id, atom.element, atom.x, atom.y, atom.color, atom.explicit_label) for atom in plan.atoms],
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

    def test_plan_smiles_commit_rejects_dangling_bond_endpoint(self) -> None:
        self.assertIsNone(plan_smiles_commit(_build_model(include_dangling_bond=True), (0.0, 0.0), (0.0, 0.0)))

    def test_plan_smiles_preview_returns_clear_without_model_center_or_radius(self) -> None:
        resolvers = SmilesPreviewResolvers(parallel_bond_segments=Mock(return_value=[]))
        existing = build_smiles_preview_snapshot({}, ())

        self.assertEqual(
            plan_smiles_preview_update(None, (0.0, 0.0), (1.0, 1.0), 1.0, existing, resolvers).action,
            "clear",
        )
        self.assertEqual(
            plan_smiles_preview_update(_build_model(), None, (1.0, 1.0), 1.0, existing, resolvers).action,
            "clear",
        )
        self.assertEqual(
            plan_smiles_preview_update(_build_model(), (0.0, 0.0), (1.0, 1.0), None, existing, resolvers).action,
            "clear",
        )

    def test_plan_smiles_preview_rebuilds_when_topology_changes(self) -> None:
        model = _build_model()
        segment_resolver = Mock(return_value=[(0.0, 1.0, 2.0, 3.0), (4.0, 5.0, 6.0, 7.0)])
        resolvers = SmilesPreviewResolvers(parallel_bond_segments=segment_resolver)
        existing = build_smiles_preview_snapshot({}, ())

        plan = plan_smiles_preview_update(model, (0.0, 0.0), (10.0, 10.0), 2.0, existing, resolvers)

        self.assertEqual(plan.action, "rebuild")
        assert plan.geometry is not None
        self.assertEqual(plan.geometry.bond_segments[0], ((0.0, 1.0, 2.0, 3.0), (4.0, 5.0, 6.0, 7.0)))
        self.assertEqual(plan.geometry.atom_rects[0], (-2.0, 8.0, 4.0, 4.0))
        self.assertEqual(plan.geometry.atom_rects[1], (18.0, 8.0, 4.0, 4.0))
        segment_resolver.assert_called_once_with(0.0, 10.0, 20.0, 10.0, 2)

    def test_plan_smiles_preview_updates_when_signature_matches(self) -> None:
        model = _build_model()
        segment_resolver = Mock(return_value=[(0.0, 1.0, 2.0, 3.0), (4.0, 5.0, 6.0, 7.0)])
        resolvers = SmilesPreviewResolvers(parallel_bond_segments=segment_resolver)
        existing = build_smiles_preview_snapshot({0: 2}, (0, 1))

        plan = plan_smiles_preview_update(model, (0.0, 0.0), (10.0, 10.0), 2.0, existing, resolvers)

        self.assertEqual(plan.action, "update")
        assert plan.geometry is not None
        self.assertEqual(len(plan.geometry.bond_segments[0]), 2)

    def test_plan_smiles_preview_rebuilds_when_atom_ids_change_even_if_count_matches(self) -> None:
        model = _build_model()
        segment_resolver = Mock(return_value=[(0.0, 1.0, 2.0, 3.0), (4.0, 5.0, 6.0, 7.0)])
        resolvers = SmilesPreviewResolvers(parallel_bond_segments=segment_resolver)
        existing = build_smiles_preview_snapshot({0: 2}, (4, 5))

        plan = plan_smiles_preview_update(model, (0.0, 0.0), (10.0, 10.0), 2.0, existing, resolvers)

        self.assertEqual(plan.action, "rebuild")

    def test_plan_smiles_preview_returns_clear_for_invalid_parallel_segment_result(self) -> None:
        model = _build_model()
        resolvers = SmilesPreviewResolvers(parallel_bond_segments=Mock(return_value=[]))
        existing = build_smiles_preview_snapshot({0: 2}, (0, 1))

        plan = plan_smiles_preview_update(model, (0.0, 0.0), (10.0, 10.0), 2.0, existing, resolvers)

        self.assertEqual(plan.action, "clear")

    def test_plan_smiles_preview_returns_clear_for_dangling_bond_endpoint(self) -> None:
        model = _build_model(include_dangling_bond=True)
        resolvers = SmilesPreviewResolvers(parallel_bond_segments=Mock(return_value=[(0.0, 1.0, 2.0, 3.0)]))
        existing = build_smiles_preview_snapshot({}, ())

        plan = plan_smiles_preview_update(model, (0.0, 0.0), (0.0, 0.0), 2.0, existing, resolvers)

        self.assertEqual(plan.action, "clear")


if __name__ == "__main__":
    unittest.main()
