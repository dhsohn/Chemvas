import unittest

from ui.hover_highlight_logic import HoverUpdatePlan, plan_structure_hover_update
from ui.selection_hit_logic import StructureHit


class HoverHighlightLogicTest(unittest.TestCase):
    def test_plan_structure_hover_update_handles_no_atom_cases(self) -> None:
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=False,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=None,
                free_preview_key=None,
            ),
            HoverUpdatePlan(action="clear"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=False,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key="wedge:1:8.0:9.0",
                preferred_hit=None,
                free_preview_key="wedge:1:8.0:9.0",
            ),
            HoverUpdatePlan(action="noop"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=False,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=None,
                free_preview_key="wedge:1:8.0:9.0",
            ),
            HoverUpdatePlan(action="free_bond_preview", preview_key="wedge:1:8.0:9.0"),
        )

    def test_plan_structure_hover_update_handles_missing_and_invalid_hits(self) -> None:
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=None,
            ),
            HoverUpdatePlan(action="clear"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=StructureHit(kind="other", id=None),
            ),
            HoverUpdatePlan(action="clear"),
        )

    def test_plan_structure_hover_update_handles_atom_hit_paths(self) -> None:
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=1,
                current_hover_bond_id=None,
                current_preview_key="wedge:1:13.0:14.0",
                preferred_hit=StructureHit(kind="atom", id=1),
                atom_preview_signature="wedge:1",
                atom_preview_key="wedge:1:13.0:14.0",
            ),
            HoverUpdatePlan(action="noop"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=StructureHit(kind="atom", id=1),
                atom_preview_signature="wedge:1",
                atom_preview_key=None,
            ),
            HoverUpdatePlan(action="clear"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=StructureHit(kind="atom", id=1),
                atom_preview_signature="wedge:1",
                atom_preview_key="wedge:1:13.0:14.0",
            ),
            HoverUpdatePlan(action="atom_hit", hover_atom_id=1, preview_key="wedge:1:13.0:14.0"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=StructureHit(kind="atom", id=2),
                atom_preview_signature=None,
                atom_preview_key=None,
            ),
            HoverUpdatePlan(action="atom_hit", hover_atom_id=2, preview_key=None),
        )

    def test_plan_structure_hover_update_handles_bond_hit_paths(self) -> None:
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=3,
                current_preview_key="hash",
                preferred_hit=StructureHit(kind="bond", id=3),
                bond_preview_key="hash",
            ),
            HoverUpdatePlan(action="noop"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=StructureHit(kind="bond", id=4),
                bond_preview_key="wedge",
            ),
            HoverUpdatePlan(action="bond_hit", hover_bond_id=4, preview_key="wedge"),
        )
        self.assertEqual(
            plan_structure_hover_update(
                has_atoms=True,
                current_hover_atom_id=None,
                current_hover_bond_id=None,
                current_preview_key=None,
                preferred_hit=StructureHit(kind="bond", id=5),
                bond_preview_key=None,
            ),
            HoverUpdatePlan(action="bond_hit", hover_bond_id=5, preview_key=None),
        )


if __name__ == "__main__":
    unittest.main()
