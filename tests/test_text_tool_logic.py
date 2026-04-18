import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.history import AddAtomsCommand
from core.model import Atom, Bond, MoleculeModel
from core.text_tool_logic import (
    build_created_atom_command,
    normalize_text_symbol,
    plan_text_input,
    resolve_text_tool_target,
)


class TextToolLogicTest(unittest.TestCase):
    def test_normalize_text_symbol_strips_whitespace(self) -> None:
        self.assertEqual(normalize_text_symbol("  Cl  "), "Cl")

    def test_plan_text_input_marks_prompt_need_and_initial_value(self) -> None:
        direct = plan_text_input("  Cl  ", existing_element="C")
        self.assertEqual(direct.text, "Cl")
        self.assertFalse(direct.needs_prompt)
        self.assertEqual(direct.initial, "C")

        prompted = plan_text_input("   ", existing_element="N")
        self.assertIsNone(prompted.text)
        self.assertTrue(prompted.needs_prompt)
        self.assertEqual(prompted.initial, "N")

    def test_resolve_text_tool_target_prefers_valid_hover_atom_and_snaps_position(self) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 1.0, 2.0), 2: Atom("O", 8.0, 9.0)})

        target = resolve_text_tool_target(
            model,
            pos=(10.0, 20.0),
            hover_atom_id=2,
            item_atom_id=1,
            nearby_atom_id=1,
        )

        self.assertEqual(target.atom_id, 2)
        self.assertEqual(target.pos, (8.0, 9.0))

    def test_resolve_text_tool_target_ignores_invalid_ids_and_falls_back_to_nearby_bond(self) -> None:
        model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )

        target = resolve_text_tool_target(
            model,
            pos=(9.0, 0.0),
            hover_atom_id=99,
            item_atom_id=98,
            hover_bond_id=97,
            nearby_bond_id=0,
            nearby_atom_id=96,
        )

        self.assertEqual(target.atom_id, 2)
        self.assertEqual(target.pos, (10.0, 0.0))

    def test_resolve_text_tool_target_uses_atom_near_without_snapping_position(self) -> None:
        model = MoleculeModel(atoms={1: Atom("C", 1.0, 2.0)})

        target = resolve_text_tool_target(
            model,
            pos=(4.0, 5.0),
            nearby_atom_id=1,
        )

        self.assertEqual(target.atom_id, 1)
        self.assertEqual(target.pos, (4.0, 5.0))

    def test_build_created_atom_command_preserves_history_metadata(self) -> None:
        command = build_created_atom_command(
            atom_id=3,
            atom_state={"element": "Cl", "x": 5.0, "y": 6.0},
            before_next_atom_id=3,
            after_next_atom_id=4,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        self.assertIsInstance(command, AddAtomsCommand)
        self.assertEqual(command.atom_states, {3: {"element": "Cl", "x": 5.0, "y": 6.0}})
        self.assertEqual(command.before_next_atom_id, 3)
        self.assertEqual(command.after_next_atom_id, 4)
        self.assertEqual(command.before_smiles_input, "before")
        self.assertEqual(command.after_smiles_input, "after")


if __name__ == "__main__":
    unittest.main()
