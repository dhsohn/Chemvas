import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    UpdateAtomColorCommand,
    UpdateBondCommand,
)
from PyQt6.QtWidgets import QApplication
from ui.bond_graphics_access import add_bond_graphics_for
from ui.canvas_atom_graphics_state import atom_items_for
from ui.canvas_bond_graphics_state import bond_items_for, bond_items_for_id
from ui.canvas_view import CanvasView
from ui.graphics_items import AtomLabelItem
from ui.history_commands import UpdateSceneItemCommand
from ui.structure_mutation_access import add_atom_for, add_bond_for


class CoreHistoryUiAtomicityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _canvas(self) -> CanvasView:
        canvas = CanvasView()

        def close_canvas(target=canvas) -> None:
            target.services.canvas_scene_reset_service.clear_scene()
            target.close()

        self.addCleanup(close_canvas)
        return canvas

    @staticmethod
    def _atom_state(canvas: CanvasView, atom_id: int) -> dict:
        atom = canvas.model.atoms[atom_id]
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
        }

    @staticmethod
    def _bond_state(canvas: CanvasView, bond_id: int) -> dict:
        bond = canvas.model.bonds[bond_id]
        assert bond is not None
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def test_add_and_delete_atoms_restore_exact_graphics_after_lifecycle_failure(self) -> None:
        for command_kind in ("add", "delete"):
            with self.subTest(command=command_kind):
                canvas = self._canvas()
                atom_id = add_atom_for(canvas, "N", 3.0, 7.0)
                original_item = atom_items_for(canvas)[atom_id]
                original_item.setSelected(True)
                registry = atom_items_for(canvas)
                history_state = canvas.services.history_service.state
                reference_command = UpdateSceneItemCommand(
                    item=original_item,
                    before_state={"opacity": 1.0},
                    after_state={"opacity": 0.5},
                )
                history_state.history.append(reference_command)
                history_list = history_state.history
                state = self._atom_state(canvas, atom_id)
                command = (
                    AddAtomsCommand(
                        atom_states={atom_id: state},
                        before_next_atom_id=atom_id,
                        after_next_atom_id=canvas.model.next_atom_id,
                    )
                    if command_kind == "add"
                    else DeleteAtomsCommand(
                        atom_states={atom_id: state},
                        before_next_atom_id=canvas.model.next_atom_id,
                        after_next_atom_id=canvas.model.next_atom_id,
                    )
                )

                # CanvasAtomMutationService pops the registry entry before this
                # scene removal. The old inverse compensation created a second
                # label and orphaned the selected original item.
                with mock.patch(
                    "ui.canvas_atom_mutation_service.remove_item_from_canvas_scene",
                    side_effect=RuntimeError("scene removal failed"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "scene removal failed"):
                        if command_kind == "add":
                            command.undo(canvas)
                        else:
                            command.redo(canvas)

                matching_items = [
                    item
                    for item in canvas.scene().items()
                    if item.data(0) == "atom" and item.data(1) == atom_id
                ]
                self.assertIs(atom_items_for(canvas), registry)
                self.assertIs(atom_items_for(canvas)[atom_id], original_item)
                self.assertEqual(matching_items, [original_item])
                self.assertTrue(original_item.isSelected())
                self.assertIn(atom_id, canvas.model.atoms)
                self.assertIs(history_state.history, history_list)
                self.assertEqual(history_state.history, [reference_command])
                self.assertIs(reference_command.item, original_item)

    def test_add_and_delete_bonds_restore_exact_graphics_after_registry_pop_failure(self) -> None:
        for command_kind in ("add", "delete"):
            with self.subTest(command=command_kind):
                canvas = self._canvas()
                atom_a = add_atom_for(canvas, "C", 0.0, 0.0)
                atom_b = add_atom_for(canvas, "C", 20.0, 0.0)
                bond_id = add_bond_for(canvas, atom_a, atom_b)
                add_bond_graphics_for(canvas, bond_id)
                registry = bond_items_for(canvas)
                original_items = bond_items_for_id(canvas, bond_id)
                original_item = original_items[0]
                original_item.setSelected(True)
                original_bond = canvas.model.bonds[bond_id]
                history_state = canvas.services.history_service.state
                reference_command = UpdateSceneItemCommand(
                    item=original_item,
                    before_state={"opacity": 1.0},
                    after_state={"opacity": 0.5},
                )
                history_state.history.append(reference_command)
                history_list = history_state.history
                state = self._bond_state(canvas, bond_id)
                command = (
                    AddBondCommand(
                        bond_id=bond_id,
                        bond_state=state,
                        previous_bond_count=bond_id,
                        before_smiles_input=None,
                        after_smiles_input=None,
                    )
                    if command_kind == "add"
                    else DeleteBondCommand(
                        bond_id=bond_id,
                        bond_state=state,
                        before_smiles_input=None,
                        after_smiles_input=None,
                    )
                )

                from ui import canvas_bond_mutation_service as mutation_module

                original_pop = mutation_module.pop_bond_items_for
                armed = True

                def pop_then_fail(
                    target_canvas,
                    target_bond_id,
                    *,
                    _pop=original_pop,
                ):
                    nonlocal armed
                    result = _pop(target_canvas, target_bond_id)
                    if armed:
                        armed = False
                        raise RuntimeError("registry pop failed")
                    return result

                with mock.patch(
                    "ui.canvas_bond_mutation_service.pop_bond_items_for",
                    side_effect=pop_then_fail,
                ):
                    with self.assertRaisesRegex(RuntimeError, "registry pop failed"):
                        if command_kind == "add":
                            command.undo(canvas)
                        else:
                            command.redo(canvas)

                self.assertIs(bond_items_for(canvas), registry)
                self.assertIs(bond_items_for_id(canvas, bond_id), original_items)
                self.assertEqual(bond_items_for_id(canvas, bond_id), [original_item])
                self.assertIs(original_item.scene(), canvas.scene())
                self.assertTrue(original_item.isSelected())
                self.assertIs(canvas.model.bonds[bond_id], original_bond)
                self.assertIs(history_state.history, history_list)
                self.assertEqual(history_state.history, [reference_command])
                self.assertIs(reference_command.item, original_item)

    def test_update_bond_restores_original_model_and_graphics_identity_after_add_failure(self) -> None:
        canvas = self._canvas()
        atom_a = add_atom_for(canvas, "C", 0.0, 0.0)
        atom_b = add_atom_for(canvas, "C", 20.0, 0.0)
        bond_id = add_bond_for(canvas, atom_a, atom_b)
        add_bond_graphics_for(canvas, bond_id)
        registry = bond_items_for(canvas)
        original_items = bond_items_for_id(canvas, bond_id)
        original_item = original_items[0]
        original_item.setSelected(True)
        original_bond = canvas.model.bonds[bond_id]
        before_state = self._bond_state(canvas, bond_id)
        after_state = {**before_state, "order": 2, "style": "double"}
        command = UpdateBondCommand(
            bond_id=bond_id,
            before_state=before_state,
            after_state=after_state,
            before_smiles_input=None,
            after_smiles_input=None,
        )
        history_state = canvas.services.history_service.state
        reference_command = UpdateSceneItemCommand(
            item=original_item,
            before_state={"opacity": 1.0},
            after_state={"opacity": 0.5},
        )
        history_state.history.append(reference_command)
        history_list = history_state.history

        from ui import canvas_bond_mutation_service as mutation_module

        original_add = mutation_module.add_bond_graphics_for

        def add_then_fail(target_canvas, target_bond_id) -> None:
            original_add(target_canvas, target_bond_id)
            raise RuntimeError("bond graphics add failed")

        with mock.patch(
            "ui.canvas_bond_mutation_service.add_bond_graphics_for",
            side_effect=add_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "bond graphics add failed"):
                command.redo(canvas)

        self.assertIs(canvas.model.bonds[bond_id], original_bond)
        self.assertIs(bond_items_for(canvas), registry)
        self.assertIs(bond_items_for_id(canvas, bond_id), original_items)
        self.assertEqual(bond_items_for_id(canvas, bond_id), [original_item])
        self.assertIs(original_item.scene(), canvas.scene())
        self.assertTrue(original_item.isSelected())
        self.assertIs(history_state.history, history_list)
        self.assertEqual(history_state.history, [reference_command])
        self.assertIs(reference_command.item, original_item)

    def test_update_atom_color_compensates_mutate_then_raise_label_setter(self) -> None:
        canvas = self._canvas()
        atom_id = add_atom_for(canvas, "N", 0.0, 0.0)
        label = atom_items_for(canvas)[atom_id]
        before_model_color = canvas.model.atoms[atom_id].color
        before_label_color = label.defaultTextColor()
        command = UpdateAtomColorCommand(
            atom_id=atom_id,
            before_color=before_model_color,
            after_color="#ff0000",
        )
        original_set_color = AtomLabelItem.setDefaultTextColor
        calls = 0

        def fail_once_after_mutation(item, color) -> None:
            nonlocal calls
            original_set_color(item, color)
            calls += 1
            if calls == 1:
                raise RuntimeError("label color failed after mutation")

        with mock.patch.object(
            AtomLabelItem,
            "setDefaultTextColor",
            new=fail_once_after_mutation,
        ):
            with self.assertRaisesRegex(RuntimeError, "failed after mutation"):
                command.redo(canvas)

        self.assertEqual(canvas.model.atoms[atom_id].color, before_model_color)
        self.assertEqual(label.defaultTextColor(), before_label_color)


if __name__ == "__main__":
    unittest.main()
