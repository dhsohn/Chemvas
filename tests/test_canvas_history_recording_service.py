import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.history import AddAtomsCommand, AddBondCommand, AddSceneItemsCommand, CompositeCommand, UpdateBondCommand
from ui.canvas_history_recording_service import CanvasHistoryRecordingService


def _make_canvas(
    *,
    atoms=None,
    bonds=None,
    next_atom_id=0,
    last_smiles_input="after-smiles",
    history_enabled=True,
):
    return SimpleNamespace(
        _push_command=mock.Mock(),
        _atom_state_dict=mock.Mock(side_effect=lambda atom_id: {"atom_id": atom_id, "kind": "atom"}),
        _bond_state_dict=mock.Mock(side_effect=lambda bond: {"bond": getattr(bond, "name", "bond")}),
        scene_item_state=mock.Mock(side_effect=lambda item: {"item": getattr(item, "name", "item")}),
        model=SimpleNamespace(
            atoms=dict(atoms or {}),
            bonds=list(bonds or []),
            next_atom_id=next_atom_id,
        ),
        last_smiles_input=last_smiles_input,
        _history_enabled=history_enabled,
    )


class CanvasHistoryRecordingServiceTest(unittest.TestCase):
    def test_record_additions_pushes_composite_command_for_atom_bond_and_scene_items(self) -> None:
        existing_bond = SimpleNamespace(name="existing-bond")
        new_bond = SimpleNamespace(name="new-bond")
        scene_item = SimpleNamespace(name="arrow")
        canvas = _make_canvas(
            atoms={1: object(), 2: object()},
            bonds=[existing_bond, new_bond],
            next_atom_id=3,
        )

        CanvasHistoryRecordingService(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=1,
            before_smiles_input="before-smiles",
            added_scene_items=[scene_item],
        )

        canvas._push_command.assert_called_once()
        command = canvas._push_command.call_args.args[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(item) for item in command.commands], [AddAtomsCommand, AddBondCommand, AddSceneItemsCommand])

        atom_command = command.commands[0]
        self.assertEqual(atom_command.atom_states, {1: {"atom_id": 1, "kind": "atom"}, 2: {"atom_id": 2, "kind": "atom"}})
        self.assertEqual(atom_command.before_next_atom_id, 1)
        self.assertEqual(atom_command.after_next_atom_id, 3)
        self.assertEqual(atom_command.before_smiles_input, "before-smiles")
        self.assertEqual(atom_command.after_smiles_input, "after-smiles")

        bond_command = command.commands[1]
        self.assertEqual(bond_command.bond_id, 1)
        self.assertEqual(bond_command.bond_state, {"bond": "new-bond"})
        self.assertEqual(bond_command.previous_bond_count, 1)
        self.assertEqual(bond_command.before_smiles_input, "before-smiles")
        self.assertEqual(bond_command.after_smiles_input, "after-smiles")

        scene_item_command = command.commands[2]
        self.assertEqual(scene_item_command.item_states, [{"item": "arrow"}])
        self.assertEqual(scene_item_command.items, [scene_item])

    def test_record_additions_pushes_single_scene_item_command_when_only_scene_items_are_added(self) -> None:
        scene_item = SimpleNamespace(name="label")
        canvas = _make_canvas()

        CanvasHistoryRecordingService(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before-smiles",
            added_scene_items=[scene_item],
        )

        canvas._push_command.assert_called_once()
        command = canvas._push_command.call_args.args[0]
        self.assertIsInstance(command, AddSceneItemsCommand)
        self.assertEqual(command.item_states, [{"item": "label"}])
        self.assertEqual(command.items, [scene_item])

    def test_record_additions_skips_push_when_nothing_was_added(self) -> None:
        canvas = _make_canvas()

        CanvasHistoryRecordingService(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before-smiles",
            added_scene_items=None,
        )

        canvas._push_command.assert_not_called()

    def test_record_bond_update_pushes_update_command_when_state_changes(self) -> None:
        canvas = _make_canvas(history_enabled=True)

        CanvasHistoryRecordingService(canvas).record_bond_update(
            bond_id=4,
            before_state={"order": 1},
            after_state={"order": 2},
            before_smiles_input="before-smiles",
            after_smiles_input="after-smiles",
        )

        canvas._push_command.assert_called_once()
        command = canvas._push_command.call_args.args[0]
        self.assertIsInstance(command, UpdateBondCommand)
        self.assertEqual(command.bond_id, 4)
        self.assertEqual(command.before_state, {"order": 1})
        self.assertEqual(command.after_state, {"order": 2})
        self.assertEqual(command.before_smiles_input, "before-smiles")
        self.assertEqual(command.after_smiles_input, "after-smiles")

    def test_record_bond_update_skips_push_when_history_disabled_or_state_is_unchanged(self) -> None:
        disabled_canvas = _make_canvas(history_enabled=False)
        CanvasHistoryRecordingService(disabled_canvas).record_bond_update(
            bond_id=1,
            before_state={"order": 1},
            after_state={"order": 2},
            before_smiles_input="before-smiles",
            after_smiles_input="after-smiles",
        )
        disabled_canvas._push_command.assert_not_called()

        unchanged_canvas = _make_canvas(history_enabled=True)
        CanvasHistoryRecordingService(unchanged_canvas).record_bond_update(
            bond_id=1,
            before_state={"order": 1},
            after_state={"order": 1},
            before_smiles_input="same-smiles",
            after_smiles_input="same-smiles",
        )
        unchanged_canvas._push_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
