import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    HistoryTransactionRestoreResult,
    UpdateBondCommand,
)
from chemvas.domain.document import Atom, Bond
from chemvas.ui.atom_coords_access import set_atom_coords_3d_for
from chemvas.ui.canvas_history_recording_service import (
    CanvasHistoryRecordingService,
)
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas_smiles_input_state import CanvasSmilesInputState
from chemvas.ui.history_commands import AddSceneItemsCommand


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
        services=canvas_runtime_services(history_service=history_service),
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
    def test_canvas_services_property_cannot_redefine_raw_history_baseline(
        self,
    ) -> None:
        state = CanvasHistoryState()
        sentinel = object()

        class Command(HistoryCommand):
            def undo(self, target) -> None:
                target.value = "before"

            def redo(self, target) -> None:
                target.value = "after"

        class History:
            def __init__(self) -> None:
                self.state = state

            @staticmethod
            def push(command) -> bool:
                state.history.append(command)
                state.redo_stack.clear()
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        history = History()
        services = canvas_runtime_services(history_service=history)

        class Canvas:
            def __init__(self) -> None:
                self.value = "after"
                self.model = SimpleNamespace(
                    atoms={},
                    bonds=[],
                    next_atom_id=0,
                )
                self.history_state = state
                self.smiles_input_state = CanvasSmilesInputState(
                    last_smiles_input="after-smiles"
                )
                self._services = services
                self.services_reads = 0

            @property
            def services(self):
                self.services_reads += 1
                state.history.append(sentinel)
                self.value = "descriptor poison"
                return self._services

        canvas = Canvas()
        command = Command()
        CanvasHistoryRecordingService(canvas, history).push_history(command)

        self.assertEqual(canvas.services_reads, 0)
        self.assertEqual(canvas.value, "after")
        self.assertEqual(state.history, [command])
        self.assertNotIn(sentinel, state.history)
        self.assertEqual(state.redo_stack, [])

    def test_record_bond_update_does_not_cross_live_enabled_getter(self) -> None:
        bond = Bond(1, 2, order=2)
        canvas = _make_canvas(bonds=[bond], history_enabled=True)
        state = canvas.history_state

        class History:
            def __init__(self) -> None:
                self.state = state
                self.is_enabled = mock.Mock(side_effect=self.poison_runtime)

            @staticmethod
            def poison_runtime() -> bool:
                bond.order = 3
                return False

            @staticmethod
            def push(command) -> bool:
                state.history.append(command)
                state.redo_stack.clear()
                return True

        history = History()
        canvas.services.history_service = history
        CanvasHistoryRecordingService(canvas, history).record_bond_update(
            bond_id=0,
            before_state={
                "a": 1,
                "b": 2,
                "order": 1,
                "style": "single",
                "color": "#000000",
            },
            after_state={
                "a": 1,
                "b": 2,
                "order": 2,
                "style": "single",
                "color": "#000000",
            },
            before_smiles_input="before-smiles",
            after_smiles_input="after-smiles",
        )

        history.is_enabled.assert_not_called()
        self.assertEqual(bond.order, 2)
        self.assertEqual(len(state.history), 1)

    def test_enabled_recording_push_false_rolls_back_and_raises(self) -> None:
        canvas = SimpleNamespace(value="after")
        state = CanvasHistoryState(enabled=True)

        class Command(HistoryCommand):
            def undo(self, target) -> None:
                target.value = "before"

            def redo(self, target) -> None:
                target.value = "after"

        class RuntimeSnapshot:
            def __init__(self) -> None:
                self.value = canvas.value

            def verify_exact(self):
                return ()

            def restore_with_result(self):
                canvas.value = self.value
                return HistoryTransactionRestoreResult(authoritative=True)

            @staticmethod
            def release() -> None:
                return None

        history = SimpleNamespace(
            state=state,
            push=lambda _command: False,
            notify_change=lambda: None,
        )
        with (
            mock.patch(
                "chemvas.ui.canvas_history_recording_service.capture_history_transaction_for_history",
                side_effect=lambda *_args, **_kwargs: RuntimeSnapshot(),
            ),
            self.assertRaisesRegex(RuntimeError, "explicitly disabled policy"),
        ):
            CanvasHistoryRecordingService(canvas, history)._push_history(Command())

        self.assertEqual(canvas.value, "before")
        self.assertTrue(state.enabled)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_capture_failure_rolls_back_recorded_mutation(self) -> None:
        # The canvas is already mutated when a recorded push starts; a
        # capture failure (malformed history state is a real bug shape) must
        # run the inverse before propagating so the canvas cannot silently
        # diverge from what history describes.
        canvas = _make_canvas(
            atoms={0: Atom("C", 1.0, 2.0)},
            next_atom_id=1,
        )
        state = CanvasHistoryState()
        state.history = "not-a-list"  # type: ignore[assignment]
        history_service = SimpleNamespace(
            state=state,
            push=mock.Mock(),
            is_enabled=mock.Mock(return_value=True),
        )
        service = CanvasHistoryRecordingService(canvas, history_service=history_service)

        with self.assertRaisesRegex(
            RuntimeError,
            "exact mutable history stacks",
        ):
            service.record_additions(
                before_next_atom_id=0,
                before_bond_count=0,
                before_smiles_input="before-smiles",
            )

        history_service.push.assert_not_called()
        self.assertEqual(set(canvas.model.atoms), {0})

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
        disabled_bond = Bond(1, 2, order=2)
        disabled_canvas = _make_canvas(
            bonds=[None, disabled_bond],
            history_enabled=False,
        )
        disabled_canvas.services.history_service = CanvasHistoryService(
            disabled_canvas,
            disabled_canvas.history_state,
        )
        _recording_service(disabled_canvas).record_bond_update(
            bond_id=1,
            before_state={
                "a": 1,
                "b": 2,
                "order": 1,
                "style": "single",
                "color": "#000000",
            },
            after_state={
                "a": 1,
                "b": 2,
                "order": 2,
                "style": "single",
                "color": "#000000",
            },
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
