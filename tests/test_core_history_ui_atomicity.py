import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    MoveAtomsCommand,
    SetAtomPositionsCommand,
    UpdateAtomColorCommand,
    UpdateBondCommand,
    UpdateBondLengthCommand,
)
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for, bond_items_for_id
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.graphics_items import AtomLabelItem
from chemvas.ui.history_commands import MoveItemsCommand, UpdateSceneItemCommand
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsTextItem,
)

from tests.canvas_factory import build_canvas_view


class CoreHistoryUiAtomicityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _canvas(self) -> CanvasView:
        canvas = build_canvas_view()

        def close_canvas(target=canvas) -> None:
            target.services.document.canvas_scene_reset_service.clear_scene()
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

    def test_add_and_delete_atoms_restore_exact_graphics_after_lifecycle_failure(
        self,
    ) -> None:
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
                    "chemvas.ui.canvas_atom_mutation_service.remove_item_from_canvas_scene",
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

    def test_add_and_delete_bonds_restore_exact_graphics_after_registry_pop_failure(
        self,
    ) -> None:
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

                from chemvas.ui import canvas_bond_mutation_service as mutation_module

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
                    "chemvas.ui.canvas_bond_mutation_service.pop_bond_items_for",
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

    def test_update_bond_restores_original_model_and_graphics_identity_after_add_failure(
        self,
    ) -> None:
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

        from chemvas.ui import canvas_bond_mutation_service as mutation_module

        original_add = mutation_module.add_bond_graphics_for

        def add_then_fail(target_canvas, target_bond_id) -> None:
            original_add(target_canvas, target_bond_id)
            raise RuntimeError("bond graphics add failed")

        with mock.patch(
            "chemvas.ui.canvas_bond_mutation_service.add_bond_graphics_for",
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

    def test_mixed_ui_and_lifecycle_composite_uses_one_snapshot_and_restores_item(
        self,
    ) -> None:
        canvas = self._canvas()
        note = QGraphicsTextItem("transactional note")
        note.setData(0, "note")
        note.setData(2, {})
        note.setPos(QPointF(3.0, 7.0))
        canvas.scene().addItem(note)
        original_position = note.pos()
        original_data = dict(note.data(2))
        command = CompositeCommand(
            [
                MoveItemsCommand([note], 11.0, 13.0),
                UpdateBondLengthCommand(20.0, 30.0),
            ]
        )

        from chemvas.ui import history_canvas_access as history_access

        original_restore_length = history_access.restore_bond_length_for_history

        def mutate_length_then_fail(target_canvas, length_px: float) -> None:
            original_restore_length(target_canvas, length_px)
            raise RuntimeError("mixed lifecycle child failed")

        with (
            mock.patch.object(
                history_access,
                "capture_history_transaction_for_history",
                wraps=history_access.capture_history_transaction_for_history,
            ) as capture,
            mock.patch.object(
                history_access,
                "restore_bond_length_for_history",
                side_effect=mutate_length_then_fail,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "mixed lifecycle child failed"):
                command.redo(canvas)

        self.assertEqual(capture.call_count, 1)
        self.assertEqual(note.pos(), original_position)
        self.assertEqual(note.data(2), original_data)

    def test_move_exact_owner_preserves_retryable_service_stacks_with_one_capture(
        self,
    ) -> None:
        from chemvas.ui import history_canvas_access as history_access
        from chemvas.ui import history_commands as history_commands_module

        for move_kind in ("atoms", "items"):
            for wrapped in (False, True):
                for direction in ("undo", "redo"):
                    with self.subTest(
                        move_kind=move_kind,
                        wrapped=wrapped,
                        direction=direction,
                    ):
                        canvas = self._canvas()
                        primary = RuntimeError(f"{move_kind} {direction} interrupted")
                        if move_kind == "atoms":
                            atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
                            leaf_command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
                            original_state = (
                                canvas.model.atoms[atom_id].x,
                                canvas.model.atoms[atom_id].y,
                            )
                            original_mutation = history_access.move_atoms_for

                            def mutate_then_fail(
                                *args,
                                _mutation=original_mutation,
                                _primary=primary,
                                **kwargs,
                            ) -> None:
                                _mutation(*args, **kwargs)
                                raise _primary

                            mutation_patch = mock.patch.object(
                                history_access,
                                "move_atoms_for",
                                side_effect=mutate_then_fail,
                            )

                            def assert_canvas_restored(
                                _canvas=canvas,
                                _atom_id=atom_id,
                                _state=original_state,
                            ) -> None:
                                self.assertEqual(
                                    (
                                        _canvas.model.atoms[_atom_id].x,
                                        _canvas.model.atoms[_atom_id].y,
                                    ),
                                    _state,
                                )
                        else:
                            item = QGraphicsTextItem("move exact owner")
                            item.setData(0, "note")
                            item.setPos(QPointF(3.0, 7.0))
                            canvas.scene().addItem(item)
                            original_state = QPointF(item.pos())
                            leaf_command = MoveItemsCommand([item], 5.0, 9.0)
                            original_mutation = history_commands_module.move_item_for

                            def mutate_then_fail(
                                *args,
                                _mutation=original_mutation,
                                _primary=primary,
                                **kwargs,
                            ) -> None:
                                _mutation(*args, **kwargs)
                                raise _primary

                            mutation_patch = mock.patch.object(
                                history_commands_module,
                                "move_item_for",
                                side_effect=mutate_then_fail,
                            )

                            def assert_canvas_restored(
                                _item=item,
                                _state=original_state,
                            ) -> None:
                                self.assertEqual(_item.pos(), _state)

                        command = (
                            CompositeCommand([leaf_command])
                            if wrapped
                            else leaf_command
                        )
                        service = canvas.services.history_service
                        state = service.state
                        history = state.history
                        redo = state.redo_stack
                        history_sentinel = object()
                        redo_sentinel = object()
                        if direction == "undo":
                            history[:] = [history_sentinel, command]
                            redo[:] = [redo_sentinel]
                        else:
                            history[:] = [history_sentinel]
                            redo[:] = [redo_sentinel, command]
                        expected_history = list(history)
                        expected_redo = list(redo)
                        with (
                            mock.patch.object(
                                history_access,
                                "capture_history_transaction_for_history",
                                wraps=(
                                    history_access.capture_history_transaction_for_history
                                ),
                            ) as capture,
                            mutation_patch,
                        ):
                            with self.assertRaises(RuntimeError) as caught:
                                getattr(service, direction)()

                        self.assertIs(caught.exception, primary)
                        self.assertEqual(capture.call_count, 1)
                        assert_canvas_restored()
                        self.assertIs(state.history, history)
                        self.assertIs(state.redo_stack, redo)
                        self.assertEqual(history, expected_history)
                        self.assertEqual(redo, expected_redo)

    def test_composite_exact_restore_covers_persistently_failing_projection_state(
        self,
    ) -> None:
        canvas = self._canvas()
        rotation = rotation_state_for(canvas)
        rotation.projection_center_3d = (1.0, 2.0, 3.0)
        rotation.projection_anchor_2d = (4.0, 5.0)
        before_center = rotation.projection_center_3d
        before_anchor = rotation.projection_anchor_2d
        before_style = canvas.renderer.style
        command = CompositeCommand(
            [
                UpdateBondLengthCommand(
                    before_style.bond_length_px,
                    before_style.bond_length_px + 10.0,
                ),
                SetAtomPositionsCommand(
                    before_positions={},
                    after_positions={},
                    restore_projection_state=True,
                    before_projection_center_3d=before_center,
                    after_projection_center_3d=(10.0, 20.0, 30.0),
                    before_projection_anchor_2d=before_anchor,
                    after_projection_anchor_2d=(40.0, 50.0),
                ),
            ]
        )

        from chemvas.ui import history_canvas_access as history_access

        calls = 0

        def corrupt_projection_then_fail(
            target_canvas,
            _projection_center_3d,
            _projection_anchor_2d,
        ) -> None:
            nonlocal calls
            calls += 1
            target_rotation = rotation_state_for(target_canvas)
            target_rotation.projection_center_3d = (900.0, 901.0, 902.0)
            target_rotation.projection_anchor_2d = (903.0, 904.0)
            raise RuntimeError("persistent projection restore failure")

        with mock.patch.object(
            history_access,
            "restore_projection_state_for_history",
            side_effect=corrupt_projection_then_fail,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "persistent projection restore failure",
            ):
                command.redo(canvas)

        # The child transaction defers to the composite owner, so the failed
        # relative compensation is deliberately skipped and one outer exact
        # restore is the final authority.
        self.assertEqual(calls, 1)
        self.assertIs(rotation_state_for(canvas), rotation)
        self.assertEqual(rotation.projection_center_3d, before_center)
        self.assertEqual(rotation.projection_anchor_2d, before_anchor)
        self.assertIs(canvas.renderer.style, before_style)

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

    def test_push_many_preserves_linear_entries_limit_and_disabled_policy(self) -> None:
        canvas = object()
        callback = mock.Mock()
        existing = mock.Mock()
        redo = mock.Mock()
        state = CanvasHistoryState(
            history=[existing],
            redo_stack=[redo],
            limit=2,
            change_callback=callback,
        )
        service = CanvasHistoryService(canvas, state)
        first = mock.Mock()
        second = mock.Mock()

        self.assertTrue(service.push_many((first, second)))
        self.assertEqual(state.history, [first, second])
        self.assertEqual(state.redo_stack, [])
        callback.assert_called_once_with()

        state.enabled = False
        self.assertFalse(service.push_many((mock.Mock(),)))
        self.assertEqual(state.history, [first, second])
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
