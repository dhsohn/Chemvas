import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from core.history import (  # noqa: E402
    CompositeCommand,
    HistoryCommand,
    SetSmilesInputCommand,
)
from ui.delete_tool_logic import (  # noqa: E402
    build_delete_tool_history_command,
    erase_delete_tool_item,
)
from ui.history_commands import DeleteSceneItemsCommand  # noqa: E402


class _Command(HistoryCommand):
    def __init__(self, name: str) -> None:
        self.name = name

    def undo(self, canvas) -> None:
        return None

    def redo(self, canvas) -> None:
        return None


class _Item:
    def __init__(self, kind=None, item_id=None, state=None) -> None:
        self._data = {0: kind, 1: item_id}
        if state is not None:
            self._data[9] = state

    def data(self, key):
        return self._data.get(key)


class _Canvas:
    def __init__(self) -> None:
        self.deleted_atoms = []
        self.deleted_bonds = []
        self.deleted_rings = []
        self.removed_items = []
        self.services = SimpleNamespace(
            scene_delete_controller=SimpleNamespace(
                delete_atom=self.delete_atom,
                delete_bond=self.delete_bond,
                delete_ring=self.delete_ring,
            ),
            scene_item_controller=SimpleNamespace(remove_scene_item=self.remove_scene_item),
        )

    def delete_atom(self, atom_id: int, record: bool = True):
        self.deleted_atoms.append((atom_id, record))
        return f"atom-{atom_id}"

    def delete_bond(self, bond_id: int, record: bool = True):
        self.deleted_bonds.append((bond_id, record))
        return f"bond-{bond_id}"

    def delete_ring(self, item, record: bool = True):
        self.deleted_rings.append((item, record))
        return "ring"

    def remove_scene_item(self, item) -> None:
        self.removed_items.append(item)


class _SceneItemController:
    def __init__(self, canvas: _Canvas) -> None:
        self.canvas = canvas
        self.calls = []

    def remove_scene_item(self, item) -> None:
        self.calls.append(item)
        self.canvas.removed_items.append(("controller", item))


class DeleteToolLogicTest(unittest.TestCase):
    def test_erase_delete_tool_item_dispatches_atom_bond_ring_and_scene_items(self) -> None:
        canvas = _Canvas()

        changed, command = erase_delete_tool_item(canvas, _Item("atom", 3))
        self.assertTrue(changed)
        self.assertEqual(command, "atom-3")
        self.assertEqual(canvas.deleted_atoms, [(3, False)])

        changed, command = erase_delete_tool_item(canvas, _Item("bond", 7))
        self.assertTrue(changed)
        self.assertEqual(command, "bond-7")
        self.assertEqual(canvas.deleted_bonds, [(7, False)])

        ring_item = _Item("ring", 1)
        changed, command = erase_delete_tool_item(canvas, ring_item)
        self.assertTrue(changed)
        self.assertEqual(command, "ring")
        self.assertEqual(canvas.deleted_rings, [(ring_item, False)])

        note_item = _Item("note", 9, state={"kind": "note", "id": 9})
        changed, command = erase_delete_tool_item(canvas, note_item)
        self.assertTrue(changed)
        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(command.item_states, [{"kind": "note", "id": 9}])
        self.assertEqual(command.items, [note_item])
        self.assertEqual(canvas.removed_items, [note_item])

        weird_item = _Item("weird", 11, state={"kind": "weird", "id": 11})
        changed, command = erase_delete_tool_item(canvas, weird_item)
        self.assertTrue(changed)
        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(command.item_states, [{"kind": "weird", "id": 11}])
        self.assertEqual(canvas.removed_items[-1], weird_item)

    def test_erase_delete_tool_item_rejects_non_integer_atom_and_bond_ids(self) -> None:
        canvas = _Canvas()

        self.assertEqual(erase_delete_tool_item(canvas, _Item("atom", "bad")), (False, None))
        self.assertEqual(erase_delete_tool_item(canvas, _Item("bond", None)), (False, None))
        self.assertEqual(canvas.deleted_atoms, [])
        self.assertEqual(canvas.deleted_bonds, [])

    def test_erase_delete_tool_item_prefers_scene_item_controller_when_available(self) -> None:
        canvas = _Canvas()
        canvas.services.scene_item_controller = _SceneItemController(canvas)
        note_item = _Item("note", 9, state={"kind": "note", "id": 9})

        changed, command = erase_delete_tool_item(canvas, note_item)

        self.assertTrue(changed)
        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(canvas.services.scene_item_controller.calls, [note_item])
        self.assertEqual(canvas.removed_items, [("controller", note_item)])

    def test_build_delete_tool_history_command_wraps_single_command_and_multiple(self) -> None:
        single = _Command("single")
        single_command = build_delete_tool_history_command(
            [single],
            before_smiles_input="before",
            after_smiles_input="after",
        )
        self.assertIsInstance(single_command, CompositeCommand)
        self.assertEqual(len(single_command.commands), 2)
        self.assertIsInstance(single_command.commands[0], SetSmilesInputCommand)
        self.assertEqual(single_command.commands[0].before_value, "before")
        self.assertEqual(single_command.commands[0].after_value, "after")
        self.assertIs(single_command.commands[1], single)

        first = _Command("first")
        second = _Command("second")
        command = build_delete_tool_history_command(
            [first, second],
            before_smiles_input="before",
            after_smiles_input="after",
        )

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(len(command.commands), 3)
        self.assertIsInstance(command.commands[0], SetSmilesInputCommand)
        self.assertEqual(command.commands[0].before_value, "before")
        self.assertEqual(command.commands[0].after_value, "after")
        self.assertIs(command.commands[1], first)
        self.assertIs(command.commands[2], second)

    def test_build_delete_tool_history_command_returns_none_for_empty_input(self) -> None:
        self.assertIsNone(
            build_delete_tool_history_command(
                [],
                before_smiles_input="before",
                after_smiles_input="after",
            )
        )


if __name__ == "__main__":
    unittest.main()
