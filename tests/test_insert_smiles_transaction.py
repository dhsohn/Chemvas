import unittest

from core.history import AddAtomsCommand, AddBondCommand, CompositeCommand
from core.model import Atom, Bond, MoleculeModel
from ui.history_commands import DeleteSceneItemsCommand
from ui.insert_smiles_transaction import SmilesLoadTransactionBuilder


class _FakeItem:
    def __init__(self, kind: str, atom_id=None) -> None:
        self.kind = kind
        self._payload = {}
        if atom_id is not None:
            self._payload["atom_id"] = atom_id

    def data(self, role: int):
        if role != 1:
            return None
        return dict(self._payload)


class _FakeCanvas:
    def __init__(self) -> None:
        self.last_smiles_input = "before"
        self.model = MoleculeModel()
        self._marks_by_atom = {}
        self.ring_items = []
        self.note_items = []
        self.arrow_items = []
        self.ts_bracket_items = []
        self.orbital_items = []
        self.mark_items = []

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
        }

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def _mark_state_dict(self, mark) -> dict:
        return {"kind": getattr(mark, "kind", "mark")}

    def scene_item_state(self, item) -> dict:
        return {"kind": item.kind}


class SmilesLoadTransactionBuilderTest(unittest.TestCase):
    def test_capture_collects_bound_mark_states_and_free_scene_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 1.0, 2.0),
                2: Atom("O", 3.0, 4.0),
            },
            bonds=[Bond(1, 2, 2)],
        )
        bound_mark = _FakeItem("bound-mark", atom_id=1)
        stale_mark = _FakeItem("stale-mark", atom_id=999)
        free_mark = _FakeItem("free-mark")
        ring = _FakeItem("ring")
        note = _FakeItem("note")
        arrow = _FakeItem("arrow")
        ts_bracket = _FakeItem("ts")
        orbital = _FakeItem("orbital")
        canvas._marks_by_atom = {1: [bound_mark]}
        canvas.mark_items = [bound_mark, stale_mark, free_mark]
        canvas.ring_items = [ring]
        canvas.note_items = [note]
        canvas.arrow_items = [arrow]
        canvas.ts_bracket_items = [ts_bracket]
        canvas.orbital_items = [orbital]
        builder = SmilesLoadTransactionBuilder(canvas)

        snapshot = builder.capture()

        self.assertEqual(set(snapshot.atom_states), {1, 2})
        self.assertEqual(snapshot.bond_states[0]["order"], 2)
        self.assertEqual(snapshot.mark_states_for_atoms, [{"kind": "bound-mark"}])
        self.assertEqual(
            [item.kind for item in snapshot.scene_items],
            ["ring", "stale-mark", "free-mark", "note", "arrow", "ts", "orbital"],
        )
        self.assertEqual(
            snapshot.scene_item_states,
            [
                {"kind": "ring"},
                {"kind": "stale-mark"},
                {"kind": "free-mark"},
                {"kind": "note"},
                {"kind": "arrow"},
                {"kind": "ts"},
                {"kind": "orbital"},
            ],
        )

    def test_build_command_returns_none_when_nothing_changed(self) -> None:
        canvas = _FakeCanvas()
        builder = SmilesLoadTransactionBuilder(canvas)

        snapshot = builder.capture()
        command = builder.build_command(
            snapshot,
            after_clear_next_atom_id=0,
            after_smiles_input="C",
        )

        self.assertIsNone(command)

    def test_build_command_returns_single_add_atoms_command_for_new_atoms_only(self) -> None:
        canvas = _FakeCanvas()
        builder = SmilesLoadTransactionBuilder(canvas)
        snapshot = builder.capture()
        canvas.model = MoleculeModel(atoms={0: Atom("N", 5.0, 6.0)})

        command = builder.build_command(
            snapshot,
            after_clear_next_atom_id=0,
            after_smiles_input="N",
        )

        self.assertIsInstance(command, AddAtomsCommand)
        self.assertEqual(command.before_smiles_input, "before")
        self.assertEqual(command.after_smiles_input, "N")
        self.assertEqual(command.before_next_atom_id, 0)
        self.assertEqual(command.after_next_atom_id, 1)
        self.assertEqual(command.atom_states[0]["element"], "N")

    def test_build_command_returns_composite_for_full_replacement(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={0: Atom("C", 1.0, 2.0)},
            bonds=[Bond(0, 0, 1)],
        )
        ring = _FakeItem("ring")
        canvas.ring_items = [ring]
        builder = SmilesLoadTransactionBuilder(canvas)
        snapshot = builder.capture()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 10.0, 20.0),
                1: Atom("O", 30.0, 40.0),
            },
            bonds=[Bond(0, 1, 2)],
        )

        command = builder.build_command(
            snapshot,
            after_clear_next_atom_id=0,
            after_smiles_input="CO",
        )

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(
            [type(child).__name__ for child in command.commands],
            [
                "DeleteBondCommand",
                "DeleteAtomsCommand",
                "DeleteSceneItemsCommand",
                "AddAtomsCommand",
                "AddBondCommand",
            ],
        )
        delete_scene_items = [child for child in command.commands if isinstance(child, DeleteSceneItemsCommand)]
        self.assertEqual(len(delete_scene_items), 1)
        self.assertEqual(delete_scene_items[0].item_states, [{"kind": "ring"}])

    def test_build_command_skips_sparse_new_bonds(self) -> None:
        canvas = _FakeCanvas()
        builder = SmilesLoadTransactionBuilder(canvas)
        snapshot = builder.capture()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 1.0, 2.0),
                1: Atom("O", 3.0, 4.0),
            },
            bonds=[None, Bond(0, 1, 2)],
        )

        command = builder.build_command(
            snapshot,
            after_clear_next_atom_id=0,
            after_smiles_input="CO",
        )

        self.assertIsInstance(command, CompositeCommand)
        assert command is not None
        add_bond_commands = [child for child in command.commands if isinstance(child, AddBondCommand)]
        self.assertEqual(len(add_bond_commands), 1)
        self.assertEqual(add_bond_commands[0].bond_id, 1)
        self.assertEqual(add_bond_commands[0].bond_state["order"], 2)


if __name__ == "__main__":
    unittest.main()
