import os
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    HistoryTransactionRestoreResult,
    UpdateBondCommand,
)
from core.model import Atom, Bond
from ui.atom_coords_access import set_atom_coords_3d_for
from ui.canvas_history_recording_service import CanvasHistoryRecordingService
from ui.canvas_history_state import CanvasHistoryState
from ui.canvas_smiles_input_state import CanvasSmilesInputState
from ui.history_commands import AddSceneItemsCommand
from ui.history_push_failure_recovery import (
    RecordingHistoryPolicySnapshot,
    _verify_history_and_policy_authority,
)
from ui.history_stack_snapshot import HistoryStackSnapshot


class _SceneItem:
    def __init__(self, kind: str, state: dict) -> None:
        self._data = {0: kind, 9: dict(state)}

    def data(self, key: int):
        return self._data.get(key)


class _FailOnceHistoryState:
    def __init__(self, fail_field: str, history: list, redo_stack: list) -> None:
        self.fail_field = fail_field
        self.read_counts = {"history": 0, "redo_stack": 0}
        self._history = history
        self._redo_stack = redo_stack

    def _read(self, field: str, value: list) -> list:
        self.read_counts[field] += 1
        if self.fail_field == field and self.read_counts[field] == 1:
            raise AttributeError(f"live history {field} capture failed")
        return value

    @property
    def history(self) -> list:
        return self._read("history", self._history)

    @history.setter
    def history(self, value: list) -> None:
        self._history = value

    @property
    def redo_stack(self) -> list:
        return self._read("redo_stack", self._redo_stack)

    @redo_stack.setter
    def redo_stack(self, value: list) -> None:
        self._redo_stack = value


class _FailOnceHistoryService:
    def __init__(self, fail_field: str, history: list, redo_stack: list) -> None:
        self.fail_field = fail_field
        self.state_reads = 0
        self._state = _FailOnceHistoryState(fail_field, history, redo_stack)
        self.push_calls = 0
        self.push_error: BaseException | None = None

    @property
    def state(self) -> _FailOnceHistoryState:
        self.state_reads += 1
        if self.fail_field == "state" and self.state_reads == 1:
            raise AttributeError("live history state capture failed")
        return self._state

    def push(self, command) -> None:
        self.push_calls += 1
        self._state._history.append(command)
        self._state._redo_stack.clear()
        if self.push_error is not None:
            error = self.push_error
            self.push_error = None
            raise error

    @staticmethod
    def is_enabled() -> bool:
        return True


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
        _atom_state_dict=mock.Mock(
            side_effect=lambda atom_id: {"atom_id": atom_id, "kind": "atom"}
        ),
        _bond_state_dict=mock.Mock(
            side_effect=lambda bond: {"bond": getattr(bond, "name", "bond")}
        ),
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
    def test_successful_push_command_payload_mutation_rolls_back_exactly(self) -> None:
        canvas = SimpleNamespace(value="after")
        old_history = object()
        old_redo = object()
        state = CanvasHistoryState(
            history=[old_history],
            redo_stack=[old_redo],
        )

        @dataclass
        class Command(HistoryCommand):
            after_state: dict[str, str]

            def undo(self, target) -> None:
                target.value = "before"

            def redo(self, target) -> None:
                target.value = self.after_state["value"]

        command = Command(after_state={"value": "after"})

        class History:
            def __init__(self) -> None:
                self.state = state

            def push(self, published) -> bool:
                state.history.append(published)
                state.redo_stack.clear()
                published.after_state["value"] = "poison"
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        with self.assertRaisesRegex(RuntimeError, "history command field"):
            CanvasHistoryRecordingService(
                canvas,
                history_service=History(),
            )._push_history(command)

        self.assertEqual(command.after_state, {"value": "after"})
        self.assertEqual(canvas.value, "before")
        self.assertEqual(state.history, [old_history])
        self.assertEqual(state.redo_stack, [old_redo])

    def test_recording_authority_rejects_cross_policy_reader_poisoning(self) -> None:
        class CrossPolicyState:
            def __init__(self) -> None:
                self.history: list[object] = []
                self.redo_stack: list[object] = []
                self.enabled = True
                self._limit = 100
                self.poison_enabled = False

            @property
            def limit(self) -> int:
                if self.poison_enabled:
                    self.enabled = False
                return self._limit

            @limit.setter
            def limit(self, value: int) -> None:
                self._limit = value

        state = CrossPolicyState()
        history_service = SimpleNamespace(state=state, notify_change=lambda: None)
        history_snapshot = HistoryStackSnapshot.capture(history_service)
        self.assertIsNotNone(history_snapshot)
        assert history_snapshot is not None
        policy_snapshot = RecordingHistoryPolicySnapshot.capture(history_snapshot)
        state.poison_enabled = True

        with self.assertRaisesRegex(RuntimeError, "policy 'enabled' changed"):
            _verify_history_and_policy_authority(
                history_snapshot,
                policy_snapshot,
            )

    def test_push_failure_observer_cannot_recontaminate_rolled_back_runtime(
        self,
    ) -> None:
        canvas = SimpleNamespace(value="after")
        old_history_entry = object()
        old_redo_entry = object()
        state = CanvasHistoryState(
            history=[old_history_entry],
            redo_stack=[old_redo_entry],
        )
        history_list = state.history
        redo_list = state.redo_stack
        primary = KeyboardInterrupt("recording push interrupted")
        observer_calls = 0

        class Command(HistoryCommand):
            def undo(self, target) -> None:
                target.value = "before"

            def redo(self, target) -> None:
                target.value = "after"

        class History:
            def __init__(self) -> None:
                self.state = state

            def push(self, command) -> None:
                state.history.append(command)
                state.redo_stack.clear()
                raise primary

            def notify_change(self) -> None:
                nonlocal observer_calls
                observer_calls += 1
                canvas.value = "observer poison"

        class RuntimeSnapshot:
            def __init__(self) -> None:
                self.value = canvas.value

            def verify_exact(self):
                if canvas.value != self.value:
                    return (RuntimeError("runtime value changed"),)
                return ()

        def restore_runtime(_canvas, snapshot):
            canvas.value = snapshot.value
            return HistoryTransactionRestoreResult(authoritative=True)

        service = CanvasHistoryRecordingService(canvas, history_service=History())
        with (
            mock.patch(
                "ui.history_push_failure_recovery.capture_history_transaction_for_history",
                side_effect=lambda *_args, **_kwargs: RuntimeSnapshot(),
            ),
            mock.patch(
                "ui.history_push_failure_recovery.restore_history_transaction_for_history",
                side_effect=restore_runtime,
            ),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            service._push_history(Command())

        self.assertIs(caught.exception, primary)
        self.assertEqual(observer_calls, 1)
        self.assertEqual(canvas.value, "before")
        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(history_list, [old_history_entry])
        self.assertEqual(redo_list, [old_redo_entry])

    def test_push_failure_restores_exact_after_authority_before_inverse(self) -> None:
        canvas = SimpleNamespace(value="after", unrelated="clean")
        old_history_entry = object()
        old_redo_entry = object()
        state = CanvasHistoryState(
            history=[old_history_entry],
            redo_stack=[old_redo_entry],
            enabled=True,
            limit=23,
        )
        history_list = state.history
        redo_list = state.redo_stack
        primary = KeyboardInterrupt("recording push mutated then interrupted")
        inverse_preflights: list[tuple[object, ...]] = []

        @dataclass
        class Command(HistoryCommand):
            after_state: dict[str, str]

            def undo(self, target) -> None:
                inverse_preflights.append(
                    (
                        dict(self.after_state),
                        target.value,
                        target.unrelated,
                        tuple(state.history),
                        tuple(state.redo_stack),
                        state.enabled,
                        state.limit,
                    )
                )
                target.value = "before"

            def redo(self, target) -> None:
                target.value = self.after_state["value"]

        command = Command(after_state={"value": "after"})

        class History:
            def __init__(self) -> None:
                self.state = state

            def push(self, published) -> None:
                state.history.append(published)
                state.redo_stack.clear()
                state.enabled = False
                state.limit = 0
                published.after_state["value"] = "push payload poison"
                canvas.value = "push value poison"
                canvas.unrelated = "push unrelated poison"
                raise primary

            @staticmethod
            def notify_change() -> None:
                return None

        class RuntimeSnapshot:
            def __init__(self) -> None:
                self.value = canvas.value
                self.unrelated = canvas.unrelated

            def verify_exact(self):
                if (canvas.value, canvas.unrelated) != (
                    self.value,
                    self.unrelated,
                ):
                    return (RuntimeError("runtime changed"),)
                return ()

        def capture_runtime(*_args, **_kwargs):
            return RuntimeSnapshot()

        def restore_runtime(_canvas, snapshot):
            canvas.value = snapshot.value
            canvas.unrelated = snapshot.unrelated
            # The runtime port is itself untrusted. The command snapshot must
            # be the final payload writer before inverse dispatch.
            command.after_state["value"] = "restore payload poison"
            return HistoryTransactionRestoreResult(authoritative=True)

        service = CanvasHistoryRecordingService(canvas, history_service=History())
        with (
            mock.patch(
                "ui.canvas_history_recording_service.capture_history_transaction_for_history",
                side_effect=capture_runtime,
            ),
            mock.patch(
                "ui.canvas_history_recording_service.release_history_transaction_for_history",
                return_value=None,
            ),
            mock.patch(
                "ui.history_push_failure_recovery.capture_history_transaction_for_history",
                side_effect=capture_runtime,
            ),
            mock.patch(
                "ui.history_push_failure_recovery.restore_history_transaction_for_history",
                side_effect=restore_runtime,
            ),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            service._push_history(command)

        self.assertIs(caught.exception, primary)
        self.assertEqual(
            inverse_preflights,
            [
                (
                    {"value": "after"},
                    "after",
                    "clean",
                    (old_history_entry,),
                    (old_redo_entry,),
                    True,
                    23,
                )
            ],
        )
        self.assertEqual(canvas.value, "before")
        self.assertEqual(canvas.unrelated, "clean")
        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(history_list, [old_history_entry])
        self.assertEqual(redo_list, [old_redo_entry])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 23)

    def test_runtime_restore_cannot_leave_recording_history_root_poisoned(
        self,
    ) -> None:
        canvas = SimpleNamespace(value="after")
        old_history_entry = object()
        old_redo_entry = object()
        poison = object()
        state = CanvasHistoryState(
            history=[old_history_entry],
            redo_stack=[old_redo_entry],
            enabled=True,
            limit=37,
        )
        history_list = state.history
        redo_list = state.redo_stack
        primary = KeyboardInterrupt("recording push interrupted")

        class Command(HistoryCommand):
            def undo(self, target) -> None:
                target.value = "before"

            def redo(self, target) -> None:
                target.value = "after"

        class History:
            def __init__(self) -> None:
                self.state = state

            def push(self, command) -> None:
                state.history.append(command)
                state.redo_stack.clear()
                raise primary

            @staticmethod
            def notify_change() -> None:
                return None

        class RuntimeSnapshot:
            def __init__(self) -> None:
                self.value = canvas.value

            def verify_exact(self):
                if canvas.value != self.value:
                    return (RuntimeError("runtime value changed"),)
                return ()

        restore_calls = 0

        def restore_runtime(_canvas, snapshot):
            nonlocal restore_calls
            restore_calls += 1
            canvas.value = snapshot.value
            state.history = [poison]
            state.redo_stack = [poison]
            state.enabled = False
            state.limit = 0
            return HistoryTransactionRestoreResult(authoritative=True)

        service = CanvasHistoryRecordingService(canvas, history_service=History())
        with (
            mock.patch(
                "ui.history_push_failure_recovery.capture_history_transaction_for_history",
                side_effect=lambda *_args, **_kwargs: RuntimeSnapshot(),
            ),
            mock.patch(
                "ui.history_push_failure_recovery.restore_history_transaction_for_history",
                side_effect=restore_runtime,
            ),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            service._push_history(Command())

        self.assertIs(caught.exception, primary)
        self.assertGreaterEqual(restore_calls, 1)
        self.assertEqual(canvas.value, "before")
        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(history_list, [old_history_entry])
        self.assertEqual(redo_list, [old_redo_entry])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 37)

    def test_push_failure_restores_exact_history_stacks(self) -> None:
        canvas = _make_canvas(
            atoms={0: Atom("C", 1.0, 2.0)},
            next_atom_id=1,
        )
        old_history_entry = object()
        old_redo_entry = object()
        state = CanvasHistoryState(
            history=[old_history_entry],
            redo_stack=[old_redo_entry],
        )
        history_list = state.history
        redo_list = state.redo_stack
        push_error = RuntimeError("injected post-append failure")

        def append_then_raise(command) -> None:
            state.history.append(command)
            state.redo_stack.clear()
            raise push_error

        history_service = SimpleNamespace(
            state=state,
            push=append_then_raise,
            is_enabled=mock.Mock(return_value=True),
        )
        service = CanvasHistoryRecordingService(canvas, history_service=history_service)

        with self.assertRaises(RuntimeError) as raised:
            service.record_additions(
                before_next_atom_id=0,
                before_bond_count=0,
                before_smiles_input="before-smiles",
            )

        self.assertIs(raised.exception, push_error)
        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(state.history, [old_history_entry])
        self.assertEqual(state.redo_stack, [old_redo_entry])

    def test_history_descriptor_capture_and_control_flow_retry(self) -> None:
        cases = (
            ("state", KeyboardInterrupt),
            ("history", SystemExit),
            ("redo_stack", KeyboardInterrupt),
        )
        for fail_field, error_type in cases:
            with self.subTest(field=fail_field, error=error_type.__name__):
                canvas = _make_canvas(
                    atoms={0: Atom("C", 1.0, 2.0)},
                    next_atom_id=1,
                )
                old_history_entry = object()
                old_redo_entry = object()
                history = [old_history_entry]
                redo_stack = [old_redo_entry]
                history_service = _FailOnceHistoryService(
                    fail_field,
                    history,
                    redo_stack,
                )
                service = CanvasHistoryRecordingService(
                    canvas,
                    history_service=history_service,
                )

                with self.assertRaisesRegex(
                    AttributeError,
                    f"{fail_field} capture failed",
                ):
                    service.record_additions(
                        before_next_atom_id=0,
                        before_bond_count=0,
                        before_smiles_input="before-smiles",
                    )

                self.assertEqual(history_service.push_calls, 0)
                self.assertIs(history_service._state._history, history)
                self.assertIs(history_service._state._redo_stack, redo_stack)
                self.assertEqual(history, [old_history_entry])
                self.assertEqual(redo_stack, [old_redo_entry])

                primary_error = error_type("recording history push interrupted")
                history_service.push_error = primary_error
                with self.assertRaises(error_type) as raised:
                    service.record_additions(
                        before_next_atom_id=0,
                        before_bond_count=0,
                        before_smiles_input="before-smiles",
                    )

                self.assertIs(raised.exception, primary_error)
                self.assertIs(history_service._state._history, history)
                self.assertIs(history_service._state._redo_stack, redo_stack)
                self.assertEqual(history, [old_history_entry])
                self.assertEqual(redo_stack, [old_redo_entry])

                service.record_additions(
                    before_next_atom_id=0,
                    before_bond_count=0,
                    before_smiles_input="before-smiles",
                )

                self.assertEqual(len(history), 2)
                self.assertIsInstance(history[-1], AddAtomsCommand)
                self.assertEqual(redo_stack, [])

    def test_record_additions_pushes_composite_command_for_atom_bond_and_scene_items(
        self,
    ) -> None:
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
        self.assertEqual(
            [type(item) for item in command.commands],
            [AddAtomsCommand, AddBondCommand, AddSceneItemsCommand],
        )

        atom_command = command.commands[0]
        self.assertEqual(
            atom_command.atom_states,
            {
                1: {
                    "element": "C",
                    "x": 1.0,
                    "y": 2.0,
                    "color": "#000000",
                    "explicit_label": False,
                },
                2: {
                    "element": "O",
                    "x": 3.0,
                    "y": 4.0,
                    "color": "#112233",
                    "explicit_label": False,
                },
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

    def test_record_additions_includes_atom_coords_3d_in_add_atoms_command(
        self,
    ) -> None:
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

    def test_record_additions_pushes_single_scene_item_command_when_only_scene_items_are_added(
        self,
    ) -> None:
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

    def test_record_additions_skips_empty_sparse_atom_range_and_none_only_scene_items(
        self,
    ) -> None:
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
        before_state = {
            "a": 1,
            "b": 2,
            "order": 1,
            "style": "single",
            "color": "#000000",
        }
        after_state = {**before_state, "order": 2}
        canvas = _make_canvas(
            bonds=[None, None, None, None, Bond(1, 2, order=2)],
            history_enabled=True,
        )

        _recording_service(canvas).record_bond_update(
            bond_id=4,
            before_state=before_state,
            after_state=after_state,
            before_smiles_input="before-smiles",
            after_smiles_input="after-smiles",
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, UpdateBondCommand)
        self.assertEqual(command.bond_id, 4)
        self.assertEqual(command.before_state, before_state)
        self.assertEqual(command.after_state, after_state)
        self.assertEqual(command.before_smiles_input, "before-smiles")
        self.assertEqual(command.after_smiles_input, "after-smiles")

    def test_record_bond_update_skips_push_when_history_disabled_or_state_is_unchanged(
        self,
    ) -> None:
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
