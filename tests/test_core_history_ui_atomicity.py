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
    HistoryCommand,
    HistoryTransactionRestoreResult,
    MoveAtomsCommand,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
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
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
)


class CoreHistoryUiAtomicityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _canvas(self) -> CanvasView:
        canvas = CanvasView()

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

    def test_bond_length_style_restore_controls_retryable_history_stacks(self) -> None:
        from chemvas.core.renderer import Renderer
        from chemvas.ui import history_canvas_access as history_access

        class _ControlledRenderer(Renderer):
            def __init__(self, style) -> None:
                self._style = style
                self.rollback_behavior = "normal"
                self.rollback_armed = False
                self.rollback_setter_calls = 0
                super().__init__(style)

            @property
            def style(self):
                return self._style

            @style.setter
            def style(self, value) -> None:
                if self.rollback_armed:
                    self.rollback_setter_calls += 1
                    if (
                        self.rollback_behavior == "fail_once"
                        and self.rollback_setter_calls == 1
                    ):
                        raise KeyboardInterrupt(
                            "transient renderer rollback setter failure"
                        )
                    if self.rollback_behavior == "no_op":
                        return
                self._style = value

            def arm_rollback(self, behavior: str) -> None:
                self.rollback_behavior = behavior
                self.rollback_armed = True
                self.rollback_setter_calls = 0

        original_restore_length = history_access.restore_bond_length_for_history
        for behavior in ("fail_once", "no_op"):
            for direction in ("undo", "redo"):
                with self.subTest(behavior=behavior, direction=direction):
                    canvas = self._canvas()
                    renderer = _ControlledRenderer(canvas.renderer.style)
                    canvas.renderer = renderer
                    before_length = renderer.style.bond_length_px
                    after_length = before_length + 10.0
                    if direction == "undo":
                        renderer.set_bond_length(after_length)
                    source_style = renderer.style
                    command = UpdateBondLengthCommand(before_length, after_length)
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
                    primary = RuntimeError(
                        f"{direction} bond-length mutation interrupted"
                    )

                    def mutate_then_fail(
                        target_canvas,
                        length_px: float,
                        *,
                        _primary=primary,
                        _behavior=behavior,
                        _renderer=renderer,
                    ) -> None:
                        original_restore_length(target_canvas, length_px)
                        _renderer.arm_rollback(_behavior)
                        raise _primary

                    with mock.patch.object(
                        history_access,
                        "restore_bond_length_for_history",
                        side_effect=mutate_then_fail,
                    ):
                        with self.assertRaises(RuntimeError) as caught:
                            getattr(service, direction)()

                    self.assertIs(caught.exception, primary)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo)
                    self.assertEqual(
                        renderer.rollback_setter_calls,
                        3 if behavior == "fail_once" else 2,
                    )
                    if behavior == "fail_once":
                        self.assertIs(renderer.style, source_style)
                        self.assertEqual(history, expected_history)
                        self.assertEqual(redo, expected_redo)

                        # The authoritative retry contract is useful only if
                        # the exact same stack entry can be attempted again.
                        renderer.rollback_armed = False
                        getattr(service, direction)()
                        self.assertIs(state.history, history)
                        self.assertIs(state.redo_stack, redo)
                        if direction == "undo":
                            self.assertEqual(history, [history_sentinel])
                            self.assertEqual(redo, [redo_sentinel, command])
                        else:
                            self.assertEqual(
                                history,
                                [history_sentinel, command],
                            )
                            self.assertEqual(redo, [redo_sentinel])
                    elif direction == "undo":
                        self.assertEqual(history, [history_sentinel])
                        self.assertEqual(redo, [])
                    else:
                        self.assertEqual(history, [history_sentinel])
                        self.assertEqual(redo, [])

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

    def test_move_atom_preflight_failures_keep_exact_retryable_service_stacks(
        self,
    ) -> None:
        from chemvas.ui import history_canvas_access as history_access

        for failure_source in ("atom_lookup", "position_descriptor", "coords"):
            for direction in ("undo", "redo"):
                with self.subTest(
                    failure_source=failure_source,
                    direction=direction,
                ):
                    canvas = self._canvas()
                    atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
                    atom = canvas.model.atoms[atom_id]
                    command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
                    if direction == "undo":
                        atom.x = 8.0
                        atom.y = 16.0
                    source_position = (atom.x, atom.y)
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
                    primary: BaseException
                    if failure_source == "atom_lookup":
                        primary = KeyboardInterrupt("atom lookup interrupted")
                        preflight_patch = mock.patch.object(
                            history_access,
                            "atom_for_id",
                            side_effect=primary,
                        )
                    elif failure_source == "position_descriptor":
                        primary = SystemExit("atom x descriptor terminated")

                        class BrokenPosition:
                            y = source_position[1]

                            def __init__(self, error: BaseException) -> None:
                                self.error = error

                            @property
                            def x(self):
                                raise self.error

                        preflight_patch = mock.patch.object(
                            history_access,
                            "atom_for_id",
                            return_value=BrokenPosition(primary),
                        )
                    else:
                        primary = KeyboardInterrupt(
                            "atom 3D coordinate lookup interrupted"
                        )
                        preflight_patch = mock.patch.object(
                            history_access,
                            "atom_coords_3d_for_id",
                            side_effect=primary,
                        )

                    with (
                        mock.patch.object(
                            history_access,
                            "_capture_history_transaction_for_command",
                            wraps=(
                                history_access._capture_history_transaction_for_command
                            ),
                        ) as capture,
                        mock.patch.object(
                            history_access,
                            "_restore_history_transaction_for_command",
                            wraps=(
                                history_access._restore_history_transaction_for_command
                            ),
                        ) as restore,
                        mock.patch.object(
                            history_access,
                            "_release_history_transaction_for_command",
                            wraps=(
                                history_access._release_history_transaction_for_command
                            ),
                        ) as release,
                        preflight_patch,
                    ):
                        with self.assertRaises(type(primary)) as caught:
                            getattr(service, direction)()

                    self.assertIs(caught.exception, primary)
                    self.assertEqual(capture.call_count, 1)
                    self.assertEqual(restore.call_count, 1)
                    self.assertEqual(release.call_count, 0)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo)
                    self.assertEqual(history, expected_history)
                    self.assertEqual(redo, expected_redo)
                    self.assertEqual((atom.x, atom.y), source_position)

                    getattr(service, direction)()
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo)
                    expected_position = (
                        (3.0, 7.0) if direction == "undo" else (8.0, 16.0)
                    )
                    self.assertEqual((atom.x, atom.y), expected_position)

    def test_exact_move_callback_cannot_replace_success_or_failure_stacks(
        self,
    ) -> None:
        from chemvas.ui import history_canvas_access as history_access

        for direction in ("undo", "redo"):
            for outcome in ("success", "system_exit"):
                with self.subTest(direction=direction, outcome=outcome):
                    canvas = self._canvas()
                    atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
                    atom = canvas.model.atoms[atom_id]
                    command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
                    if direction == "undo":
                        atom.x = 8.0
                        atom.y = 16.0
                    source_position = (atom.x, atom.y)
                    service = canvas.services.history_service
                    state = service.state
                    history = state.history
                    redo_stack = state.redo_stack
                    history_sentinel = object()
                    redo_sentinel = object()
                    history[:] = (
                        [history_sentinel, command]
                        if direction == "undo"
                        else [history_sentinel]
                    )
                    redo_stack[:] = (
                        [redo_sentinel]
                        if direction == "undo"
                        else [redo_sentinel, command]
                    )
                    before_history = list(history)
                    before_redo = list(redo_stack)
                    replacement = CanvasHistoryState(
                        history=[object()],
                        redo_stack=[object()],
                        enabled=False,
                        limit=0,
                    )
                    primary = SystemExit(f"{direction} scene callback terminated")
                    original_move = history_access.move_atoms_for

                    def mutate_history_after_move(
                        *args,
                        _original_move=original_move,
                        _history=history,
                        _redo_stack=redo_stack,
                        _state=state,
                        _service=service,
                        _replacement=replacement,
                        _outcome=outcome,
                        _primary=primary,
                        **kwargs,
                    ) -> None:
                        _original_move(*args, **kwargs)
                        _history.clear()
                        _redo_stack.append(object())
                        _state.enabled = False
                        _state.limit = 0
                        _service.state = _replacement
                        if _outcome == "system_exit":
                            raise _primary

                    with mock.patch.object(
                        history_access,
                        "move_atoms_for",
                        side_effect=mutate_history_after_move,
                    ):
                        if outcome == "system_exit":
                            with self.assertRaises(SystemExit) as caught:
                                getattr(service, direction)()
                            self.assertIs(caught.exception, primary)
                        else:
                            getattr(service, direction)()

                    self.assertIs(service.state, state)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo_stack)
                    self.assertTrue(state.enabled)
                    self.assertEqual(state.limit, 100)
                    if outcome == "system_exit":
                        self.assertEqual(history, before_history)
                        self.assertEqual(redo_stack, before_redo)
                        self.assertEqual((atom.x, atom.y), source_position)
                    else:
                        expected_history = (
                            [history_sentinel]
                            if direction == "undo"
                            else [history_sentinel, command]
                        )
                        expected_redo = (
                            [redo_sentinel, command]
                            if direction == "undo"
                            else [redo_sentinel]
                        )
                        self.assertEqual(history, expected_history)
                        self.assertEqual(redo_stack, expected_redo)
                        expected_position = (
                            (3.0, 7.0) if direction == "undo" else (8.0, 16.0)
                        )
                        self.assertEqual((atom.x, atom.y), expected_position)

    def test_move_atom_transaction_capture_failure_uses_conservative_stacks(
        self,
    ) -> None:
        from chemvas.ui import history_canvas_access as history_access

        for direction in ("undo", "redo"):
            with self.subTest(direction=direction):
                canvas = self._canvas()
                atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
                command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
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
                primary = SystemExit("move transaction capture terminated")

                with mock.patch.object(
                    history_access,
                    "_capture_history_transaction_for_command",
                    side_effect=primary,
                ):
                    with self.assertRaises(SystemExit) as caught:
                        getattr(service, direction)()

                self.assertIs(caught.exception, primary)
                self.assertIs(state.history, history)
                self.assertIs(state.redo_stack, redo)
                if direction == "undo":
                    self.assertEqual(history, [history_sentinel])
                else:
                    self.assertEqual(history, [history_sentinel])
                self.assertEqual(redo, [])
                self.assertEqual(
                    (
                        canvas.model.atoms[atom_id].x,
                        canvas.model.atoms[atom_id].y,
                    ),
                    (3.0, 7.0),
                )

    def test_move_item_preflight_failures_keep_exact_retryable_service_stacks(
        self,
    ) -> None:
        from chemvas.ui import history_commands as history_commands_module

        for failure_source in ("membership", "handles"):
            for direction in ("undo", "redo"):
                with self.subTest(
                    failure_source=failure_source,
                    direction=direction,
                ):
                    canvas = self._canvas()
                    item = QGraphicsTextItem("preflight move")
                    item.setData(0, "note")
                    item.setPos(QPointF(3.0, 7.0))
                    canvas.scene().addItem(item)
                    command = MoveItemsCommand([item], 5.0, 9.0)
                    if direction == "undo":
                        item.setPos(QPointF(8.0, 16.0))
                    source_position = QPointF(item.pos())
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
                    primary = KeyboardInterrupt(
                        f"move-item {failure_source} preflight interrupted"
                    )
                    preflight_name = (
                        "_item_is_in_canvas_scene"
                        if failure_source == "membership"
                        else "_active_handle_position_snapshots"
                    )

                    with (
                        mock.patch.object(
                            history_commands_module,
                            "capture_history_transaction_for_command",
                            wraps=(
                                history_commands_module.capture_history_transaction_for_command
                            ),
                        ) as capture,
                        mock.patch.object(
                            history_commands_module,
                            "restore_history_transaction_for_command",
                            wraps=(
                                history_commands_module.restore_history_transaction_for_command
                            ),
                        ) as restore,
                        mock.patch.object(
                            history_commands_module,
                            "release_history_transaction_for_command",
                            wraps=(
                                history_commands_module.release_history_transaction_for_command
                            ),
                        ) as release,
                        mock.patch.object(
                            history_commands_module,
                            preflight_name,
                            side_effect=primary,
                        ),
                    ):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            getattr(service, direction)()

                    self.assertIs(caught.exception, primary)
                    self.assertEqual(capture.call_count, 1)
                    self.assertEqual(restore.call_count, 1)
                    self.assertEqual(release.call_count, 0)
                    self.assertEqual(item.pos(), source_position)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo)
                    self.assertEqual(history, expected_history)
                    self.assertEqual(redo, expected_redo)

                    getattr(service, direction)()
                    expected_position = (
                        QPointF(3.0, 7.0) if direction == "undo" else QPointF(8.0, 16.0)
                    )
                    self.assertEqual(item.pos(), expected_position)

    def test_legacy_marker_lookup_is_bypassed_by_operation_scope_authority(
        self,
    ) -> None:
        from chemvas.ui import history_canvas_access as history_access

        for direction in ("undo", "redo"):
            for primary_type, lookup_error_type in (
                (SystemExit, KeyboardInterrupt),
                (KeyboardInterrupt, SystemExit),
            ):
                with self.subTest(
                    direction=direction,
                    primary=primary_type.__name__,
                ):
                    lookup_error = lookup_error_type("marker lookup terminated")

                    class BrokenMarkerPrimary(primary_type):  # type: ignore[misc, valid-type]
                        def __init__(
                            self,
                            message: str,
                            marker_lookup_error: BaseException,
                        ) -> None:
                            super().__init__(message)
                            self._marker_lookup_error = marker_lookup_error

                        def __getattribute__(self, name: str):
                            if (
                                name
                                == "_chemvas_authoritative_history_transaction_restore"
                            ):
                                raise object.__getattribute__(
                                    self,
                                    "_marker_lookup_error",
                                )
                            return super().__getattribute__(name)

                    canvas = self._canvas()
                    atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
                    command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
                    service = canvas.services.history_service
                    state = service.state
                    history = state.history
                    redo = state.redo_stack
                    history_sentinel = object()
                    redo_sentinel = object()
                    if direction == "undo":
                        history[:] = [command]
                        redo[:] = [redo_sentinel]
                    else:
                        history[:] = [history_sentinel]
                        redo[:] = [redo_sentinel, command]
                    expected_history = list(history)
                    expected_redo = list(redo)
                    primary = BrokenMarkerPrimary(
                        f"{direction} primary interrupted",
                        lookup_error,
                    )
                    notifications = 0
                    state.change_callback = lambda: None
                    original_notify = service.notify_change

                    def count_notification(
                        _notify=original_notify,
                    ) -> None:
                        nonlocal notifications
                        notifications += 1
                        _notify()

                    original_mutation = history_access.move_atoms_for

                    def mutate_then_fail(
                        *args,
                        _mutation=original_mutation,
                        _primary=primary,
                        **kwargs,
                    ) -> None:
                        _mutation(*args, **kwargs)
                        raise _primary

                    with (
                        mock.patch.object(
                            history_access,
                            "move_atoms_for",
                            side_effect=mutate_then_fail,
                        ),
                        mock.patch.object(
                            service,
                            "notify_change",
                            side_effect=count_notification,
                        ),
                    ):
                        with self.assertRaises(primary_type) as caught:
                            getattr(service, direction)()

                    self.assertIs(caught.exception, primary)
                    self.assertEqual(notifications, 1)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo)
                    self.assertEqual(history, expected_history)
                    self.assertEqual(redo, expected_redo)
                    self.assertEqual(
                        (
                            canvas.model.atoms[atom_id].x,
                            canvas.model.atoms[atom_id].y,
                        ),
                        (3.0, 7.0),
                    )

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

    def test_failed_history_observer_cannot_recorrupt_restored_runtime(self) -> None:
        from chemvas.ui import history_canvas_access as history_access

        canvas = self._canvas()
        atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
        command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
        service = canvas.services.history_service
        state = service.state
        history = state.history
        redo_stack = state.redo_stack
        redo_sentinel = UpdateAtomColorCommand(atom_id, None, "blue")
        history[:] = [command]
        redo_stack[:] = [redo_sentinel]
        callback_calls = 0

        def corrupt_restored_result() -> None:
            nonlocal callback_calls
            callback_calls += 1
            canvas.model.atoms[atom_id].x = 900.0
            canvas.model.atoms[atom_id].y = 901.0
            state.history = [redo_sentinel]
            state.redo_stack = [command]
            state.enabled = False

        state.change_callback = corrupt_restored_result
        primary = KeyboardInterrupt("move interrupted after mutation")
        original_move = history_access.move_atoms_for

        def mutate_then_interrupt(*args, **kwargs) -> None:
            original_move(*args, **kwargs)
            raise primary

        with mock.patch.object(
            history_access,
            "move_atoms_for",
            side_effect=mutate_then_interrupt,
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                service.undo()

        self.assertIs(caught.exception, primary)
        self.assertEqual(callback_calls, 1)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(state.history, [command])
        self.assertEqual(state.redo_stack, [redo_sentinel])
        self.assertTrue(state.enabled)
        self.assertEqual(
            (
                canvas.model.atoms[atom_id].x,
                canvas.model.atoms[atom_id].y,
            ),
            (3.0, 7.0),
        )

    def test_legacy_failure_closes_nonauthoritative_publication_stacks(self) -> None:
        from chemvas.ui import history_canvas_access as history_access

        for direction in ("undo", "redo"):
            with self.subTest(direction=direction):
                primary = KeyboardInterrupt(f"legacy {direction} interrupted")
                poison = object()

                class LegacyCommand(HistoryCommand):
                    def __init__(self, error: BaseException) -> None:
                        self.error = error

                    def undo(self, _canvas) -> None:
                        raise self.error

                    def redo(self, _canvas) -> None:
                        raise self.error

                command = LegacyCommand(primary)
                sentinel = object()
                state = CanvasHistoryState(
                    history=[command] if direction == "undo" else [sentinel],
                    redo_stack=[sentinel] if direction == "undo" else [command],
                )
                history = state.history
                redo_stack = state.redo_stack
                state.change_callback = lambda: None
                service = CanvasHistoryService(object(), state)

                class PoisoningRuntimeSnapshot:
                    def __init__(self, target_state, target_service, marker) -> None:
                        self.target_state = target_state
                        self.target_service = target_service
                        self.marker = marker
                        self.verify_calls = 0

                    @staticmethod
                    def restore_with_result():
                        return HistoryTransactionRestoreResult(authoritative=True)

                    def verify_exact(self):
                        self.verify_calls += 1
                        self.target_state.history = [self.marker]
                        self.target_state.redo_stack = [self.marker]
                        self.target_service.state = CanvasHistoryState(
                            history=[self.marker],
                            redo_stack=[self.marker],
                        )
                        return ()

                runtime_snapshot = PoisoningRuntimeSnapshot(
                    state,
                    service,
                    poison,
                )
                with mock.patch.object(
                    history_access,
                    "capture_history_transaction_for_history",
                    return_value=runtime_snapshot,
                ):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        getattr(service, direction)()

                self.assertIs(caught.exception, primary)
                self.assertGreaterEqual(runtime_snapshot.verify_calls, 4)
                self.assertIs(service.state, state)
                self.assertIs(state.history, history)
                self.assertIs(state.redo_stack, redo_stack)
                self.assertEqual(
                    history,
                    [] if direction == "undo" else [sentinel],
                )
                self.assertEqual(redo_stack, [])

    def test_failed_runtime_restore_cannot_recorrupt_history_authority(self) -> None:
        from chemvas.ui import history_canvas_access as history_access

        canvas = self._canvas()
        atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
        command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
        service = canvas.services.history_service
        state = service.state
        history = state.history
        redo_stack = state.redo_stack
        redo_sentinel = UpdateAtomColorCommand(atom_id, None, "blue")
        history[:] = [command]
        redo_stack[:] = [redo_sentinel]
        callback_calls = 0

        def observer() -> None:
            nonlocal callback_calls
            callback_calls += 1

        state.change_callback = observer
        primary = KeyboardInterrupt("move interrupted before failure publication")
        original_move = history_access.move_atoms_for
        original_restore = history_access.restore_history_transaction_for_history
        restore_calls = 0

        def mutate_then_interrupt(*args, **kwargs) -> None:
            original_move(*args, **kwargs)
            raise primary

        def restore_runtime_then_corrupt_history(target_canvas, snapshot):
            nonlocal restore_calls
            result = original_restore(target_canvas, snapshot)
            restore_calls += 1
            if restore_calls == 2:
                state.history = [redo_sentinel]
                state.redo_stack = [command]
                state.enabled = False
                state.limit = 0
                service.state = CanvasHistoryState(
                    history=[object()],
                    redo_stack=[object()],
                    enabled=False,
                    limit=0,
                )
            return result

        with (
            mock.patch.object(
                history_access,
                "move_atoms_for",
                side_effect=mutate_then_interrupt,
            ),
            mock.patch.object(
                history_access,
                "restore_history_transaction_for_history",
                side_effect=restore_runtime_then_corrupt_history,
            ),
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                service.undo()

        self.assertIs(caught.exception, primary)
        self.assertEqual(callback_calls, 1)
        self.assertGreaterEqual(restore_calls, 2)
        self.assertIs(service.state, state)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(history, [command])
        self.assertEqual(redo_stack, [redo_sentinel])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 100)
        self.assertEqual(
            (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y),
            (3.0, 7.0),
        )

    def test_failed_runtime_verifier_cannot_poison_history_after_second_sweep(
        self,
    ) -> None:
        from chemvas.ui import history_canvas_access as history_access

        canvas = self._canvas()
        atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
        command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
        service = canvas.services.history_service
        state = service.state
        history = state.history
        redo_stack = state.redo_stack
        redo_sentinel = UpdateAtomColorCommand(atom_id, None, "blue")
        history[:] = [command]
        redo_stack[:] = [redo_sentinel]
        state.change_callback = lambda: None
        primary = KeyboardInterrupt("move interrupted before verifier poison")
        original_move = history_access.move_atoms_for
        original_capture = history_access.capture_history_transaction_for_history
        verify_calls = 0

        def mutate_then_interrupt(*args, **kwargs) -> None:
            original_move(*args, **kwargs)
            raise primary

        def capture_with_poisoning_verifier(*args, **kwargs):
            nonlocal verify_calls
            snapshot = original_capture(*args, **kwargs)
            if kwargs.get("guard_scene_rect") is not False:
                return snapshot

            class RuntimeSnapshotProxy:
                def restore_with_result(self):
                    return snapshot.restore_with_result()

                def verify_exact(self):
                    nonlocal verify_calls
                    errors = snapshot.verify_exact()
                    verify_calls += 1
                    if verify_calls == 2:
                        state.history = [redo_sentinel]
                        state.redo_stack = [command]
                        state.enabled = False
                        state.limit = 0
                        service.state = CanvasHistoryState(
                            history=[object()],
                            redo_stack=[object()],
                            enabled=False,
                            limit=0,
                        )
                    return errors

            return RuntimeSnapshotProxy()

        with (
            mock.patch.object(
                history_access,
                "move_atoms_for",
                side_effect=mutate_then_interrupt,
            ),
            mock.patch.object(
                history_access,
                "capture_history_transaction_for_history",
                side_effect=capture_with_poisoning_verifier,
            ),
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                service.undo()

        self.assertIs(caught.exception, primary)
        self.assertGreaterEqual(verify_calls, 3)
        self.assertIs(service.state, state)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(history, [command])
        self.assertEqual(redo_stack, [redo_sentinel])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 100)
        self.assertEqual(
            (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y),
            (3.0, 7.0),
        )

    def test_failed_history_reassert_runtime_poison_uses_reverse_pass(self) -> None:
        from chemvas.ui import history_canvas_access as history_access

        canvas = self._canvas()
        atom_id = add_atom_for(canvas, "C", 3.0, 7.0)
        atom = canvas.model.atoms[atom_id]
        command = MoveAtomsCommand({atom_id}, 5.0, 9.0)
        redo_sentinel = UpdateAtomColorCommand(atom_id, None, "blue")

        class _RuntimePoisoningState:
            def __init__(self) -> None:
                self._history = [command]
                self._redo_stack = [redo_sentinel]
                self.enabled = True
                self.limit = 100
                self.change_callback = self.observe_failure
                self.callback_calls = 0
                self.poisoning_setters = 0
                self.poisoned_setter_calls = 0

            @property
            def history(self):
                return self._history

            @history.setter
            def history(self, value) -> None:
                self._history = value
                if self.poisoning_setters:
                    self.poisoning_setters -= 1
                    self.poisoned_setter_calls += 1
                    atom.x = 900.0 + self.poisoned_setter_calls

            @property
            def redo_stack(self):
                return self._redo_stack

            @redo_stack.setter
            def redo_stack(self, value) -> None:
                self._redo_stack = value

            def observe_failure(self) -> None:
                self.callback_calls += 1
                self._history.clear()
                atom.x = 800.0
                # First poison occurs during notify_change's silent reassert;
                # second occurs after the first outer runtime restore.
                self.poisoning_setters = 2

        state = _RuntimePoisoningState()
        history = state.history
        redo_stack = state.redo_stack
        service = CanvasHistoryService(canvas, state)
        primary = SystemExit("move failure needs cross-authority recovery")
        original_move = history_access.move_atoms_for

        def mutate_then_exit(*args, **kwargs) -> None:
            original_move(*args, **kwargs)
            raise primary

        with mock.patch.object(
            history_access,
            "move_atoms_for",
            side_effect=mutate_then_exit,
        ):
            with self.assertRaises(SystemExit) as caught:
                service.undo()

        self.assertIs(caught.exception, primary)
        self.assertEqual(state.callback_calls, 1)
        self.assertEqual(state.poisoned_setter_calls, 2)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(history, [command])
        self.assertEqual(redo_stack, [redo_sentinel])
        self.assertEqual((atom.x, atom.y), (3.0, 7.0))

    def test_ring_polygon_failure_restores_auto_rect_and_retryable_stack(self) -> None:
        scene = QGraphicsScene()
        before = [
            [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)],
            [(20.0, 0.0), (30.0, 0.0), (20.0, 10.0)],
        ]
        after = [
            [(10_000.0, 0.0), (10_010.0, 0.0), (10_000.0, 10.0)],
            [(20_000.0, 0.0), (20_010.0, 0.0), (20_000.0, 10.0)],
        ]
        items = [
            QGraphicsPolygonItem(QPolygonF([QPointF(x, y) for x, y in points]))
            for points in before
        ]
        for item in items:
            scene.addItem(item)
        canvas = type("RingCanvas", (), {"scene": lambda self: scene})()
        command = SetRingPolygonsCommand(items, before, after)
        history = []
        redo = [command]
        service = CanvasHistoryService(
            canvas,
            CanvasHistoryState(history=history, redo_stack=redo),
        )
        baseline = QRectF(scene.sceneRect())
        original_set_polygon = items[1].setPolygon
        failed = False

        def set_polygon_then_interrupt(polygon) -> None:
            nonlocal failed
            original_set_polygon(polygon)
            if not failed:
                failed = True
                raise KeyboardInterrupt("second ring polygon interrupted")

        with mock.patch.object(
            items[1],
            "setPolygon",
            side_effect=set_polygon_then_interrupt,
        ):
            with self.assertRaisesRegex(
                KeyboardInterrupt,
                "second ring polygon interrupted",
            ):
                service.redo()

        self.assertIs(service.state.history, history)
        self.assertIs(service.state.redo_stack, redo)
        self.assertEqual(history, [])
        self.assertEqual(redo, [command])
        self.assertEqual(scene.sceneRect(), baseline)
        for item, points in zip(items, before, strict=True):
            self.assertEqual(
                [(point.x(), point.y()) for point in item.polygon()],
                points,
            )

        future = scene.addRect(QRectF(50_000.0, 0.0, 10.0, 10.0))
        self.assertGreater(scene.sceneRect().right(), 50_000.0)
        scene.removeItem(future)
        service.redo()
        self.assertEqual(history, [command])
        self.assertEqual(redo, [])

    def test_atom_position_failure_restores_actual_qt_auto_rect(self) -> None:
        for error_type in (KeyboardInterrupt, SystemExit):
            with self.subTest(error=error_type.__name__):
                canvas = self._canvas()
                atom_id = add_atom_for(canvas, "C", 0.0, 0.0)
                scene = canvas.scene()
                scene.setSceneRect(QRectF())
                scene._chemvas_scene_rect_automatic = True
                tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
                if tracker is not None:
                    current = QRectF(scene.sceneRect())
                    tracker.known_rect = QRectF(current)
                    tracker.baseline_rect = QRectF(current)
                    tracker.pending_rect = QRectF(current)
                    tracker.pending_expansions.clear()
                    tracker.pending_journal.clear()
                    tracker.depth = 0
                baseline = QRectF(scene.sceneRect())
                command = SetAtomPositionsCommand(
                    {atom_id: (0.0, 0.0)},
                    {atom_id: (10_000.0, 0.0)},
                )
                from chemvas.ui import history_canvas_access as history_access

                original_set_positions = history_access.set_atom_positions_for_history
                primary = error_type("atom position update interrupted")

                def set_positions_then_interrupt(
                    *args,
                    _setter=original_set_positions,
                    _primary=primary,
                    **kwargs,
                ) -> None:
                    _setter(*args, **kwargs)
                    raise _primary

                with mock.patch.object(
                    history_access,
                    "set_atom_positions_for_history",
                    side_effect=set_positions_then_interrupt,
                ):
                    with self.assertRaises(error_type) as caught:
                        command.redo(canvas)

                self.assertIs(caught.exception, primary)
                self.assertEqual(
                    (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y),
                    (0.0, 0.0),
                )
                self.assertEqual(scene.sceneRect(), baseline)
                future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
                self.assertGreater(scene.sceneRect().right(), 20_000.0)
                scene.removeItem(future)

    def test_broken_add_note_cannot_replace_ui_transaction_primary(self) -> None:
        from chemvas.core.history import _add_history_rollback_note
        from chemvas.ui.canvas_delete_transaction import _add_delete_rollback_note
        from chemvas.ui.canvas_document_session_service import _add_scene_recovery_note
        from chemvas.ui.canvas_geometry_controller import _add_bond_length_rollback_note
        from chemvas.ui.canvas_history_service import _add_history_notification_note
        from chemvas.ui.history_canvas_access import _add_move_rollback_note
        from chemvas.ui.history_commands import _add_rollback_error_note

        class BrokenNoteCallPrimary(SystemExit):
            def add_note(self, _note: str) -> None:
                raise KeyboardInterrupt("broken add_note")

        class BrokenNoteLookupSystemExit(SystemExit):
            def __getattribute__(self, name: str):
                if name == "add_note":
                    raise KeyboardInterrupt("broken add_note lookup")
                return super().__getattribute__(name)

        class BrokenNoteLookupKeyboardInterrupt(KeyboardInterrupt):
            def __getattribute__(self, name: str):
                if name == "add_note":
                    raise SystemExit("broken add_note lookup")
                return super().__getattribute__(name)

        helpers = (
            ("core", _add_history_rollback_note),
            ("delete", _add_delete_rollback_note),
            (
                "document",
                lambda primary, secondary: _add_scene_recovery_note(
                    primary,
                    secondary,
                    phase="testing note safety",
                ),
            ),
            ("geometry", _add_bond_length_rollback_note),
            ("history", _add_history_notification_note),
            ("move", _add_move_rollback_note),
            (
                "ui-history",
                lambda primary, secondary: _add_rollback_error_note(
                    primary,
                    secondary,
                    phase="testing note safety",
                ),
            ),
        )
        for name, helper in helpers:
            for primary_type in (
                BrokenNoteCallPrimary,
                BrokenNoteLookupSystemExit,
                BrokenNoteLookupKeyboardInterrupt,
            ):
                with self.subTest(helper=name, primary=primary_type.__name__):
                    primary = primary_type(f"{name} primary")
                    helper(primary, RuntimeError(f"{name} rollback failed"))
                    with self.assertRaises(primary_type) as caught:
                        raise primary
                    self.assertIs(caught.exception, primary)

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
