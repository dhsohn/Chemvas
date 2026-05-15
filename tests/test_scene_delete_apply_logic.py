import inspect
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import DeleteAtomsCommand, DeleteBondCommand
    from ui.history_commands import DeleteSceneItemsCommand
    from core.model import Atom, Bond, MoleculeModel
    from ui.scene_delete_logic import DeleteSelectionPlan
    from tests.test_scene_ops_controller import _make_note_item, _make_rect_item


def _load_delete_apply_helper():
    module_names = (
        "ui.scene_delete_apply_logic",
        "ui.scene_delete_logic",
    )
    helper_names = (
        "build_delete_apply_commands",
        "apply_delete_selection_plan",
        "build_delete_selection_commands",
        "apply_delete_commands",
    )
    for module_name in module_names:
        try:
            module = __import__(module_name, fromlist=["*"])
        except ModuleNotFoundError:
            continue
        for helper_name in helper_names:
            helper = getattr(module, helper_name, None)
            if callable(helper):
                return helper
    return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene delete apply logic tests")
class SceneDeleteApplyLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.helper = _load_delete_apply_helper()
        if cls.helper is None:
            raise unittest.SkipTest("delete apply helper is not available yet")

    def _invoke_helper(self, canvas, plan):
        helper = self.__class__.helper
        alias_values = {
            "canvas": canvas,
            "scene": canvas,
            "plan": plan,
            "selection_plan": plan,
            "delete_plan": plan,
            "delete_selection_plan": plan,
            "before_smiles_input": canvas.last_smiles_input,
            "current_smiles_input_getter": lambda: canvas.last_smiles_input,
            "next_atom_id_getter": lambda: canvas.model.next_atom_id,
            "clear_smiles_input": plan.clear_smiles_input,
            "clear_handles": canvas.clear_handles,
            "clear_handles_enabled": plan.clear_handles,
            "bond_ids_to_remove": plan.bond_ids_to_remove,
            "atom_ids": plan.atom_ids,
            "mark_states_for_atoms": plan.mark_states_for_atoms,
            "mark_states": plan.mark_states_for_atoms,
            "scene_items": plan.scene_items,
            "atom_states": {atom_id: canvas._atom_state_dict(atom_id) for atom_id in plan.atom_ids},
            "scene_item_states": [canvas.scene_item_state(item) for item in plan.scene_items],
            "bonds": canvas.model.bonds,
            "atoms": canvas.model.atoms,
            "next_atom_id": canvas.model.next_atom_id,
            "remove_bond_by_id": canvas._remove_bond_by_id,
            "bond_state_getter": canvas._bond_state_dict,
            "redraw_connected_bonds": canvas._redraw_connected_bonds,
            "remove_atom_only": canvas._remove_atom_only,
            "atom_state_getter": canvas._atom_state_dict,
            "remove_scene_item": canvas.remove_scene_item,
            "scene_item_state_getter": canvas.scene_item_state,
            "clear_handles_fn": canvas.clear_handles,
            "clear_handles_callback": canvas.clear_handles,
            "clear_handles_func": canvas.clear_handles,
        }
        signature = inspect.signature(helper)
        kwargs = {
            name: alias_values[name]
            for name in signature.parameters
            if name in alias_values
        }
        try:
            return helper(**kwargs)
        except TypeError:
            for args in ((canvas, plan), (plan, canvas), (canvas,), (plan,)):
                try:
                    return helper(*args)
                except TypeError:
                    continue
            raise

    def test_delete_apply_helper_returns_empty_command_list_when_plan_has_no_work(self) -> None:
        canvas = _FakeDeleteCanvas()
        plan = DeleteSelectionPlan()

        commands = self._invoke_helper(canvas, plan)

        self.assertEqual(commands, [])
        self.assertEqual(canvas.remove_bond_calls, [])
        self.assertEqual(canvas.remove_atom_calls, [])
        self.assertEqual(canvas.removed_scene_items, [])
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(canvas.last_smiles_input, "C")

    def test_delete_apply_helper_removes_only_valid_bonds_in_reverse_order(self) -> None:
        canvas = _FakeDeleteCanvas()
        plan = DeleteSelectionPlan(
            bond_ids_to_remove=[3, 1, 0, 2, 9],
            clear_smiles_input=True,
        )

        commands = self._invoke_helper(canvas, plan)

        self.assertEqual([type(command) for command in commands], [DeleteBondCommand, DeleteBondCommand, DeleteBondCommand])
        self.assertEqual([command.bond_id for command in commands], [3, 1, 0])
        self.assertEqual(canvas.remove_bond_calls, [3, 1, 0])
        self.assertEqual(canvas.redraw_connected_bonds_calls, [3, 1, 2, 3, 1, 2])
        self.assertEqual(canvas.remove_atom_calls, [])
        self.assertEqual(canvas.last_smiles_input, None)

    def test_delete_apply_helper_builds_delete_atoms_command_with_mark_snapshot(self) -> None:
        canvas = _FakeDeleteCanvas()
        plan = DeleteSelectionPlan(
            atom_ids=[1, 3],
            mark_states_for_atoms=[
                {"kind": "mark", "atom_id": 1, "x": 10.0, "y": 11.0},
                {"kind": "mark", "atom_id": 3, "x": 30.0, "y": 31.0},
            ],
            clear_smiles_input=True,
        )

        commands = self._invoke_helper(canvas, plan)

        delete_atoms_commands = [command for command in commands if isinstance(command, DeleteAtomsCommand)]
        self.assertEqual(len(delete_atoms_commands), 1)
        delete_atoms = delete_atoms_commands[0]
        self.assertEqual(set(delete_atoms.atom_states), {1, 3})
        self.assertEqual(
            delete_atoms.mark_states,
            [
                {"kind": "mark", "atom_id": 1, "x": 10.0, "y": 11.0},
                {"kind": "mark", "atom_id": 3, "x": 30.0, "y": 31.0},
            ],
        )
        self.assertEqual(delete_atoms.before_next_atom_id, 7)
        self.assertEqual(delete_atoms.after_next_atom_id, 7)
        self.assertEqual(canvas.remove_atom_calls, [(1, True), (3, True)])
        self.assertEqual(canvas.last_smiles_input, None)

    def test_delete_apply_helper_collects_scene_item_states_and_clears_handles_when_needed(self) -> None:
        canvas = _FakeDeleteCanvas()
        note_item = _make_note_item("note", 12.0, 18.0)
        arrow_item = _make_rect_item("arrow", state={"kind": "arrow", "start": (1.0, 2.0), "end": (3.0, 4.0)})
        canvas.scene_items.extend([note_item, arrow_item])
        plan = DeleteSelectionPlan(
            scene_items=[note_item, arrow_item],
            clear_handles=True,
        )

        commands = self._invoke_helper(canvas, plan)

        delete_scene_commands = [command for command in commands if isinstance(command, DeleteSceneItemsCommand)]
        self.assertEqual(len(delete_scene_commands), 1)
        delete_scene = delete_scene_commands[0]
        self.assertEqual(
            delete_scene.item_states,
            [
                {"kind": "note", "text": "note", "x": 12.0, "y": 18.0},
                {"kind": "arrow", "start": (1.0, 2.0), "end": (3.0, 4.0)},
            ],
        )
        self.assertEqual(delete_scene.items, [note_item, arrow_item])
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.removed_scene_items, [note_item, arrow_item])


class _FakeDeleteCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel(
            atoms={
                1: Atom("C", 10.0, 11.0),
                2: Atom("O", 20.0, 21.0),
                3: Atom("N", 30.0, 31.0),
            },
            bonds=[
                Bond(1, 2, 1),
                Bond(2, 3, 2),
                None,
                Bond(3, 1, 3),
            ],
            next_atom_id=7,
        )
        self.model.next_atom_id = 7
        self.last_smiles_input = "C"
        self.scene_items: list[object] = []
        self.remove_bond_calls: list[int] = []
        self.redraw_connected_bonds_calls: list[int] = []
        self.remove_atom_calls: list[tuple[int, bool]] = []
        self.removed_scene_items: list[object] = []
        self.clear_handles_calls = 0

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def _remove_bond_by_id(self, bond_id: int) -> None:
        self.remove_bond_calls.append(bond_id)
        if 0 <= bond_id < len(self.model.bonds):
            self.model.bonds[bond_id] = None
        self.last_smiles_input = None

    def _redraw_connected_bonds(self, atom_id: int) -> None:
        self.redraw_connected_bonds_calls.append(atom_id)

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
        }

    def _remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        self.remove_atom_calls.append((atom_id, remove_marks))
        self.model.atoms.pop(atom_id, None)
        self.last_smiles_input = None

    def scene_item_state(self, item) -> dict:
        state = item.data(9)
        return dict(state) if isinstance(state, dict) else {}

    def remove_scene_item(self, item) -> None:
        self.removed_scene_items.append(item)
        if item in self.scene_items:
            self.scene_items.remove(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1


if __name__ == "__main__":
    unittest.main()
