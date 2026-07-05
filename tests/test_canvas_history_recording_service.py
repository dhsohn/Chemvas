import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    UpdateBondCommand,
)
from core.model import Atom, Bond
from ui.atom_coords_access import set_atom_coords_3d_for
from ui.canvas_history_recording_service import CanvasHistoryRecordingService
from ui.canvas_history_state import CanvasHistoryState
from ui.canvas_smiles_input_state import CanvasSmilesInputState
from ui.history_commands import AddSceneItemsCommand


class _SceneItem:
    def __init__(self, kind: str, state: dict) -> None:
        self._data = {0: kind, 9: dict(state)}

    def data(self, key: int):
        return self._data.get(key)


def _make_canvas(
    *,
    atoms=None,
    bonds=None,
    next_atom_id=0,
    last_smiles_input="after-smiles",
    history_enabled=True,
):
    push_command = mock.Mock()
    history_service = SimpleNamespace(
        push=push_command,
        is_enabled=mock.Mock(return_value=history_enabled),
    )
    return SimpleNamespace(
        push_command=push_command,
        services=SimpleNamespace(history_service=history_service),
        _atom_state_dict=mock.Mock(side_effect=lambda atom_id: {"atom_id": atom_id, "kind": "atom"}),
        _bond_state_dict=mock.Mock(side_effect=lambda bond: {"bond": getattr(bond, "name", "bond")}),
        model=SimpleNamespace(
            atoms=dict(atoms or {}),
            bonds=list(bonds or []),
            next_atom_id=next_atom_id,
        ),
        smiles_input_state=CanvasSmilesInputState(last_smiles_input=last_smiles_input),
        history_state=CanvasHistoryState(enabled=history_enabled),
    )


def _recording_service(canvas) -> CanvasHistoryRecordingService:
    return CanvasHistoryRecordingService(
        canvas,
        history_service=canvas.services.history_service,
    )


class CanvasHistoryRecordingServiceTest(unittest.TestCase):
    def test_record_additions_pushes_composite_command_for_atom_bond_and_scene_items(self) -> None:
        existing_bond = Bond(0, 1)
        new_bond = Bond(1, 2, 2, style="double_center", color="#336699")
        scene_item = _SceneItem("arrow", {"item": "arrow"})
        canvas = _make_canvas(
            atoms={1: Atom("C", 1.0, 2.0), 2: Atom("O", 3.0, 4.0, color="#112233")},
            bonds=[existing_bond, new_bond],
            next_atom_id=3,
        )

        _recording_service(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=1,
            before_smiles_input="before-smiles",
            added_scene_items=[scene_item],
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(item) for item in command.commands], [AddAtomsCommand, AddBondCommand, AddSceneItemsCommand])

        atom_command = command.commands[0]
        self.assertEqual(
            atom_command.atom_states,
            {
                1: {"element": "C", "x": 1.0, "y": 2.0, "color": "#000000", "explicit_label": False},
                2: {"element": "O", "x": 3.0, "y": 4.0, "color": "#112233", "explicit_label": False},
            },
        )
        self.assertEqual(atom_command.before_next_atom_id, 1)
        self.assertEqual(atom_command.after_next_atom_id, 3)
        self.assertEqual(atom_command.before_smiles_input, "before-smiles")
        self.assertEqual(atom_command.after_smiles_input, "after-smiles")

        bond_command = command.commands[1]
        self.assertEqual(bond_command.bond_id, 1)
        self.assertEqual(
            bond_command.bond_state,
            {"a": 1, "b": 2, "order": 2, "style": "double_center", "color": "#336699"},
        )
        self.assertEqual(bond_command.previous_bond_count, 1)
        self.assertEqual(bond_command.before_smiles_input, "before-smiles")
        self.assertEqual(bond_command.after_smiles_input, "after-smiles")

        scene_item_command = command.commands[2]
        self.assertEqual(scene_item_command.item_states, [{"item": "arrow"}])
        self.assertEqual(scene_item_command.items, [scene_item])

    def test_record_additions_includes_atom_annotations_in_atom_states(self) -> None:
        canvas = _make_canvas(
            atoms={1: Atom("N", 1.0, 2.0)},
            next_atom_id=2,
        )
        canvas.model.atom_annotations = {1: {"formal_charge": 1}}

        _recording_service(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=0,
            before_smiles_input="before-smiles",
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, AddAtomsCommand)
        self.assertEqual(command.atom_states[1]["annotation"], {"formal_charge": 1})

    def test_record_additions_includes_atom_coords_3d_in_add_atoms_command(self) -> None:
        canvas = _make_canvas(
            atoms={1: Atom("N", 1.0, 2.0), 2: Atom("C", 3.0, 4.0)},
            next_atom_id=3,
        )
        set_atom_coords_3d_for(canvas, {1: (1.0, 2.0, 3.0), 99: (9.0, 9.0, 9.0)})

        _recording_service(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=0,
            before_smiles_input="before-smiles",
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, AddAtomsCommand)
        self.assertEqual(command.atom_coords_3d, {1: (1.0, 2.0, 3.0)})

    def test_record_additions_pushes_single_scene_item_command_when_only_scene_items_are_added(self) -> None:
        scene_item = _SceneItem("label", {"item": "label"})
        canvas = _make_canvas()

        _recording_service(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before-smiles",
            added_scene_items=[scene_item],
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, AddSceneItemsCommand)
        self.assertEqual(command.item_states, [{"item": "label"}])
        self.assertEqual(command.items, [scene_item])

    def test_record_additions_skips_push_when_nothing_was_added(self) -> None:
        canvas = _make_canvas()

        _recording_service(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before-smiles",
            added_scene_items=None,
        )

        canvas.push_command.assert_not_called()

    def test_record_additions_skips_none_new_bonds(self) -> None:
        canvas = _make_canvas(
            bonds=[SimpleNamespace(name="existing-bond"), None],
            next_atom_id=0,
        )

        _recording_service(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=1,
            before_smiles_input="before-smiles",
            added_scene_items=None,
        )

        canvas.push_command.assert_not_called()

    def test_record_additions_skips_empty_sparse_atom_range_and_none_only_scene_items(self) -> None:
        canvas = _make_canvas(
            atoms={0: object()},
            bonds=[],
            next_atom_id=3,
        )

        _recording_service(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=0,
            before_smiles_input="before-smiles",
            added_scene_items=[None],
        )

        canvas.push_command.assert_not_called()

    def test_record_bond_update_pushes_update_command_when_state_changes(self) -> None:
        canvas = _make_canvas(history_enabled=True)

        _recording_service(canvas).record_bond_update(
            bond_id=4,
            before_state={"order": 1},
            after_state={"order": 2},
            before_smiles_input="before-smiles",
            after_smiles_input="after-smiles",
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, UpdateBondCommand)
        self.assertEqual(command.bond_id, 4)
        self.assertEqual(command.before_state, {"order": 1})
        self.assertEqual(command.after_state, {"order": 2})
        self.assertEqual(command.before_smiles_input, "before-smiles")
        self.assertEqual(command.after_smiles_input, "after-smiles")

    def test_record_bond_update_skips_push_when_history_disabled_or_state_is_unchanged(self) -> None:
        disabled_canvas = _make_canvas(history_enabled=False)
        _recording_service(disabled_canvas).record_bond_update(
            bond_id=1,
            before_state={"order": 1},
            after_state={"order": 2},
            before_smiles_input="before-smiles",
            after_smiles_input="after-smiles",
        )
        disabled_canvas.push_command.assert_not_called()

        unchanged_canvas = _make_canvas(history_enabled=True)
        _recording_service(unchanged_canvas).record_bond_update(
            bond_id=1,
            before_state={"order": 1},
            after_state={"order": 1},
            before_smiles_input="same-smiles",
            after_smiles_input="same-smiles",
        )
        unchanged_canvas.push_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
