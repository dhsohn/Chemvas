import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.core.model_commands import (
    AddAtomsCommand,
    AddBondCommand,
    UpdateBondCommand,
)
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.ui.annotations.materialize import create_scene_item_from_state
from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_group_state import CanvasGroupState
from chemvas.ui.canvas.canvas_history_recording_service import (
    CanvasHistoryRecordingService,
)
from chemvas.ui.canvas.canvas_history_state import CanvasHistoryState
from chemvas.ui.history.history_commands import AddSceneItemsCommand
from chemvas.ui.molecule.atom_coords_access import (
    CanvasAtomCoords3DState,
    set_atom_coords_3d_for,
)
from tests.scene_render_context import attach_scene_render_context


def _make_canvas(*, atoms=None, bonds=None, next_atom_id=0):
    push_command = mock.Mock()
    history_service = SimpleNamespace(push=push_command)
    return SimpleNamespace(
        push_command=push_command,
        services=canvas_runtime_services(history_service=history_service),
        model=MoleculeModel(
            atoms=dict(atoms or {}),
            bonds=list(bonds or []),
            next_atom_id=next_atom_id,
        ),
        runtime_state=canvas_runtime_state(
            group_state=CanvasGroupState(),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            atom_graphics_state=CanvasAtomGraphicsState(),
            history_state=CanvasHistoryState(),
        ),
    )


def _recording_service(canvas) -> CanvasHistoryRecordingService:
    return CanvasHistoryRecordingService(
        canvas,
        history_service=canvas.services.history_service,
    )


class CanvasHistoryRecordingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

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
            def push(command) -> None:
                state.history.append(command)
                state.redo_stack.clear()

            @staticmethod
            def notify_change() -> None:
                return None

        history = History()
        services = canvas_runtime_services(history_service=history)

        class Canvas:
            def __init__(self) -> None:
                self.value = "after"
                self.model = MoleculeModel(
                    atoms={},
                    bonds=[],
                    next_atom_id=0,
                )
                self.runtime_state = canvas_runtime_state(
                    atom_coords_3d_state=CanvasAtomCoords3DState(),
                    history_state=state,
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

    def test_record_additions_pushes_composite_command_for_atom_bond_and_scene_items(
        self,
    ) -> None:
        existing_bond = Bond(0, 1)
        new_bond = Bond(1, 2, 2, style="double_center", color="#336699")
        canvas = _make_canvas(
            atoms={1: Atom("C", 1.0, 2.0), 2: Atom("O", 3.0, 4.0, color="#112233")},
            bonds=[existing_bond, new_bond],
            next_atom_id=3,
        )
        context = attach_scene_render_context(canvas)
        arrow_state = {
            "kind": "arrow",
            "start": (1.0, 2.0),
            "end": (3.0, 4.0),
            "control": None,
            "double": False,
        }
        scene_item = create_scene_item_from_state(context, arrow_state)

        _recording_service(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=1,
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

        bond_command = command.commands[1]
        self.assertEqual(bond_command.bond_id, 1)
        self.assertEqual(
            bond_command.bond_state,
            {"a": 1, "b": 2, "order": 2, "style": "double_center", "color": "#336699"},
        )
        self.assertEqual(bond_command.previous_bond_count, 1)

        scene_item_command = command.commands[2]
        self.assertEqual(
            scene_item_command.item_states,
            [{**arrow_state, "_z_value": 0.0, "_selected": False}],
        )
        self.assertEqual(scene_item_command.item_ids, [scene_item.data(3)])

    def test_record_additions_includes_atom_annotations_in_atom_states(self) -> None:
        canvas = _make_canvas(
            atoms={1: Atom("N", 1.0, 2.0)},
            next_atom_id=2,
        )
        canvas.model.atom_annotations = {1: {"formal_charge": 1}}

        _recording_service(canvas).record_additions(
            before_next_atom_id=1,
            before_bond_count=0,
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
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, AddAtomsCommand)
        self.assertEqual(command.atom_coords_3d, {1: (1.0, 2.0, 3.0)})

    def test_record_additions_pushes_single_scene_item_command_when_only_scene_items_are_added(
        self,
    ) -> None:
        canvas = _make_canvas()
        context = attach_scene_render_context(canvas)
        scene_item = create_scene_item_from_state(
            context, {"kind": "note", "text": "label", "x": 2.0, "y": 4.0}
        )
        expected = scene_item.note_state()

        _recording_service(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            added_scene_items=[scene_item],
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, AddSceneItemsCommand)
        self.assertEqual(
            command.item_states, [{**expected, "_z_value": 0.0, "_selected": False}]
        )
        self.assertEqual(command.item_ids, [scene_item.data(3)])

    def test_record_additions_skips_push_when_nothing_was_added(self) -> None:
        canvas = _make_canvas()

        _recording_service(canvas).record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
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
        canvas = _make_canvas(bonds=[None, None, None, None, Bond(1, 2, order=2)])

        _recording_service(canvas).record_bond_update(
            bond_id=4,
            before_state=before_state,
            after_state=after_state,
        )

        canvas.push_command.assert_called_once()
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, UpdateBondCommand)
        self.assertEqual(command.bond_id, 4)
        self.assertEqual(command.before_state, before_state)
        self.assertEqual(command.after_state, after_state)

    def test_record_bond_update_skips_push_when_state_is_unchanged(self) -> None:
        canvas = _make_canvas()
        _recording_service(canvas).record_bond_update(
            bond_id=1,
            before_state={"order": 1},
            after_state={"order": 1},
        )
        canvas.push_command.assert_not_called()
