import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock

import chemvas.core.history as history_core
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
    SetSmilesInputCommand,
    UpdateAtomColorCommand,
    UpdateBondCommand,
    UpdateBondLengthCommand,
    consume_authoritative_history_failure_restore,
    restore_history_transaction_for_command,
)
from chemvas.domain.document import Atom
from chemvas.ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from chemvas.ui.history_commands import (
    AddSceneItemsCommand,
    ChangeAtomLabelCommand,
    DeleteSceneItemsCommand,
    MoveItemsCommand,
    UpdateSceneItemCommand,
)

from tests.runtime_services import canvas_runtime_services


class _RecorderCommand:
    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self.log = log

    def undo(self, canvas) -> None:
        self.log.append(f"undo:{self.name}")

    def redo(self, canvas) -> None:
        self.log.append(f"redo:{self.name}")


class _FakeItem:
    def __init__(self, scene_obj, raises: bool = False) -> None:
        self._scene_obj = scene_obj
        self._raises = raises

    def scene(self):
        if self._raises:
            raise RuntimeError("item deleted")
        return self._scene_obj


class _FakeRenderer:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def set_bond_length(self, length: float) -> None:
        self.canvas.calls.append(("set_bond_length", length))


class _FakeRingItem:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def setPolygon(self, polygon) -> None:
        self.canvas.calls.append(
            ("set_ring_polygon", [(point.x(), point.y()) for point in polygon])
        )


class _FakeCanvas:
    atom_coords_3d = property(atom_coords_3d_for, set_atom_coords_3d_for)
    last_smiles_input = property(last_smiles_input_for, set_last_smiles_input_for)

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.last_smiles_input = None
        self.model = SimpleNamespace(
            next_atom_id=0, atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]
        )
        self.atom_coords_3d = {}
        self.atom_items = {}
        self.atom_dots = {}
        self.bond_items = {}
        self.mark_registry = SimpleNamespace(get_for_atom=lambda _atom_id: [])
        self._scene_obj = object()
        self.renderer = _FakeRenderer(self)
        self.rotation_state = CanvasRotationState(
            projection_center_3d="before-center",
            projection_anchor_2d="before-anchor",
        )
        self.services = canvas_runtime_services(
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label
            ),
            canvas_atom_mutation_service=SimpleNamespace(
                remove_atom_only=self.remove_atom_only,
                restore_atom_from_state=self.restore_atom_from_state,
                apply_atom_color=self.apply_atom_color,
            ),
            canvas_bond_mutation_service=SimpleNamespace(
                restore_bond_from_state=self.restore_bond_from_state,
                remove_bond_by_id=self.remove_bond_by_id,
                trim_bonds_to_length=self.trim_bonds_to_length,
            ),
            hit_testing_service=SimpleNamespace(
                mark_spatial_index_dirty=self.mark_spatial_index_dirty
            ),
            canvas_ring_fill_scene_service=SimpleNamespace(
                update_ring_fills_for_atoms=self.update_ring_fills_for_atoms
            ),
            move_controller=SimpleNamespace(
                move_atoms=self.move_atoms,
                move_item=self.move_item,
                redraw_bonds_for_atoms=self.redraw_bonds_for_atoms,
            ),
            scene_item_controller=SimpleNamespace(
                apply_scene_item_state=self.apply_scene_item_state,
                create_scene_item_from_state=self.create_scene_item_from_state,
                restore_scene_item=self.restore_scene_item,
                remove_scene_item=self.remove_scene_item,
                restore_mark_from_state=lambda mark_state: self.calls.append(
                    ("restore_mark_from_state", dict(mark_state))
                ),
            ),
            selection_controller=SimpleNamespace(
                update_selection_outline=self.refresh_selection_outline
            ),
            structure_build_service=SimpleNamespace(
                render_model=self.record_rebuild_graphics
            ),
        )

    def scene(self):
        return self._scene_obj

    def move_atoms(
        self,
        atom_ids,
        dx,
        dy,
        bond_ids=None,
        redraw_bond_ids=None,
        update_selection=True,
    ) -> None:
        self.calls.append(
            (
                "move_atoms",
                set(atom_ids),
                dx,
                dy,
                bond_ids,
                redraw_bond_ids,
                update_selection,
            )
        )

    def move_item(self, item, dx, dy, update_selection=False) -> None:
        self.calls.append(("move_item", item, dx, dy, update_selection))

    def refresh_selection_outline(self) -> None:
        self.calls.append(("refresh_selection_outline",))

    def redraw_bonds_for_atoms(self, atom_ids) -> None:
        self.calls.append(("redraw_bonds_for_atoms", set(atom_ids)))

    def update_ring_fills_for_atoms(self, atom_ids) -> None:
        self.calls.append(("update_ring_fills_for_atoms", set(atom_ids)))

    def mark_spatial_index_dirty(self) -> None:
        self.calls.append(("mark_spatial_index_dirty",))

    def record_rebuild_graphics(self) -> None:
        self.calls.append(("rebuild_graphics",))

    def remove_atom_only(self, atom_id, remove_marks=True) -> None:
        self.calls.append(("remove_atom_for_history", atom_id, remove_marks))
        self.model.atoms.pop(atom_id, None)
        atom_coords_3d_for(self).pop(atom_id, None)

    def restore_atom_from_state(self, atom_id, state) -> None:
        self.calls.append(("restore_atom_from_state", atom_id, dict(state)))
        self.model.atoms[atom_id] = Atom(
            state.get("element", "C"),
            state.get("x", 0.0),
            state.get("y", 0.0),
        )

    def apply_atom_color(self, atom_id, color) -> None:
        self.calls.append(("apply_atom_color", atom_id, color))

    def apply_scene_item_state(self, item, state) -> None:
        self.calls.append(("apply_scene_item_state", item, dict(state)))

    def create_scene_item_from_state(self, state):
        item = {"created_from": dict(state)}
        self.calls.append(("create_scene_item_from_state", dict(state)))
        return item

    def restore_scene_item(self, item) -> None:
        self.calls.append(("restore_scene_item", item))

    def remove_scene_item(self, item) -> None:
        self.calls.append(("remove_scene_item", item))

    def add_or_update_atom_label(
        self,
        atom_id,
        element,
        clear_smiles=False,
        record=False,
        allow_merge=False,
        show_carbon=False,
    ) -> None:
        self.calls.append(
            (
                "add_or_update_atom_label",
                atom_id,
                element,
                clear_smiles,
                record,
                allow_merge,
                show_carbon,
            )
        )

    def remove_bond_by_id(self, bond_id) -> None:
        self.calls.append(("remove_bond_for_history", bond_id))

    def trim_bonds_to_length(self, previous_bond_count) -> None:
        self.calls.append(("trim_bonds_for_history", previous_bond_count))

    def restore_bond_from_state(self, bond_id, bond_state) -> None:
        self.calls.append(("restore_bond_from_state", bond_id, dict(bond_state)))

    def restore_mark_from_state(self, mark_state) -> None:
        controller = getattr(self.services, "scene_item_controller", None)
        if controller is not None and hasattr(controller, "restore_mark_from_state"):
            controller.restore_mark_from_state(mark_state)
            return
        self.calls.append(("restore_mark_from_state", dict(mark_state)))


class _FakeSceneItemController:
    def __init__(self, canvas: _FakeCanvas) -> None:
        self.canvas = canvas

    def apply_scene_item_state(self, item, state) -> None:
        self.canvas.calls.append(
            ("controller_apply_scene_item_state", item, dict(state))
        )

    def create_scene_item_from_state(self, state):
        item = {"controller_created_from": dict(state)}
        self.canvas.calls.append(
            ("controller_create_scene_item_from_state", dict(state))
        )
        return item

    def restore_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_restore_scene_item", item))

    def remove_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_remove_scene_item", item))

    def restore_mark_from_state(self, mark_state) -> None:
        self.canvas.calls.append(
            ("controller_restore_mark_from_state", dict(mark_state))
        )


class _MinimalCanvas(_FakeCanvas):
    def __init__(self) -> None:
        super().__init__()
        self.rotation_state = CanvasRotationState()


class _AtomicHistoryCanvas:
    def __init__(
        self,
        *,
        atoms: dict[int, dict] | None = None,
        next_atom_id: int = 0,
        coords_3d: dict[int, tuple[float, float, float]] | None = None,
        marks: list[dict] | None = None,
        bonds: dict[int, dict] | None = None,
        smiles_input: str | None = None,
        projection_center_3d: tuple[float, float, float] | None = None,
        projection_anchor_2d: tuple[float, float] | None = None,
    ) -> None:
        self.model = SimpleNamespace(
            atoms=deepcopy(atoms or {}),
            next_atom_id=next_atom_id,
        )
        self.coords_3d = dict(coords_3d or {})
        self.marks = deepcopy(marks or [])
        self.bonds = deepcopy(bonds or {})
        self.smiles_input = smiles_input
        self.projection_center_3d = projection_center_3d
        self.projection_anchor_2d = projection_anchor_2d
        self.toggle = True


class _AtomicRingItem:
    def __init__(self, name: str, polygon: list[tuple[float, float]]) -> None:
        self.name = name
        self.polygon = list(polygon)


def _atomic_canvas_snapshot(canvas: _AtomicHistoryCanvas) -> dict:
    return {
        "atoms": deepcopy(canvas.model.atoms),
        "next_atom_id": canvas.model.next_atom_id,
        "coords_3d": dict(canvas.coords_3d),
        "marks": deepcopy(canvas.marks),
        "bonds": deepcopy(canvas.bonds),
        "smiles_input": canvas.smiles_input,
        "projection_center_3d": canvas.projection_center_3d,
        "projection_anchor_2d": canvas.projection_anchor_2d,
        "toggle": canvas.toggle,
    }


class _StatefulHistoryPort:
    """Small stateful port that can raise after mutating one requested step."""

    def __init__(self) -> None:
        self._failure: tuple[str, object] | None = None

    def fail_once_after(self, operation: str, discriminator: object = None) -> None:
        self._failure = (operation, discriminator)

    def _raise_if_armed(self, operation: str, discriminator: object = None) -> None:
        if self._failure != (operation, discriminator):
            return
        self._failure = None
        raise RuntimeError(f"{operation} failed")

    def restore_projection_state_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        projection_center_3d,
        projection_anchor_2d,
    ) -> None:
        canvas.projection_center_3d = projection_center_3d
        canvas.projection_anchor_2d = projection_anchor_2d
        self._raise_if_armed("restore_projection")

    def set_ring_polygons_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        ring_items,
        polygons,
    ) -> None:
        del canvas
        for ring_item, polygon in zip(ring_items, polygons, strict=False):
            ring_item.polygon = list(polygon)
            self._raise_if_armed("set_ring_polygon", ring_item.name)

    def set_atom_positions_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        positions,
        *,
        update_selection=True,
        coords_3d=None,
    ) -> None:
        del update_selection
        for atom_id, (x, y) in positions.items():
            atom = canvas.model.atoms.get(atom_id)
            if atom is not None:
                atom["x"] = x
                atom["y"] = y
        if coords_3d is not None:
            canvas.coords_3d.update(coords_3d)
        self._raise_if_armed("set_positions")

    def remove_atom_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        atom_id: int,
        *,
        remove_marks: bool = True,
    ) -> None:
        canvas.model.atoms.pop(atom_id, None)
        canvas.coords_3d.pop(atom_id, None)
        if remove_marks:
            canvas.marks[:] = [
                mark for mark in canvas.marks if mark.get("atom_id") != atom_id
            ]
        self._raise_if_armed("remove_atom", atom_id)

    def restore_atom_from_state_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        atom_id: int,
        state: dict,
    ) -> None:
        canvas.model.atoms[atom_id] = deepcopy(state)
        self._raise_if_armed("restore_atom", atom_id)

    def restore_mark_from_state_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        mark_state: dict,
    ) -> dict:
        restored = deepcopy(mark_state)
        canvas.marks.append(restored)
        self._raise_if_armed("restore_mark", mark_state.get("atom_id"))
        return restored

    def set_last_smiles_input_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        value: str | None,
    ) -> None:
        canvas.smiles_input = value
        self._raise_if_armed("set_smiles", value)

    def restore_bond_from_state_for_history(
        self,
        canvas: _AtomicHistoryCanvas,
        bond_id: int,
        bond_state: dict,
    ) -> None:
        canvas.bonds[bond_id] = deepcopy(bond_state)
        self._raise_if_armed("restore_bond", bond_id)

    def remove_bond_for_history(
        self, canvas: _AtomicHistoryCanvas, bond_id: int
    ) -> None:
        canvas.bonds.pop(bond_id, None)
        self._raise_if_armed("remove_bond", bond_id)

    def trim_bonds_for_history(self, canvas: _AtomicHistoryCanvas, length: int) -> None:
        canvas.bonds = {
            bond_id: state
            for bond_id, state in canvas.bonds.items()
            if bond_id < length
        }
        self._raise_if_armed("trim_bonds", length)


class _ToggleStateCommand(HistoryCommand):
    def undo(self, canvas: _AtomicHistoryCanvas) -> None:
        canvas.toggle = False

    def redo(self, canvas: _AtomicHistoryCanvas) -> None:
        canvas.toggle = True


class HistoryCommandTest(unittest.TestCase):
    def test_malformed_restore_port_result_cannot_replace_primary_error(self) -> None:
        class HostileResult:
            @property
            def errors(self):
                raise KeyboardInterrupt("hostile errors getter")

        class Port:
            def __init__(self, result: object) -> None:
                self.result = result

            def restore_history_transaction_for_history(self, canvas, snapshot):
                del canvas, snapshot
                return self.result

        for malformed in (True, HostileResult()):
            with self.subTest(result=type(malformed).__name__):
                primary = ValueError("original command failure")
                with mock.patch(
                    "chemvas.core.history._history_canvas_port",
                    return_value=Port(malformed),
                ):
                    result = restore_history_transaction_for_command(
                        object(),
                        object(),
                        primary,
                    )

                self.assertFalse(result.authoritative)
                self.assertFalse(result.fallback_to_inverse)
                self.assertEqual(len(result.errors), 1)
                self.assertIsInstance(result.errors[0], TypeError)
                self.assertTrue(
                    any(
                        "History rollback also encountered TypeError" in note
                        for note in primary.__notes__
                    )
                )

    def test_history_command_base_methods_raise_not_implemented(self) -> None:
        command = HistoryCommand()

        with self.assertRaises(NotImplementedError):
            command.undo(None)
        with self.assertRaises(NotImplementedError):
            command.redo(None)

    def test_composite_command_undo_redo_order(self) -> None:
        log: list[str] = []
        command = CompositeCommand(
            [
                _RecorderCommand("first", log),
                _RecorderCommand("second", log),
                _RecorderCommand("third", log),
            ]
        )

        command.undo(None)
        command.redo(None)

        self.assertEqual(
            log,
            [
                "undo:third",
                "undo:second",
                "undo:first",
                "redo:first",
                "redo:second",
                "redo:third",
            ],
        )

    def test_composite_command_rolls_back_partially_applied_undo(self) -> None:
        log: list[str] = []

        class _FailingCommand(_RecorderCommand):
            def undo(self, canvas) -> None:
                self.log.append(f"undo:{self.name}")
                raise RuntimeError("undo failed")

        command = CompositeCommand(
            [
                _RecorderCommand("first", log),
                _FailingCommand("second", log),
                _RecorderCommand("third", log),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "undo failed"):
            command.undo(None)

        # "third" was undone before "second" failed, so it must be re-applied;
        # "first" never ran and must stay untouched.
        self.assertEqual(log, ["undo:third", "undo:second", "redo:third"])

    def test_composite_command_rolls_back_partially_applied_redo(self) -> None:
        log: list[str] = []

        class _FailingCommand(_RecorderCommand):
            def redo(self, canvas) -> None:
                self.log.append(f"redo:{self.name}")
                raise RuntimeError("redo failed")

        command = CompositeCommand(
            [
                _RecorderCommand("first", log),
                _FailingCommand("second", log),
                _RecorderCommand("third", log),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "redo failed"):
            command.redo(None)

        self.assertEqual(log, ["redo:first", "redo:second", "undo:first"])

    def test_lifecycle_composite_uses_inverse_fallback_for_capture_only_port(
        self,
    ) -> None:
        class _CaptureOnlyPort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

        class _FailingChild(HistoryCommand):
            def undo(self, canvas) -> None:
                del canvas

            def redo(self, canvas) -> None:
                del canvas
                raise RuntimeError("later child failed")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        before = _atomic_canvas_snapshot(canvas)
        port = _CaptureOnlyPort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _FailingChild(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(RuntimeError, "later child failed"):
                command.redo(canvas)

        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertEqual(port.capture_calls, 0)

    def test_lifecycle_composite_falls_back_if_restore_hook_disappears(self) -> None:
        class _VanishingRestorePort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0
                self.restore_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                del canvas, snapshot
                self.restore_calls += 1

        class _RemoveRestoreAndFail(HistoryCommand):
            def __init__(self, port) -> None:
                self.port = port

            def undo(self, canvas) -> None:
                del canvas

            def redo(self, canvas) -> None:
                del canvas
                self.port.restore_history_transaction_for_history = None
                raise RuntimeError("restore hook disappeared")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        before = _atomic_canvas_snapshot(canvas)
        port = _VanishingRestorePort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _RemoveRestoreAndFail(port),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(RuntimeError, "restore hook disappeared"):
                command.redo(canvas)

        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertEqual(port.capture_calls, 1)
        self.assertEqual(port.restore_calls, 0)

    def test_lifecycle_composite_inverse_fallback_repairs_deferred_failing_child(
        self,
    ) -> None:
        class _RestoreDisappearsDuringBondPort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0
                self.remove_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                del canvas, snapshot

            def restore_bond_from_state_for_history(
                self,
                canvas,
                bond_id: int,
                bond_state: dict,
            ) -> None:
                super().restore_bond_from_state_for_history(canvas, bond_id, bond_state)
                self.restore_history_transaction_for_history = None
                raise KeyboardInterrupt("bond restore interrupted after mutation")

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                self.remove_calls += 1
                super().remove_bond_for_history(canvas, bond_id)

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        port = _RestoreDisappearsDuringBondPort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                )
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaises(KeyboardInterrupt) as caught:
                command.redo(canvas)

        self.assertEqual(
            str(caught.exception), "bond restore interrupted after mutation"
        )
        self.assertEqual(canvas.bonds, {})
        self.assertEqual(canvas.smiles_input, "before")
        self.assertEqual(port.capture_calls, 1)
        self.assertEqual(port.remove_calls, 1)

    def test_lifecycle_composite_falls_back_if_restore_fails_before_authoritative_pass(
        self,
    ) -> None:
        class _PreAuthoritativeFailurePort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0
                self.restore_calls = 0
                self.remove_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(
                self,
                canvas,
                snapshot,
            ) -> HistoryTransactionRestoreResult:
                del canvas, snapshot
                self.restore_calls += 1
                return HistoryTransactionRestoreResult(
                    authoritative=False,
                    fallback_to_inverse=True,
                    errors=(RuntimeError("restore failed before absolute pass"),),
                )

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                self.remove_calls += 1
                super().remove_bond_for_history(canvas, bond_id)

        class _FailingChild(HistoryCommand):
            def undo(self, canvas) -> None:
                del canvas

            def redo(self, canvas) -> None:
                del canvas
                raise ValueError("later child failed")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        before = _atomic_canvas_snapshot(canvas)
        port = _PreAuthoritativeFailurePort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _FailingChild(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(ValueError, "later child failed") as caught:
                command.redo(canvas)

        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertEqual(port.restore_calls, 1)
        self.assertEqual(port.remove_calls, 1)
        self.assertTrue(
            any(
                "restore failed before absolute pass" in note
                for note in caught.exception.__notes__
            )
        )

    def test_lifecycle_composite_does_not_inverse_if_restore_hook_mutates_then_raises(
        self,
    ) -> None:
        class _MutateThenRaiseRestorePort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.restore_calls = 0
                self.remove_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                self.restore_calls += 1
                canvas.smiles_input = snapshot["smiles_input"]
                raise RuntimeError("restore hook mutated then raised")

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                self.remove_calls += 1
                super().remove_bond_for_history(canvas, bond_id)

        class _FailingChild(HistoryCommand):
            def undo(self, canvas) -> None:
                del canvas

            def redo(self, canvas) -> None:
                del canvas
                raise ValueError("later child failed")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        port = _MutateThenRaiseRestorePort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _FailingChild(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(ValueError, "later child failed") as caught:
                command.redo(canvas)

        self.assertEqual(canvas.smiles_input, "before")
        self.assertIn(0, canvas.bonds)
        self.assertEqual(port.restore_calls, 1)
        self.assertEqual(port.remove_calls, 0)
        self.assertTrue(
            any(
                "restore hook mutated then raised" in note
                for note in caught.exception.__notes__
            )
        )

    def test_lifecycle_composite_does_not_inverse_after_authoritative_restore_with_secondary_error(
        self,
    ) -> None:
        class _AuthoritativeRestorePort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.remove_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(
                self,
                canvas,
                snapshot,
            ) -> HistoryTransactionRestoreResult:
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]
                return HistoryTransactionRestoreResult(
                    authoritative=True,
                    errors=(RuntimeError("observer failed after absolute pass"),),
                )

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                self.remove_calls += 1
                super().remove_bond_for_history(canvas, bond_id)

        class _FailingChild(HistoryCommand):
            def undo(self, canvas) -> None:
                del canvas

            def redo(self, canvas) -> None:
                del canvas
                raise ValueError("later child failed")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        before = _atomic_canvas_snapshot(canvas)
        port = _AuthoritativeRestorePort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _FailingChild(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(ValueError, "later child failed") as caught:
                command.redo(canvas)

        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertEqual(port.remove_calls, 0)
        self.assertTrue(
            any(
                "observer failed after absolute pass" in note
                for note in caught.exception.__notes__
            )
        )

    def test_lifecycle_composite_does_not_inverse_after_partial_absolute_restore(
        self,
    ) -> None:
        class _PartialRestorePort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.remove_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(
                self,
                canvas,
                snapshot,
            ) -> HistoryTransactionRestoreResult:
                # Simulate a full best-effort pass that restored one absolute
                # field but hit a persistent critical setter on another.
                canvas.smiles_input = snapshot["smiles_input"]
                return HistoryTransactionRestoreResult(
                    authoritative=False,
                    fallback_to_inverse=False,
                    errors=(RuntimeError("persistent model setter failure"),),
                )

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                self.remove_calls += 1
                super().remove_bond_for_history(canvas, bond_id)

        class _FailingChild(HistoryCommand):
            def undo(self, canvas) -> None:
                del canvas

            def redo(self, canvas) -> None:
                del canvas
                raise ValueError("later child failed")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        port = _PartialRestorePort()
        command = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _FailingChild(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(ValueError, "later child failed") as caught:
                command.redo(canvas)

        self.assertEqual(canvas.smiles_input, "before")
        self.assertIn(0, canvas.bonds)
        self.assertEqual(port.remove_calls, 0)
        self.assertTrue(
            any(
                "persistent model setter failure" in note
                for note in caught.exception.__notes__
            )
        )

    def test_history_canvas_restore_marks_persistent_renderer_setter_as_partial(
        self,
    ) -> None:
        from chemvas.ui.history_canvas_access import (
            _capture_renderer_style_access,
            _HistoryCanvasTransactionSnapshot,
            restore_history_transaction_for_history,
        )

        class _PersistentRenderer:
            def __init__(self) -> None:
                self._style = "before"
                self.setter_calls = 0

            @property
            def style(self):
                return self._style

            @style.setter
            def style(self, value) -> None:
                del value
                self.setter_calls += 1
                raise RuntimeError("persistent renderer style setter failure")

        class _CompletedCanvasSnapshot:
            def __init__(self) -> None:
                self.restore_calls = 0

            def restore_with_result(self) -> HistoryTransactionRestoreResult:
                self.restore_calls += 1
                return HistoryTransactionRestoreResult(authoritative=True)

        canvas_snapshot = _CompletedCanvasSnapshot()
        renderer = _PersistentRenderer()
        renderer_style = _capture_renderer_style_access(renderer)
        self.assertIsNotNone(renderer_style)
        renderer._style = "mutated"
        snapshot = _HistoryCanvasTransactionSnapshot(
            canvas_snapshot=canvas_snapshot,
            renderer_style=renderer_style,
        )

        result = restore_history_transaction_for_history(None, snapshot)

        self.assertFalse(result.authoritative)
        self.assertFalse(result.fallback_to_inverse)
        self.assertEqual(canvas_snapshot.restore_calls, 1)
        self.assertEqual(renderer.setter_calls, 1)
        self.assertTrue(
            any(
                "persistent renderer style setter failure" in str(error)
                for error in result.errors
            )
        )

    def test_history_canvas_restore_keeps_history_notification_failure_secondary(
        self,
    ) -> None:
        from chemvas.ui.history_canvas_access import (
            capture_history_transaction_for_history,
            restore_history_transaction_for_history,
        )

        class _FailingObserverHistory:
            def __init__(self) -> None:
                self.state = SimpleNamespace(history=[], redo_stack=[])

            def notify_change(self) -> None:
                raise RuntimeError("history observer failure")

        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={},
                bonds=[],
                next_atom_id=0,
                atom_annotations={},
            ),
            renderer=SimpleNamespace(style=object()),
            scene=lambda: None,
        )
        snapshot = capture_history_transaction_for_history(
            canvas,
            history_service=_FailingObserverHistory(),
        )

        result = restore_history_transaction_for_history(canvas, snapshot)

        self.assertTrue(result.authoritative)
        self.assertFalse(result.fallback_to_inverse)
        self.assertTrue(
            any("history observer failure" in str(error) for error in result.errors)
        )

    def test_value_commands_compensate_mutate_then_baseexception(self) -> None:
        class _InterruptingPort:
            def __init__(self) -> None:
                self.position_calls = 0
                self.ring_calls = 0
                self.length_calls = 0

            def set_atom_positions_for_history(
                self,
                canvas,
                positions,
                **_kwargs,
            ) -> None:
                self.position_calls += 1
                canvas.position = next(iter(positions.values()))
                if self.position_calls == 1:
                    raise KeyboardInterrupt("position interrupted")

            def set_ring_polygons_for_history(
                self,
                canvas,
                ring_items,
                polygons,
            ) -> None:
                del canvas
                self.ring_calls += 1
                ring_items[0].polygon = list(polygons[0])
                if self.ring_calls == 1:
                    raise KeyboardInterrupt("ring interrupted")

            def restore_bond_length_for_history(self, canvas, length) -> None:
                self.length_calls += 1
                canvas.bond_length = length
                if self.length_calls == 1:
                    raise KeyboardInterrupt("length interrupted")

        port = _InterruptingPort()
        position_canvas = SimpleNamespace(position=(1.0, 2.0))
        position_command = SetAtomPositionsCommand(
            before_positions={1: (1.0, 2.0)},
            after_positions={1: (9.0, 10.0)},
        )
        ring = _AtomicRingItem("ring", [(0.0, 0.0)])
        ring_command = SetRingPolygonsCommand(
            [ring],
            [[(0.0, 0.0)]],
            [[(5.0, 6.0)]],
        )
        length_canvas = SimpleNamespace(bond_length=20.0)
        length_command = UpdateBondLengthCommand(20.0, 30.0)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(KeyboardInterrupt, "position interrupted"):
                position_command.redo(position_canvas)
            with self.assertRaisesRegex(KeyboardInterrupt, "ring interrupted"):
                ring_command.redo(SimpleNamespace())
            with self.assertRaisesRegex(KeyboardInterrupt, "length interrupted"):
                length_command.redo(length_canvas)

        self.assertEqual(position_canvas.position, (1.0, 2.0))
        self.assertEqual(ring.polygon, [(0.0, 0.0)])
        self.assertEqual(length_canvas.bond_length, 20.0)

    def test_inverse_compensation_keeps_secondary_control_flow_error_as_note(
        self,
    ) -> None:
        class _InterruptingColorPort:
            def __init__(self) -> None:
                self.calls = 0

            def apply_atom_color_for_history(
                self, canvas, atom_id: int, color: str
            ) -> None:
                del atom_id
                self.calls += 1
                canvas.color = color
                if self.calls == 1:
                    raise KeyboardInterrupt("primary color interruption")
                raise SystemExit("color compensation terminated")

        canvas = SimpleNamespace(color="#111111")
        port = _InterruptingColorPort()
        command = UpdateAtomColorCommand(
            atom_id=1,
            before_color="#111111",
            after_color="#222222",
        )
        original_error: KeyboardInterrupt | None = None

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaises(KeyboardInterrupt) as caught:
                command.redo(canvas)
            original_error = caught.exception

        self.assertEqual(canvas.color, "#111111")
        self.assertEqual(port.calls, 2)
        self.assertIsNotNone(original_error)
        self.assertTrue(
            any(
                "SystemExit: color compensation terminated" in note
                for note in original_error.__notes__
            )
        )

    def test_add_atoms_command_compensates_failed_current_atom_in_both_directions(
        self,
    ) -> None:
        canvas = _AtomicHistoryCanvas(next_atom_id=1, smiles_input="before")
        port = _StatefulHistoryPort()
        command = AddAtomsCommand(
            atom_states={
                1: {"element": "C", "x": 1.0, "y": 2.0},
                2: {"element": "N", "x": 3.0, "y": 4.0},
            },
            atom_coords_3d={1: (1.0, 2.0, 3.0), 2: (3.0, 4.0, 5.0)},
            before_next_atom_id=1,
            after_next_atom_id=3,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            before = _atomic_canvas_snapshot(canvas)
            port.fail_once_after("restore_atom", 2)
            with self.assertRaisesRegex(RuntimeError, "restore_atom failed"):
                command.redo(canvas)
            self.assertEqual(_atomic_canvas_snapshot(canvas), before)

            command.redo(canvas)
            after = _atomic_canvas_snapshot(canvas)
            port.fail_once_after("remove_atom", 2)
            with self.assertRaisesRegex(RuntimeError, "remove_atom failed"):
                command.undo(canvas)
            self.assertEqual(_atomic_canvas_snapshot(canvas), after)

    def test_delete_atoms_command_compensates_atoms_marks_coords_and_projection(
        self,
    ) -> None:
        atom_states = {
            1: {"element": "C", "x": 1.0, "y": 2.0},
            2: {"element": "O", "x": 3.0, "y": 4.0},
        }
        mark_states = [
            {"kind": "plus", "atom_id": 1},
            {"kind": "minus", "atom_id": 2},
        ]
        canvas = _AtomicHistoryCanvas(
            atoms=atom_states,
            next_atom_id=3,
            coords_3d={1: (1.0, 2.0, 3.0), 2: (3.0, 4.0, 5.0)},
            marks=mark_states,
            smiles_input="before",
            projection_center_3d=(1.0, 2.0, 3.0),
            projection_anchor_2d=(4.0, 5.0),
        )
        port = _StatefulHistoryPort()
        command = DeleteAtomsCommand(
            atom_states=atom_states,
            mark_states=mark_states,
            atom_coords_3d={1: (1.0, 2.0, 3.0), 2: (3.0, 4.0, 5.0)},
            before_next_atom_id=3,
            after_next_atom_id=1,
            before_smiles_input="before",
            after_smiles_input="after",
            restore_projection_state=True,
            before_projection_center_3d=(1.0, 2.0, 3.0),
            after_projection_center_3d=None,
            before_projection_anchor_2d=(4.0, 5.0),
            after_projection_anchor_2d=None,
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            before = _atomic_canvas_snapshot(canvas)
            port.fail_once_after("remove_atom", 2)
            with self.assertRaisesRegex(RuntimeError, "remove_atom failed"):
                command.redo(canvas)
            self.assertEqual(_atomic_canvas_snapshot(canvas), before)

            command.redo(canvas)
            after = _atomic_canvas_snapshot(canvas)
            port.fail_once_after("restore_mark", 2)
            with self.assertRaisesRegex(RuntimeError, "restore_mark failed"):
                command.undo(canvas)
            self.assertEqual(_atomic_canvas_snapshot(canvas), after)

    def test_set_atom_positions_command_compensates_projection_and_positions(
        self,
    ) -> None:
        canvas = _AtomicHistoryCanvas(
            atoms={1: {"element": "C", "x": 1.0, "y": 2.0}},
            coords_3d={1: (1.0, 2.0, 3.0)},
            projection_center_3d=(1.0, 2.0, 3.0),
            projection_anchor_2d=(4.0, 5.0),
        )
        port = _StatefulHistoryPort()
        command = SetAtomPositionsCommand(
            before_positions={1: (1.0, 2.0)},
            after_positions={1: (10.0, 20.0)},
            before_coords_3d={1: (1.0, 2.0, 3.0)},
            after_coords_3d={1: (10.0, 20.0, 30.0)},
            restore_projection_state=True,
            before_projection_center_3d=(1.0, 2.0, 3.0),
            after_projection_center_3d=(10.0, 20.0, 30.0),
            before_projection_anchor_2d=(4.0, 5.0),
            after_projection_anchor_2d=(40.0, 50.0),
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            before = _atomic_canvas_snapshot(canvas)
            port.fail_once_after("set_positions")
            with self.assertRaisesRegex(RuntimeError, "set_positions failed"):
                command.redo(canvas)
            self.assertEqual(_atomic_canvas_snapshot(canvas), before)

    def test_set_ring_polygons_command_compensates_failed_current_ring(self) -> None:
        first = _AtomicRingItem("first", [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)])
        second = _AtomicRingItem("second", [(2.0, 2.0), (3.0, 2.0), (2.0, 3.0)])
        before = [list(first.polygon), list(second.polygon)]
        after = [
            [(10.0, 10.0), (11.0, 10.0), (10.0, 11.0)],
            [(12.0, 12.0), (13.0, 12.0), (12.0, 13.0)],
        ]
        canvas = _AtomicHistoryCanvas()
        port = _StatefulHistoryPort()
        command = SetRingPolygonsCommand([first, second], before, after)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_once_after("set_ring_polygon", "second")
            with self.assertRaisesRegex(RuntimeError, "set_ring_polygon failed"):
                command.redo(canvas)

        self.assertEqual([first.polygon, second.polygon], before)

    def test_position_and_ring_commands_preserve_primary_during_persistent_legacy_compensation(
        self,
    ) -> None:
        for command_kind in ("positions", "rings"):
            for primary_type in (KeyboardInterrupt, SystemExit):
                with self.subTest(command=command_kind, primary=primary_type.__name__):
                    primary = primary_type(f"{command_kind} apply interrupted")
                    secondary = RuntimeError(f"{command_kind} compensation failed")

                    if command_kind == "positions":
                        canvas = _AtomicHistoryCanvas(
                            atoms={1: {"element": "C", "x": 1.0, "y": 2.0}}
                        )

                        class Port(_StatefulHistoryPort):
                            def __init__(
                                self,
                                primary_error: BaseException,
                                secondary_error: BaseException,
                            ) -> None:
                                super().__init__()
                                self.calls = 0
                                self.primary = primary_error
                                self.secondary = secondary_error

                            def set_atom_positions_for_history(
                                self,
                                target_canvas,
                                positions,
                                *,
                                update_selection=True,
                                coords_3d=None,
                            ) -> None:
                                del update_selection, coords_3d
                                for atom_id, (x, y) in positions.items():
                                    target_canvas.model.atoms[atom_id]["x"] = x
                                    target_canvas.model.atoms[atom_id]["y"] = y
                                self.calls += 1
                                raise (
                                    self.primary if self.calls == 1 else self.secondary
                                )

                        port = Port(primary, secondary)
                        command = SetAtomPositionsCommand(
                            {1: (1.0, 2.0)},
                            {1: (10.0, 20.0)},
                        )
                    else:
                        canvas = _AtomicHistoryCanvas()
                        rings = [
                            _AtomicRingItem("first", [(0.0, 0.0)]),
                            _AtomicRingItem("second", [(1.0, 1.0)]),
                        ]

                        class Port(_StatefulHistoryPort):
                            def __init__(
                                self,
                                primary_error: BaseException,
                                secondary_error: BaseException,
                            ) -> None:
                                super().__init__()
                                self.calls = 0
                                self.primary = primary_error
                                self.secondary = secondary_error

                            def set_ring_polygons_for_history(
                                self,
                                _canvas,
                                ring_items,
                                polygons,
                            ) -> None:
                                for ring_item, polygon in zip(
                                    ring_items,
                                    polygons,
                                    strict=False,
                                ):
                                    ring_item.polygon = list(polygon)
                                self.calls += 1
                                raise (
                                    self.primary if self.calls == 1 else self.secondary
                                )

                        port = Port(primary, secondary)
                        command = SetRingPolygonsCommand(
                            rings,
                            [[(0.0, 0.0)], [(1.0, 1.0)]],
                            [[(10.0, 10.0)], [(20.0, 20.0)]],
                        )

                    with mock.patch(
                        "chemvas.core.history._history_canvas_port",
                        return_value=port,
                    ):
                        with self.assertRaises(primary_type) as caught:
                            command.redo(canvas)

                    self.assertIs(caught.exception, primary)
                    self.assertGreaterEqual(port.calls, 2)
                    self.assertTrue(
                        any(
                            str(secondary) in note
                            for note in getattr(primary, "__notes__", [])
                        )
                    )

    def test_bond_length_command_compensates_failed_current_composite_child(
        self,
    ) -> None:
        class _FailingLengthPort:
            def __init__(self) -> None:
                self.fail_next = False

            def restore_bond_length_for_history(self, canvas, length: float) -> None:
                canvas.bond_length = length
                if self.fail_next:
                    self.fail_next = False
                    raise RuntimeError("graphics rebuild failed")

        canvas = SimpleNamespace(bond_length=24.0, toggle=True)
        port = _FailingLengthPort()
        command = CompositeCommand(
            [
                UpdateBondLengthCommand(before_length=18.0, after_length=24.0),
                _ToggleStateCommand(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_next = True
            with self.assertRaisesRegex(RuntimeError, "graphics rebuild failed"):
                command.undo(canvas)
            self.assertEqual((canvas.bond_length, canvas.toggle), (24.0, True))

            command.undo(canvas)
            self.assertEqual((canvas.bond_length, canvas.toggle), (18.0, False))

            port.fail_next = True
            with self.assertRaisesRegex(RuntimeError, "graphics rebuild failed"):
                command.redo(canvas)
            self.assertEqual((canvas.bond_length, canvas.toggle), (18.0, False))

    def test_bond_length_composite_owns_one_outer_transaction_per_direction(
        self,
    ) -> None:
        class _SnapshotLengthPort:
            def __init__(self) -> None:
                self.capture_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return canvas.bond_length

            def restore_history_transaction_for_history(
                self,
                canvas,
                snapshot,
            ) -> HistoryTransactionRestoreResult:
                canvas.bond_length = snapshot
                return HistoryTransactionRestoreResult(authoritative=True)

            def restore_bond_length_for_history(self, canvas, length: float) -> None:
                canvas.bond_length = length

        canvas = SimpleNamespace(bond_length=18.0, toggle=False)
        port = _SnapshotLengthPort()
        command = CompositeCommand(
            [
                UpdateBondLengthCommand(before_length=18.0, after_length=24.0),
                _ToggleStateCommand(),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            command.redo(canvas)
            command.undo(canvas)

        self.assertEqual((canvas.bond_length, canvas.toggle), (18.0, False))
        self.assertEqual(port.capture_calls, 2)

    def test_move_atoms_command_restores_absolute_snapshot_after_partial_move(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms[2] = Atom("N", 10.0, 20.0)
        canvas.atom_coords_3d = {
            1: (0.0, 0.0, 1.0),
            2: (10.0, 20.0, 2.0),
        }
        before_positions = {
            atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
        }
        before_coords_3d = dict(canvas.atom_coords_3d)

        def partially_move_first_atom(
            target_canvas,
            atom_ids,
            dx,
            dy,
            **_kwargs,
        ) -> None:
            atom_id = min(atom_ids)
            atom = target_canvas.model.atoms[atom_id]
            atom.x += dx
            atom.y += dy
            x, y, z = target_canvas.atom_coords_3d[atom_id]
            target_canvas.atom_coords_3d[atom_id] = (x + dx, y + dy, z)
            raise RuntimeError("partial move failed")

        command = MoveAtomsCommand({1, 2}, 5.0, 7.0)
        with mock.patch(
            "chemvas.ui.history_canvas_access.move_atoms_for",
            side_effect=partially_move_first_atom,
        ):
            with self.assertRaisesRegex(RuntimeError, "partial move failed"):
                command.redo(canvas)

        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            before_positions,
        )
        self.assertEqual(canvas.atom_coords_3d, before_coords_3d)

    def test_move_atoms_command_restores_absolute_snapshot_after_baseexception(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms[2] = Atom("N", 10.0, 20.0)
        canvas.atom_coords_3d = {
            1: (0.0, 0.0, 1.0),
            2: (10.0, 20.0, 2.0),
        }
        before_positions = {
            atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
        }
        before_coords_3d = dict(canvas.atom_coords_3d)

        def interrupt_after_first_atom(
            target_canvas,
            atom_ids,
            dx,
            dy,
            **_kwargs,
        ) -> None:
            atom_id = min(atom_ids)
            atom = target_canvas.model.atoms[atom_id]
            atom.x += dx
            atom.y += dy
            x, y, z = target_canvas.atom_coords_3d[atom_id]
            target_canvas.atom_coords_3d[atom_id] = (x + dx, y + dy, z)
            raise KeyboardInterrupt("partial move interrupted")

        command = MoveAtomsCommand({1, 2}, 5.0, 7.0)
        with mock.patch(
            "chemvas.ui.history_canvas_access.move_atoms_for",
            side_effect=interrupt_after_first_atom,
        ):
            with self.assertRaisesRegex(KeyboardInterrupt, "partial move interrupted"):
                command.redo(canvas)

        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            before_positions,
        )
        self.assertEqual(canvas.atom_coords_3d, before_coords_3d)

    def test_bond_commands_compensate_when_smiles_update_fails(self) -> None:
        before_state = {"a": 1, "b": 2, "order": 1}
        after_state = {"a": 1, "b": 2, "order": 2}
        cases = [
            (
                "add",
                AddBondCommand(0, after_state, 0, "before", "after"),
                {},
            ),
            (
                "delete",
                DeleteBondCommand(0, before_state, "before", "after"),
                {0: before_state},
            ),
            (
                "update",
                UpdateBondCommand(0, before_state, after_state, "before", "after"),
                {0: before_state},
            ),
        ]

        for name, command, bonds in cases:
            with self.subTest(command=name):
                canvas = _AtomicHistoryCanvas(bonds=bonds, smiles_input="before")
                port = _StatefulHistoryPort()
                with mock.patch(
                    "chemvas.core.history._history_canvas_port", return_value=port
                ):
                    before = _atomic_canvas_snapshot(canvas)
                    port.fail_once_after("set_smiles", "after")
                    with self.assertRaisesRegex(RuntimeError, "set_smiles failed"):
                        command.redo(canvas)
                    self.assertEqual(_atomic_canvas_snapshot(canvas), before)

                    command.redo(canvas)
                    after = _atomic_canvas_snapshot(canvas)
                    port.fail_once_after("set_smiles", "before")
                    with self.assertRaisesRegex(RuntimeError, "set_smiles failed"):
                        command.undo(canvas)
                    self.assertEqual(_atomic_canvas_snapshot(canvas), after)

    def test_history_service_preserves_failed_exact_composite_and_stack_identity(
        self,
    ) -> None:
        class _AuthoritativePort(_StatefulHistoryPort):
            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                canvas.model.atoms = deepcopy(snapshot["atoms"])
                canvas.model.next_atom_id = snapshot["next_atom_id"]
                canvas.coords_3d = dict(snapshot["coords_3d"])
                canvas.marks = deepcopy(snapshot["marks"])
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]
                canvas.projection_center_3d = snapshot["projection_center_3d"]
                canvas.projection_anchor_2d = snapshot["projection_anchor_2d"]
                canvas.toggle = snapshot["toggle"]

        atom_states = {
            1: {"element": "C", "x": 1.0, "y": 2.0},
            2: {"element": "N", "x": 3.0, "y": 4.0},
        }
        canvas = _AtomicHistoryCanvas(
            atoms=atom_states,
            next_atom_id=3,
            smiles_input="after",
        )
        port = _AuthoritativePort()
        add_atoms = AddAtomsCommand(
            atom_states=atom_states,
            before_next_atom_id=1,
            after_next_atom_id=3,
            before_smiles_input="before",
            after_smiles_input="after",
        )
        composite = CompositeCommand([add_atoms, _ToggleStateCommand()])
        stale_redo = _RecorderCommand("stale", [])
        state = CanvasHistoryState(history=[composite], redo_stack=[stale_redo])
        history = state.history
        redo_stack = state.redo_stack
        service = CanvasHistoryService(canvas, state)
        before = _atomic_canvas_snapshot(canvas)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_once_after("remove_atom", 2)
            with self.assertRaisesRegex(RuntimeError, "remove_atom failed"):
                service.undo()

        # The exact composite restored the canvas authoritatively, so both
        # stacks remain the same retryable objects with the same commands.
        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(state.history, [composite])
        self.assertIs(state.history[0], composite)
        self.assertEqual(state.redo_stack, [stale_redo])
        self.assertIs(state.redo_stack[0], stale_redo)

    def test_history_service_push_reasserts_committed_observer_authority(self) -> None:
        before = _RecorderCommand("before", [])
        stale_redo = _RecorderCommand("stale", [])
        command = _RecorderCommand("commit", [])
        state = CanvasHistoryState(
            history=[before],
            redo_stack=[stale_redo],
        )
        history = state.history
        redo_stack = state.redo_stack
        service = CanvasHistoryService(SimpleNamespace(), state)
        callback_calls = 0

        def corrupt_every_history_root() -> None:
            nonlocal callback_calls
            callback_calls += 1
            state.history = [_RecorderCommand("corrupt-history", [])]
            state.redo_stack = [_RecorderCommand("corrupt-redo", [])]
            state.enabled = False
            state.limit = 0
            service.state = CanvasHistoryState(
                history=[_RecorderCommand("replacement-history", [])],
                redo_stack=[_RecorderCommand("replacement-redo", [])],
                enabled=False,
                limit=0,
            )

        state.change_callback = corrupt_every_history_root

        committed = service.push(command)

        self.assertTrue(committed)
        self.assertEqual(callback_calls, 1)
        self.assertIs(service.state, state)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(state.history, [before, command])
        self.assertEqual(state.redo_stack, [])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 100)

    def test_history_service_push_reports_disabled_noop(self) -> None:
        callback_calls = 0

        def count_callback() -> None:
            nonlocal callback_calls
            callback_calls += 1

        command = _RecorderCommand("disabled", [])
        state = CanvasHistoryState(
            history=[],
            redo_stack=[_RecorderCommand("redo", [])],
            enabled=False,
            change_callback=count_callback,
        )
        service = CanvasHistoryService(SimpleNamespace(), state)

        committed = service.push(command)

        self.assertFalse(committed)
        self.assertEqual(state.history, [])
        self.assertEqual(len(state.redo_stack), 1)
        self.assertEqual(callback_calls, 0)

    def test_history_publication_rejects_cross_policy_reader_poisoning(self) -> None:
        class CrossPolicyState:
            def __init__(self) -> None:
                self.history: list[object] = []
                self.redo_stack: list[object] = []
                self.enabled = True
                self._limit = 100
                self.poison_enabled = False
                self.change_callback = None

            @property
            def limit(self) -> int:
                if self.poison_enabled:
                    self.enabled = False
                return self._limit

            @limit.setter
            def limit(self, value: int) -> None:
                self._limit = value

        state = CrossPolicyState()
        service = CanvasHistoryService(SimpleNamespace(), state)  # type: ignore[arg-type]
        state.change_callback = lambda: setattr(state, "poison_enabled", True)

        with self.assertRaises(BaseExceptionGroup):
            service.notify_change()

        # A persistent reader can keep the policy non-authoritative, but the
        # publication must never return success while accepting that drift.
        self.assertFalse(state.enabled)

    def test_history_failure_authority_does_not_fail_open_when_error_rejects_marker(
        self,
    ) -> None:
        class SelectiveMarkerError(SystemExit):
            marker_writes = 0

            def __setattr__(self, name: str, value: object) -> None:
                if name.startswith("_chemvas_"):
                    type(self).marker_writes += 1
                    raise KeyboardInterrupt("exception rejected recovery marker")
                super().__setattr__(name, value)

        class ExactPort:
            @staticmethod
            def restore_history_transaction_for_history(
                _canvas: object,
                _snapshot: object,
            ) -> HistoryTransactionRestoreResult:
                return HistoryTransactionRestoreResult(authoritative=True)

        primary = SelectiveMarkerError("command failed")
        with (
            mock.patch(
                "chemvas.core.history._history_canvas_port", return_value=ExactPort()
            ),
            history_core.history_operation_scope() as operation_token,
        ):
            history_core._mark_nonexact_history_compensation_failed(primary)
            restore_history_transaction_for_command(object(), object(), primary)
            self.assertFalse(
                consume_authoritative_history_failure_restore(
                    primary,
                    operation_token=operation_token,
                )
            )

        self.assertEqual(SelectiveMarkerError.marker_writes, 0)

    def test_undo_redo_preflight_bypasses_hostile_list_length(self) -> None:
        class HostileLengthList(list):
            length_reads = 0

            def __len__(self) -> int:
                type(self).length_reads += 1
                list.__setitem__(self, slice(None), ())
                return 0

        for direction in ("undo", "redo"):
            with self.subTest(direction=direction):
                log: list[str] = []
                command = _RecorderCommand("target", log)
                history = HostileLengthList()
                redo = HostileLengthList()
                if direction == "undo":
                    list.append(history, command)
                else:
                    list.append(redo, command)
                state = CanvasHistoryState(  # type: ignore[arg-type]
                    history=history,
                    redo_stack=redo,
                )
                service = CanvasHistoryService(SimpleNamespace(), state)

                getattr(service, direction)()

                self.assertEqual(log, [f"{direction}:target"])
                self.assertEqual(HostileLengthList.length_reads, 0)
                HostileLengthList.length_reads = 0

    def test_history_service_reentrant_observer_push_reports_no_commit(self) -> None:
        outer = _RecorderCommand("outer", [])
        inner = _RecorderCommand("inner", [])
        state = CanvasHistoryState()
        service = CanvasHistoryService(SimpleNamespace(), state)
        inner_errors: list[BaseException] = []

        def reentrant_observer() -> None:
            try:
                service.push(inner)
            except BaseException as error:
                inner_errors.append(error)

        state.change_callback = reentrant_observer

        self.assertTrue(service.push(outer))
        self.assertEqual(len(inner_errors), 1)
        self.assertIsInstance(inner_errors[0], RuntimeError)
        self.assertEqual(state.history, [outer])
        self.assertEqual(state.redo_stack, [])

    def test_history_context_guard_rejects_raw_flag_tampering(self) -> None:
        outer = _RecorderCommand("outer", [])
        inner = _RecorderCommand("inner", [])
        state = CanvasHistoryState()
        service = CanvasHistoryService(SimpleNamespace(), state)
        inner_errors: list[BaseException] = []

        def hostile_observer() -> None:
            state.change_callback = None
            # These compatibility/diagnostic fields are deliberately not the
            # operation authority. A callback that knows the service object
            # must not be able to counterfeit the end of the outer scope.
            service._history_mutation_active = False
            service._history_publication_active = False
            try:
                service.push(inner)
            except BaseException as error:
                inner_errors.append(error)

        state.change_callback = hostile_observer

        self.assertTrue(service.push(outer))

        self.assertEqual(len(inner_errors), 1)
        self.assertIsInstance(inner_errors[0], RuntimeError)
        self.assertEqual(state.history, [outer])
        self.assertFalse(service._history_mutation_active)
        self.assertFalse(service._history_publication_active)

    def test_history_context_guard_is_scoped_per_service_identity(self) -> None:
        outer = _RecorderCommand("outer", [])
        inner = _RecorderCommand("inner", [])
        outer_state = CanvasHistoryState()
        inner_state = CanvasHistoryState()
        outer_service = CanvasHistoryService(SimpleNamespace(), outer_state)
        inner_service = CanvasHistoryService(SimpleNamespace(), inner_state)
        inner_results: list[bool] = []

        def publish_to_independent_service() -> None:
            outer_state.change_callback = None
            inner_results.append(inner_service.push(inner))

        outer_state.change_callback = publish_to_independent_service

        self.assertTrue(outer_service.push(outer))

        self.assertEqual(inner_results, [True])
        self.assertEqual(outer_state.history, [outer])
        self.assertEqual(inner_state.history, [inner])
        self.assertFalse(outer_service._history_mutation_active)
        self.assertFalse(outer_service._history_publication_active)
        self.assertFalse(inner_service._history_mutation_active)
        self.assertFalse(inner_service._history_publication_active)

    def test_history_restore_setter_cannot_publish_then_erase_nested_push(self) -> None:
        before = _RecorderCommand("before", [])
        nested = _RecorderCommand("nested", [])
        corrupt = _RecorderCommand("corrupt", [])

        class ReentrantState(CanvasHistoryState):
            def __setattr__(self, name, value) -> None:
                object.__setattr__(self, name, value)
                if (
                    name == "history"
                    and getattr(self, "armed", False)
                    and value is getattr(self, "captured_history", None)
                ):
                    object.__setattr__(self, "armed", False)
                    try:
                        self.service.push(nested)
                    except BaseException as error:
                        self.nested_errors.append(error)

        state = ReentrantState(history=[before])
        state.captured_history = state.history
        state.armed = False
        state.nested_errors = []
        service = CanvasHistoryService(SimpleNamespace(), state)
        state.service = service

        def corrupt_then_unsubscribe() -> None:
            state.change_callback = None
            state.armed = True
            state.history = [corrupt]

        state.change_callback = corrupt_then_unsubscribe
        service.notify_change()

        self.assertEqual(len(state.nested_errors), 1)
        self.assertIsInstance(state.nested_errors[0], RuntimeError)
        self.assertEqual(state.history, [before])
        self.assertNotIn(nested, state.history)

    def test_history_push_setter_failure_recovers_or_rolls_back_pre_state(self) -> None:
        class _FlakyList(list):
            def __init__(self, values, behavior: str) -> None:
                super().__init__(values)
                self.behavior = behavior
                self.calls = 0

            def __setitem__(self, key, value) -> None:
                if isinstance(key, slice):
                    self.calls += 1
                    if self.behavior == "persistent_no_op":
                        return
                    if self.behavior == "fail_after" and self.calls == 1:
                        super().__setitem__(key, value)
                        self.append(object())
                        raise SystemExit("push setter failed after mutation")
                super().__setitem__(key, value)

        for behavior in ("fail_after", "persistent_no_op"):
            with self.subTest(behavior=behavior):
                history_sentinel = _RecorderCommand("history", [])
                redo_sentinel = _RecorderCommand("redo", [])
                command = _RecorderCommand("push", [])
                history = _FlakyList([history_sentinel], behavior)
                redo_stack = [redo_sentinel]
                state = CanvasHistoryState(
                    history=history,
                    redo_stack=redo_stack,
                )
                service = CanvasHistoryService(SimpleNamespace(), state)

                self.assertTrue(service.push(command))
                self.assertEqual(history, [history_sentinel, command])
                self.assertEqual(redo_stack, [])
                self.assertEqual(history.calls, 0)

    def test_legacy_history_uses_capture_bound_success_and_failure_deltas(self) -> None:
        class _LegacyCallbackCommand(HistoryCommand):
            def __init__(self) -> None:
                self.callback = lambda: None
                self.primary: BaseException | None = None
                self.calls: list[str] = []

            def _run(self, direction: str) -> None:
                self.calls.append(direction)
                self.callback()
                if self.primary is not None:
                    raise self.primary

            def undo(self, canvas) -> None:
                del canvas
                self._run("undo")

            def redo(self, canvas) -> None:
                del canvas
                self._run("redo")

        for direction in ("undo", "redo"):
            for outcome in ("success", "system_exit"):
                with self.subTest(direction=direction, outcome=outcome):
                    command = _LegacyCallbackCommand()
                    history_sentinel = _RecorderCommand("history", [])
                    redo_sentinel = _RecorderCommand("redo", [])
                    state = CanvasHistoryState(
                        history=(
                            [history_sentinel, command]
                            if direction == "undo"
                            else [history_sentinel]
                        ),
                        redo_stack=(
                            [redo_sentinel]
                            if direction == "undo"
                            else [redo_sentinel, command]
                        ),
                    )
                    history = state.history
                    redo_stack = state.redo_stack
                    service = CanvasHistoryService(SimpleNamespace(), state)
                    replacement = CanvasHistoryState(
                        history=[object()],
                        redo_stack=[object()],
                        enabled=False,
                        limit=0,
                    )

                    def corrupt_split_brain(
                        _state=state,
                        _service=service,
                        _replacement=replacement,
                    ) -> None:
                        _state.history.append(object())
                        _state.redo_stack.clear()
                        _state.enabled = False
                        _state.limit = 0
                        _service.state = _replacement

                    command.callback = corrupt_split_brain
                    primary = SystemExit(f"legacy {direction} callback terminated")
                    if outcome == "system_exit":
                        command.primary = primary

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
                    expected_history = [history_sentinel]
                    if outcome == "success" and direction == "redo":
                        expected_history.append(command)
                    expected_redo = (
                        [redo_sentinel, command]
                        if outcome == "success" and direction == "undo"
                        else [redo_sentinel]
                        if outcome == "success"
                        else []
                    )
                    self.assertEqual(history, expected_history)
                    self.assertEqual(redo_stack, expected_redo)

    def test_legacy_success_persistent_post_setter_clears_both_stacks(self) -> None:
        class _NoOpList(list):
            no_op = False

            def __setitem__(self, key, value) -> None:
                if self.no_op and isinstance(key, slice):
                    return
                super().__setitem__(key, value)

        class _LegacyCommand(HistoryCommand):
            def __init__(self, callback) -> None:
                self.callback = callback
                self.applied = False

            def undo(self, canvas) -> None:
                del canvas
                self.applied = True
                self.callback()

            def redo(self, canvas) -> None:
                del canvas
                self.applied = True
                self.callback()

        history_sentinel = _RecorderCommand("history", [])
        redo_sentinel = _RecorderCommand("redo", [])
        redo_stack = _NoOpList([redo_sentinel])
        command = _LegacyCommand(lambda: setattr(redo_stack, "no_op", True))
        state = CanvasHistoryState(
            history=[history_sentinel, command],
            redo_stack=redo_stack,
        )
        service = CanvasHistoryService(SimpleNamespace(), state)

        service.undo()

        self.assertTrue(command.applied)
        self.assertEqual(state.history, [history_sentinel])
        self.assertEqual(state.redo_stack, [redo_sentinel, command])

    def test_exact_success_commits_from_capture_bound_stack_authority(self) -> None:
        class _CallbackExactCommand(HistoryCommand):
            history_transaction_owns_exact_state = True

            def __init__(self) -> None:
                self.callback = lambda: None
                self.calls: list[str] = []

            def undo(self, canvas) -> None:
                del canvas
                self.calls.append("undo")
                self.callback()

            def redo(self, canvas) -> None:
                del canvas
                self.calls.append("redo")
                self.callback()

        for direction in ("undo", "redo"):
            for mutation in (
                "state",
                "history_clear",
                "history_append",
                "redo_replace",
                "policy",
            ):
                with self.subTest(direction=direction, mutation=mutation):
                    command = _CallbackExactCommand()
                    history_sentinel = _RecorderCommand("history", [])
                    redo_sentinel = _RecorderCommand("redo", [])
                    state = CanvasHistoryState(
                        history=(
                            [history_sentinel, command]
                            if direction == "undo"
                            else [history_sentinel]
                        ),
                        redo_stack=(
                            [redo_sentinel]
                            if direction == "undo"
                            else [redo_sentinel, command]
                        ),
                    )
                    history = state.history
                    redo_stack = state.redo_stack
                    service = CanvasHistoryService(SimpleNamespace(), state)
                    replacement = CanvasHistoryState(
                        history=[_RecorderCommand("wrong-history", [])],
                        redo_stack=[_RecorderCommand("wrong-redo", [])],
                        enabled=False,
                        limit=0,
                    )

                    def corrupt_during_command(
                        _mutation=mutation,
                        _service=service,
                        _replacement=replacement,
                        _state=state,
                    ) -> None:
                        if _mutation == "state":
                            _service.state = _replacement
                        elif _mutation == "history_clear":
                            _state.history.clear()
                        elif _mutation == "history_append":
                            _state.history.append(_RecorderCommand("wrong-top", []))
                        elif _mutation == "redo_replace":
                            _state.redo_stack = [_RecorderCommand("wrong-redo", [])]
                        else:
                            _state.enabled = False
                            _state.limit = 0

                    command.callback = corrupt_during_command

                    getattr(service, direction)()

                    self.assertEqual(command.calls, [direction])
                    self.assertIs(service.state, state)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo_stack)
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
                    self.assertTrue(state.enabled)
                    self.assertEqual(state.limit, 100)

    def test_exact_failure_combines_runtime_and_stack_authority(self) -> None:
        class _FailingExactCommand(HistoryCommand):
            history_transaction_owns_exact_state = True

            def __init__(self, callback, primary: BaseException) -> None:
                self.callback = callback
                self.primary = primary

            def undo(self, canvas) -> None:
                del canvas
                self.callback()
                raise self.primary

            def redo(self, canvas) -> None:
                del canvas
                self.callback()
                raise self.primary

        for direction in ("undo", "redo"):
            for primary_type in (RuntimeError, SystemExit):
                with self.subTest(
                    direction=direction,
                    primary=primary_type.__name__,
                ):
                    primary = primary_type(f"{direction} callback failure")
                    history_sentinel = _RecorderCommand("history", [])
                    redo_sentinel = _RecorderCommand("redo", [])
                    state = CanvasHistoryState()
                    service = CanvasHistoryService(SimpleNamespace(), state)
                    replacement = CanvasHistoryState(
                        history=[object()],
                        redo_stack=[object()],
                        enabled=False,
                        limit=0,
                    )

                    def corrupt_every_authority(
                        _state=state,
                        _service=service,
                        _replacement=replacement,
                    ) -> None:
                        _state.history.clear()
                        _state.redo_stack.append(object())
                        _state.enabled = False
                        _state.limit = 0
                        _service.state = _replacement

                    command = _FailingExactCommand(
                        corrupt_every_authority,
                        primary,
                    )
                    history = state.history
                    redo_stack = state.redo_stack
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
                    expected_history = list(history)
                    expected_redo = list(redo_stack)

                    with mock.patch(
                        "chemvas.ui.canvas_history_service."
                        "consume_authoritative_history_failure_restore",
                        return_value=True,
                    ):
                        with self.assertRaises(primary_type) as caught:
                            getattr(service, direction)()

                    self.assertIs(caught.exception, primary)
                    self.assertIs(service.state, state)
                    self.assertIs(state.history, history)
                    self.assertIs(state.redo_stack, redo_stack)
                    self.assertEqual(history, expected_history)
                    self.assertEqual(redo_stack, expected_redo)
                    self.assertTrue(state.enabled)
                    self.assertEqual(state.limit, 100)

    def test_exact_success_stack_setter_recovery_or_conservative_clear(self) -> None:
        class _FlakyList(list):
            def __init__(self, values) -> None:
                super().__init__(values)
                self.behavior = "normal"
                self.calls = 0

            def __setitem__(self, key, value) -> None:
                if isinstance(key, slice) and self.behavior != "normal":
                    self.calls += 1
                    if self.behavior == "persistent_no_op":
                        return
                    if self.behavior == "fail_after" and self.calls == 1:
                        super().__setitem__(key, value)
                        self.append(object())
                        raise SystemExit("stack setter failed after mutation")
                super().__setitem__(key, value)

        class _ExactCommand(HistoryCommand):
            history_transaction_owns_exact_state = True

            def __init__(self, callback) -> None:
                self.callback = callback
                self.applied = False

            def undo(self, canvas) -> None:
                del canvas
                self.applied = True
                self.callback()

            def redo(self, canvas) -> None:
                del canvas
                self.applied = True
                self.callback()

        for direction in ("undo", "redo"):
            for behavior in ("fail_after", "persistent_no_op"):
                with self.subTest(direction=direction, behavior=behavior):
                    history_sentinel = _RecorderCommand("history", [])
                    redo_sentinel = _RecorderCommand("redo", [])
                    redo_stack = _FlakyList([])
                    command = _ExactCommand(
                        lambda _redo=redo_stack, _behavior=behavior: setattr(
                            _redo,
                            "behavior",
                            _behavior,
                        )
                    )
                    history = [history_sentinel]
                    if direction == "undo":
                        history.append(command)
                        redo_stack.append(redo_sentinel)
                    else:
                        redo_stack.extend((redo_sentinel, command))
                    state = CanvasHistoryState(
                        history=history,
                        redo_stack=redo_stack,
                    )
                    service = CanvasHistoryService(SimpleNamespace(), state)

                    getattr(service, direction)()
                    self.assertTrue(command.applied)
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
                    self.assertEqual(state.history, expected_history)
                    self.assertEqual(state.redo_stack, expected_redo)
                    self.assertEqual(redo_stack.calls, 0)

    def test_exact_success_state_setter_recovery_or_split_brain_clear(self) -> None:
        class _StatefulHistoryService(CanvasHistoryService):
            def __init__(self, canvas, state) -> None:
                self._state = state
                self.state_behavior = "normal"
                self.state_setter_calls = 0
                super().__init__(canvas, state)
                self.state_setter_calls = 0

            @property
            def state(self):
                return self._state

            @state.setter
            def state(self, value) -> None:
                self.state_setter_calls += 1
                if self.state_behavior == "persistent_no_op":
                    return
                self._state = value
                if self.state_behavior == "fail_after" and self.state_setter_calls == 1:
                    raise SystemExit("state setter failed after mutation")

        class _ExactCommand(HistoryCommand):
            history_transaction_owns_exact_state = True

            def __init__(self, callback) -> None:
                self.callback = callback

            def undo(self, canvas) -> None:
                del canvas
                self.callback()

            def redo(self, canvas) -> None:
                del canvas
                self.callback()

        for behavior in ("fail_after", "persistent_no_op"):
            with self.subTest(behavior=behavior):
                history_sentinel = _RecorderCommand("history", [])
                redo_sentinel = _RecorderCommand("redo", [])
                original_state = CanvasHistoryState()
                replacement_state = CanvasHistoryState(
                    history=[object()],
                    redo_stack=[object()],
                    enabled=False,
                    limit=0,
                )
                service = _StatefulHistoryService(
                    SimpleNamespace(),
                    original_state,
                )

                def replace_state(
                    _service=service,
                    _replacement=replacement_state,
                    _behavior=behavior,
                ) -> None:
                    _service._state = _replacement
                    _service.state_behavior = _behavior
                    _service.state_setter_calls = 0

                command = _ExactCommand(replace_state)
                original_state.history[:] = [history_sentinel, command]
                original_state.redo_stack[:] = [redo_sentinel]

                if behavior == "persistent_no_op":
                    with self.assertRaises(BaseExceptionGroup):
                        service.undo()
                    self.assertIs(service.state, replacement_state)
                    self.assertEqual(original_state.history, [])
                    self.assertEqual(original_state.redo_stack, [])
                    self.assertEqual(replacement_state.history, [])
                    self.assertEqual(replacement_state.redo_stack, [])
                else:
                    service.undo()
                    self.assertIs(service.state, original_state)
                    self.assertEqual(original_state.history, [history_sentinel])
                    self.assertEqual(
                        original_state.redo_stack,
                        [redo_sentinel, command],
                    )

    def test_persistent_same_state_stack_replacement_clears_both_roots(self) -> None:
        class _NoOpStackState:
            def __init__(self, history, redo_stack) -> None:
                self._history = history
                self._redo_stack = redo_stack
                self.enabled = True
                self.limit = 100
                self.change_callback = None
                self.no_op = False

            @property
            def history(self):
                return self._history

            @history.setter
            def history(self, value) -> None:
                if not self.no_op:
                    self._history = value

            @property
            def redo_stack(self):
                return self._redo_stack

            @redo_stack.setter
            def redo_stack(self, value) -> None:
                if not self.no_op:
                    self._redo_stack = value

        class _ExactCommand(HistoryCommand):
            history_transaction_owns_exact_state = True

            def __init__(self, callback) -> None:
                self.callback = callback

            def undo(self, canvas) -> None:
                del canvas
                self.callback()

            def redo(self, canvas) -> None:
                del canvas
                self.callback()

        history_sentinel = _RecorderCommand("history", [])
        redo_sentinel = _RecorderCommand("redo", [])
        original_history: list[object] = [history_sentinel]
        original_redo: list[object] = [redo_sentinel]
        state = _NoOpStackState(original_history, original_redo)
        replacement_history = [object()]
        replacement_redo = [object()]

        def replace_both_stacks() -> None:
            state._history = replacement_history
            state._redo_stack = replacement_redo
            state.no_op = True

        command = _ExactCommand(replace_both_stacks)
        original_history.append(command)
        service = CanvasHistoryService(SimpleNamespace(), state)

        with self.assertRaises(BaseExceptionGroup):
            service.undo()

        self.assertIs(service.state, state)
        self.assertEqual(original_history, [])
        self.assertEqual(original_redo, [])
        self.assertEqual(replacement_history, [])
        self.assertEqual(replacement_redo, [])

    def test_history_observer_self_unsubscribe_is_preserved(self) -> None:
        command = _RecorderCommand("commit", [])
        state = CanvasHistoryState()
        service = CanvasHistoryService(SimpleNamespace(), state)
        callback_calls = 0

        def unsubscribe() -> None:
            nonlocal callback_calls
            callback_calls += 1
            state.change_callback = None

        state.change_callback = unsubscribe

        self.assertTrue(service.push(command))
        self.assertEqual(callback_calls, 1)
        self.assertIsNone(state.change_callback)

    def test_history_service_drops_exact_composite_after_nonauthoritative_outer_restore(
        self,
    ) -> None:
        class _PartialRestorePort(_StatefulHistoryPort):
            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(
                self,
                canvas,
                snapshot,
            ) -> HistoryTransactionRestoreResult:
                del canvas, snapshot
                return HistoryTransactionRestoreResult(
                    authoritative=False,
                    fallback_to_inverse=False,
                    errors=(RuntimeError("persistent exact restore failure"),),
                )

        atom_states = {
            1: {"element": "C", "x": 1.0, "y": 2.0},
            2: {"element": "N", "x": 3.0, "y": 4.0},
        }
        canvas = _AtomicHistoryCanvas(
            atoms=atom_states,
            next_atom_id=3,
            smiles_input="after",
        )
        port = _PartialRestorePort()
        composite = CompositeCommand(
            [
                AddAtomsCommand(
                    atom_states=atom_states,
                    before_next_atom_id=1,
                    after_next_atom_id=3,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _ToggleStateCommand(),
            ]
        )
        stale_redo = _RecorderCommand("stale", [])
        state = CanvasHistoryState(history=[composite], redo_stack=[stale_redo])
        service = CanvasHistoryService(canvas, state)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_once_after("remove_atom", 2)
            with self.assertRaisesRegex(RuntimeError, "remove_atom failed") as caught:
                service.undo()

        # The deferred child's provisional success cannot retain the command;
        # only the final owning restore result controls retry safety.
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])
        self.assertTrue(
            any(
                "persistent exact restore failure" in note
                for note in caught.exception.__notes__
            )
        )

    def test_history_service_does_not_reuse_authority_marker_from_same_exception(
        self,
    ) -> None:
        shared_error = RuntimeError("shared remove failure")

        class _SharedFailurePort(_StatefulHistoryPort):
            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                super().remove_bond_for_history(canvas, bond_id)
                raise shared_error

        bond_state = {"a": 1, "b": 2, "order": 1}
        canvas = _AtomicHistoryCanvas(bonds={0: bond_state}, smiles_input="after")
        port = _SharedFailurePort()
        command = AddBondCommand(
            bond_id=0,
            bond_state=bond_state,
            previous_bond_count=0,
            before_smiles_input="before",
            after_smiles_input="after",
        )
        stale_redo = _RecorderCommand("stale", [])
        state = CanvasHistoryState(history=[command], redo_stack=[stale_redo])
        service = CanvasHistoryService(canvas, state)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(RuntimeError, "shared remove failure"):
                service.undo()
            self.assertEqual(state.history, [command])
            self.assertEqual(state.redo_stack, [stale_redo])

            # Reuse the identical BaseException from a later operation whose
            # port no longer has an exact transaction. The prior authoritative
            # result must not make this unknown failure retryable.
            port.capture_history_transaction_for_history = None
            port.restore_history_transaction_for_history = None
            with self.assertRaisesRegex(RuntimeError, "shared remove failure"):
                service.undo()

        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_history_service_applies_failure_stack_policy_for_baseexception(
        self,
    ) -> None:
        class _CancellationCommand(HistoryCommand):
            def undo(self, canvas) -> None:
                del canvas
                raise KeyboardInterrupt("undo cancelled")

            def redo(self, canvas) -> None:
                del canvas
                raise KeyboardInterrupt("redo cancelled")

        def fail_notification() -> None:
            raise SystemExit("observer termination")

        for direction in ("undo", "redo"):
            with self.subTest(direction=direction):
                command = _CancellationCommand()
                stale_command = _RecorderCommand("stale", [])
                state = CanvasHistoryState(
                    history=[command] if direction == "undo" else [stale_command],
                    redo_stack=[stale_command]
                    if direction == "undo"
                    else [stale_command, command],
                    change_callback=fail_notification,
                )
                service = CanvasHistoryService(SimpleNamespace(), state)

                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    f"{direction} cancelled",
                ) as caught:
                    getattr(service, direction)()

                self.assertEqual(state.redo_stack, [])
                self.assertTrue(
                    any(
                        "observer termination" in note
                        for note in caught.exception.__notes__
                    )
                )

    def test_lifecycle_composite_captures_one_outer_transaction(self) -> None:
        class _SnapshotPort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0
                self.restore_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                self.restore_calls += 1
                canvas.model.atoms = deepcopy(snapshot["atoms"])
                canvas.model.next_atom_id = snapshot["next_atom_id"]
                canvas.coords_3d = dict(snapshot["coords_3d"])
                canvas.marks = deepcopy(snapshot["marks"])
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]
                canvas.projection_center_3d = snapshot["projection_center_3d"]
                canvas.projection_anchor_2d = snapshot["projection_anchor_2d"]
                canvas.toggle = snapshot["toggle"]

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        port = _SnapshotPort()
        commands = [
            AddBondCommand(
                bond_id=bond_id,
                bond_state={"a": bond_id, "b": bond_id + 1, "order": 1},
                previous_bond_count=bond_id,
                before_smiles_input="before",
                after_smiles_input="after",
            )
            for bond_id in range(50)
        ]
        composite = CompositeCommand(commands)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            composite.redo(canvas)
            self.assertEqual(port.capture_calls, 1)
            composite.undo(canvas)

        self.assertEqual(port.capture_calls, 2)
        self.assertEqual(port.restore_calls, 0)

    def test_release_failure_is_part_of_exact_command_transaction(self) -> None:
        class _Snapshot:
            def __init__(self, length: float, *, fail_release: bool) -> None:
                self.length = length
                self.fail_release = fail_release
                self.release_calls = 0

            def release(self) -> None:
                self.release_calls += 1
                if self.fail_release:
                    raise SystemExit("transaction release failed")

        class _ReleasePort(_StatefulHistoryPort):
            def __init__(self, *, fail_release: bool) -> None:
                super().__init__()
                self.fail_release = fail_release
                self.snapshot = None
                self.restore_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.snapshot = _Snapshot(
                    canvas.length,
                    fail_release=self.fail_release,
                )
                return self.snapshot

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                self.restore_calls += 1
                canvas.length = snapshot.length

            def restore_bond_length_for_history(self, canvas, length_px: float) -> None:
                canvas.length = length_px

        for fail_release in (False, True):
            with self.subTest(fail_release=fail_release):
                canvas = SimpleNamespace(length=20.0)
                port = _ReleasePort(fail_release=fail_release)
                command = UpdateBondLengthCommand(20.0, 30.0)
                with mock.patch(
                    "chemvas.core.history._history_canvas_port", return_value=port
                ):
                    if fail_release:
                        with self.assertRaisesRegex(
                            SystemExit, "transaction release failed"
                        ):
                            command.redo(canvas)
                    else:
                        command.redo(canvas)

                assert port.snapshot is not None
                self.assertEqual(port.snapshot.release_calls, 1)
                self.assertEqual(port.restore_calls, int(fail_release))
                self.assertEqual(canvas.length, 20.0 if fail_release else 30.0)

    def test_release_uses_port_hook_for_opaque_transaction_token(self) -> None:
        class _OpaqueToken:
            pass

        class _OpaquePort(_StatefulHistoryPort):
            def __init__(self, *, fail_release: bool) -> None:
                super().__init__()
                self.fail_release = fail_release
                self.token = _OpaqueToken()
                self.release_calls: list[tuple[object, object]] = []
                self.restore_calls: list[tuple[object, object]] = []

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.before_length = canvas.length
                return self.token

            def release_history_transaction_for_history(self, canvas, snapshot) -> None:
                self.release_calls.append((canvas, snapshot))
                if self.fail_release:
                    raise SystemExit("opaque transaction release failed")

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                self.restore_calls.append((canvas, snapshot))
                canvas.length = self.before_length

            def restore_bond_length_for_history(self, canvas, length_px: float) -> None:
                canvas.length = length_px

        for fail_release in (False, True):
            with self.subTest(fail_release=fail_release):
                canvas = SimpleNamespace(length=20.0)
                port = _OpaquePort(fail_release=fail_release)
                command = UpdateBondLengthCommand(20.0, 30.0)
                with mock.patch(
                    "chemvas.core.history._history_canvas_port", return_value=port
                ):
                    if fail_release:
                        with self.assertRaisesRegex(
                            SystemExit,
                            "opaque transaction release failed",
                        ):
                            command.redo(canvas)
                    else:
                        command.redo(canvas)

                self.assertEqual(port.release_calls, [(canvas, port.token)])
                self.assertEqual(
                    port.restore_calls,
                    [(canvas, port.token)] if fail_release else [],
                )
                self.assertEqual(canvas.length, 20.0 if fail_release else 30.0)

    def test_lifecycle_composite_failure_uses_outer_snapshot_without_child_inverse(
        self,
    ) -> None:
        class _SnapshotPort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0
                self.restore_calls = 0
                self.remove_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                self.restore_calls += 1
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]

            def remove_bond_for_history(self, canvas, bond_id: int) -> None:
                self.remove_calls += 1
                super().remove_bond_for_history(canvas, bond_id)

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        port = _SnapshotPort()
        composite = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state={"a": bond_id, "b": bond_id + 1, "order": 1},
                    previous_bond_count=bond_id,
                    before_smiles_input="before",
                    after_smiles_input="after",
                )
                for bond_id in range(20)
            ]
        )
        before = _atomic_canvas_snapshot(canvas)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_once_after("restore_bond", 10)
            with self.assertRaisesRegex(RuntimeError, "restore_bond failed"):
                composite.redo(canvas)

        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertEqual(port.capture_calls, 1)
        self.assertEqual(port.restore_calls, 1)
        self.assertEqual(port.remove_calls, 0)

    def test_mixed_exact_composite_inverses_completed_unknown_state_before_snapshot_restore(
        self,
    ) -> None:
        class _SnapshotPort(_StatefulHistoryPort):
            def __init__(self) -> None:
                super().__init__()
                self.capture_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]
                canvas.toggle = snapshot["toggle"]

        class _CustomCounterCommand(HistoryCommand):
            def undo(self, canvas) -> None:
                canvas.custom_counter -= 1

            def redo(self, canvas) -> None:
                canvas.custom_counter += 1

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        canvas.custom_counter = 0
        port = _SnapshotPort()
        command = CompositeCommand(
            [
                _CustomCounterCommand(),
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
            ]
        )

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_once_after("restore_bond", 0)
            with self.assertRaisesRegex(RuntimeError, "restore_bond failed"):
                command.redo(canvas)

        self.assertEqual(canvas.custom_counter, 0)
        self.assertEqual(canvas.bonds, {})
        self.assertEqual(canvas.smiles_input, "before")
        self.assertEqual(port.capture_calls, 1)

    def test_failed_unknown_inverse_makes_outer_exact_restore_nonauthoritative_for_stack(
        self,
    ) -> None:
        class _SnapshotPort(_StatefulHistoryPort):
            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]

        class _FailingCounterInverse(HistoryCommand):
            def undo(self, canvas) -> None:
                canvas.custom_counter -= 1
                raise SystemExit("custom inverse failed")

            def redo(self, canvas) -> None:
                canvas.custom_counter += 1

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        canvas.custom_counter = 0
        port = _SnapshotPort()
        composite = CompositeCommand(
            [
                _FailingCounterInverse(),
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
            ]
        )
        stale_history = _RecorderCommand("stale", [])
        state = CanvasHistoryState(
            history=[stale_history],
            redo_stack=[composite],
        )
        service = CanvasHistoryService(canvas, state)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            port.fail_once_after("restore_bond", 0)
            with self.assertRaisesRegex(RuntimeError, "restore_bond failed") as caught:
                service.redo()

        self.assertEqual(canvas.custom_counter, 0)
        self.assertEqual(state.history, [stale_history])
        self.assertEqual(state.redo_stack, [])
        self.assertTrue(
            any("custom inverse failed" in note for note in caught.exception.__notes__)
        )

    def test_failed_unknown_child_cannot_claim_outer_exact_restore_authority(
        self,
    ) -> None:
        class _SnapshotPort(_StatefulHistoryPort):
            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                return _atomic_canvas_snapshot(canvas)

            def restore_history_transaction_for_history(self, canvas, snapshot) -> None:
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]

        class _MutateThenFailUnknownCommand(HistoryCommand):
            def undo(self, canvas) -> None:
                canvas.custom_counter -= 1

            def redo(self, canvas) -> None:
                canvas.custom_counter += 1
                raise RuntimeError("unknown child failed after mutation")

        canvas = _AtomicHistoryCanvas(smiles_input="before")
        canvas.custom_counter = 0
        port = _SnapshotPort()
        composite = CompositeCommand(
            [
                AddBondCommand(
                    bond_id=0,
                    bond_state={"a": 1, "b": 2, "order": 1},
                    previous_bond_count=0,
                    before_smiles_input="before",
                    after_smiles_input="after",
                ),
                _MutateThenFailUnknownCommand(),
            ]
        )
        stale_history = _RecorderCommand("stale", [])
        state = CanvasHistoryState(history=[stale_history], redo_stack=[composite])
        service = CanvasHistoryService(canvas, state)

        with mock.patch("chemvas.core.history._history_canvas_port", return_value=port):
            with self.assertRaisesRegex(RuntimeError, "unknown child failed"):
                service.redo()

        self.assertEqual(canvas.bonds, {})
        self.assertEqual(canvas.smiles_input, "before")
        self.assertEqual(canvas.custom_counter, 1)
        self.assertEqual(state.history, [stale_history])
        self.assertEqual(state.redo_stack, [])

    def test_move_commands_delegate_to_canvas(self) -> None:
        canvas = _FakeCanvas()
        move_atoms = MoveAtomsCommand(
            {1, 2}, 3.5, -4.0, bond_ids={7}, redraw_bond_ids={8}
        )
        scene_item = _FakeItem(canvas.scene())
        off_scene_item = _FakeItem(object())
        move_items = MoveItemsCommand([scene_item, None, off_scene_item], 2.0, 5.0)

        move_atoms.undo(canvas)
        move_atoms.redo(canvas)
        move_items.undo(canvas)
        move_items.redo(canvas)

        self.assertIn(("move_atoms", {1, 2}, -3.5, 4.0, {7}, {8}, True), canvas.calls)
        self.assertIn(("move_atoms", {1, 2}, 3.5, -4.0, {7}, {8}, True), canvas.calls)
        self.assertEqual(
            canvas.calls.count(("move_item", scene_item, -2.0, -5.0, False)), 1
        )
        self.assertEqual(
            canvas.calls.count(("move_item", scene_item, 2.0, 5.0, False)), 1
        )
        self.assertEqual(canvas.calls.count(("refresh_selection_outline",)), 2)

        dead_item = _FakeItem(canvas.scene(), raises=True)
        with self.assertRaisesRegex(RuntimeError, "item deleted"):
            MoveItemsCommand([dead_item], 2.0, 5.0).redo(canvas)

    def test_position_and_polygon_commands_apply_history_ports(self) -> None:
        canvas = _FakeCanvas()
        atom_command = SetAtomPositionsCommand(
            {1: (0.0, 0.0)}, {1: (2.0, 3.0)}, update_selection=False
        )
        ring = _FakeRingItem(canvas)
        ring_command = SetRingPolygonsCommand([ring], [[(0.0, 0.0)]], [[(1.0, 1.0)]])

        atom_command.undo(canvas)
        atom_command.redo(canvas)
        ring_command.undo(canvas)
        ring_command.redo(canvas)

        self.assertEqual((canvas.model.atoms[1].x, canvas.model.atoms[1].y), (2.0, 3.0))
        self.assertEqual(canvas.calls.count(("redraw_bonds_for_atoms", {1})), 2)
        self.assertIn(("set_ring_polygon", [(0.0, 0.0)]), canvas.calls)
        self.assertIn(("set_ring_polygon", [(1.0, 1.0)]), canvas.calls)

    def test_set_atom_positions_command_restores_projection_state(self) -> None:
        canvas = _FakeCanvas()
        command = SetAtomPositionsCommand(
            {1: (0.0, 0.0)},
            {1: (2.0, 3.0)},
            before_coords_3d={1: (0.0, 0.0, 0.0)},
            after_coords_3d={1: (2.0, 3.0, 4.0)},
            restore_projection_state=True,
            before_projection_center_3d=None,
            after_projection_center_3d=(5.0, 6.0, 7.0),
            before_projection_anchor_2d=None,
            after_projection_anchor_2d=(8.0, 9.0),
        )

        command.redo(canvas)
        self.assertEqual(canvas.rotation_state.projection_center_3d, (5.0, 6.0, 7.0))
        self.assertEqual(canvas.rotation_state.projection_anchor_2d, (8.0, 9.0))

        command.undo(canvas)
        self.assertIsNone(canvas.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.rotation_state.projection_anchor_2d)

    def test_set_atom_positions_command_uses_current_projection_and_coords_contract(
        self,
    ) -> None:
        canvas = _MinimalCanvas()
        command = SetAtomPositionsCommand(
            {1: (0.0, 0.0)},
            {1: (2.0, 3.0)},
            before_coords_3d={1: (0.0, 0.0, 0.0)},
            after_coords_3d={1: (2.0, 3.0, 4.0)},
            restore_projection_state=True,
        )

        command.redo(canvas)
        command.undo(canvas)

        self.assertEqual((canvas.model.atoms[1].x, canvas.model.atoms[1].y), (0.0, 0.0))
        self.assertEqual(canvas.atom_coords_3d[1], (0.0, 0.0, 0.0))
        self.assertEqual(canvas.calls.count(("redraw_bonds_for_atoms", {1})), 2)
        self.assertEqual(canvas.calls.count(("refresh_selection_outline",)), 2)
        self.assertIsNone(canvas.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.rotation_state.projection_anchor_2d)

    def test_update_commands_apply_length_color_scene_state_and_smiles(self) -> None:
        canvas = _FakeCanvas()
        length_command = UpdateBondLengthCommand(18.0, 24.0)
        smiles_command = SetSmilesInputCommand("before", "after")
        color_command = UpdateAtomColorCommand(4, "#000000", "#ff0000")
        scene_state_command = UpdateSceneItemCommand("item", {"x": 1}, {"x": 2})

        length_command.undo(canvas)
        length_command.redo(canvas)
        smiles_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before")
        smiles_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after")
        color_command.undo(canvas)
        color_command.redo(canvas)
        scene_state_command.undo(canvas)
        scene_state_command.redo(canvas)

        self.assertEqual(canvas.calls.count(("set_bond_length", 18.0)), 1)
        self.assertEqual(canvas.calls.count(("set_bond_length", 24.0)), 1)
        self.assertIn(("apply_atom_color", 4, "#000000"), canvas.calls)
        self.assertIn(("apply_atom_color", 4, "#ff0000"), canvas.calls)
        self.assertIn(("apply_scene_item_state", "item", {"x": 1}), canvas.calls)
        self.assertIn(("apply_scene_item_state", "item", {"x": 2}), canvas.calls)
        self.assertEqual(canvas.calls.count(("refresh_selection_outline",)), 4)

    def test_atom_commands_restore_and_remove_atoms_and_marks(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.next_atom_id = 10
        add_command = AddAtomsCommand(
            atom_states={3: {"element": "C"}},
            before_next_atom_id=3,
            after_next_atom_id=4,
            before_smiles_input="old",
            after_smiles_input="new",
        )
        delete_command = DeleteAtomsCommand(
            atom_states={3: {"element": "O"}},
            mark_states=[{"kind": "plus"}],
            before_next_atom_id=4,
            after_next_atom_id=3,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        add_command.undo(canvas)
        add_command.redo(canvas)
        delete_command.undo(canvas)
        delete_command.redo(canvas)

        self.assertIn(("remove_atom_for_history", 3, True), canvas.calls)
        self.assertIn(("restore_atom_from_state", 3, {"element": "C"}), canvas.calls)
        self.assertIn(("restore_atom_from_state", 3, {"element": "O"}), canvas.calls)
        self.assertIn(("restore_mark_from_state", {"kind": "plus"}), canvas.calls)
        self.assertEqual(canvas.model.next_atom_id, 3)
        self.assertEqual(canvas.last_smiles_input, "after")

    def test_add_atoms_command_restores_atom_coords_3d_on_redo(self) -> None:
        canvas = _FakeCanvas()
        command = AddAtomsCommand(
            atom_states={3: {"element": "N", "x": 1.0, "y": 2.0}},
            before_next_atom_id=3,
            after_next_atom_id=4,
            atom_coords_3d={3: (1.0, 2.0, 3.0)},
        )

        command.redo(canvas)

        self.assertEqual(atom_coords_3d_for(canvas)[3], (1.0, 2.0, 3.0))
        self.assertIn(("redraw_bonds_for_atoms", {3}), canvas.calls)

    def test_delete_atoms_command_restores_atom_coords_3d_on_undo(self) -> None:
        canvas = _FakeCanvas()
        command = DeleteAtomsCommand(
            atom_states={3: {"element": "N", "x": 1.0, "y": 2.0}},
            before_next_atom_id=4,
            after_next_atom_id=3,
            atom_coords_3d={3: (1.0, 2.0, 3.0)},
        )

        command.undo(canvas)

        self.assertEqual(atom_coords_3d_for(canvas)[3], (1.0, 2.0, 3.0))
        self.assertIn(("redraw_bonds_for_atoms", {3}), canvas.calls)

    def test_delete_atoms_command_restores_projection_state_when_requested(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        command = DeleteAtomsCommand(
            atom_states={3: {"element": "N", "x": 1.0, "y": 2.0}},
            before_next_atom_id=4,
            after_next_atom_id=3,
            atom_coords_3d={3: (1.0, 2.0, 3.0)},
            restore_projection_state=True,
            before_projection_center_3d=(1.0, 2.0, 3.0),
            after_projection_center_3d=None,
            before_projection_anchor_2d=(1.0, 2.0),
            after_projection_anchor_2d=None,
        )

        command.undo(canvas)
        self.assertEqual(canvas.rotation_state.projection_center_3d, (1.0, 2.0, 3.0))
        self.assertEqual(canvas.rotation_state.projection_anchor_2d, (1.0, 2.0))
        self.assertEqual(atom_coords_3d_for(canvas)[3], (1.0, 2.0, 3.0))

        command.redo(canvas)
        self.assertIsNone(canvas.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.rotation_state.projection_anchor_2d)

    def test_delete_atoms_command_can_skip_mark_restoration_and_mark_removal(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        command = DeleteAtomsCommand(
            atom_states={8: {"element": "N"}},
            mark_states=[{"kind": "minus"}],
            before_next_atom_id=9,
            after_next_atom_id=8,
            before_smiles_input="before",
            after_smiles_input="after",
            remove_marks=False,
        )

        command.undo(canvas)
        command.redo(canvas)

        self.assertIn(("restore_atom_from_state", 8, {"element": "N"}), canvas.calls)
        self.assertIn(("remove_atom_for_history", 8, False), canvas.calls)
        self.assertNotIn(("restore_mark_from_state", {"kind": "minus"}), canvas.calls)
        self.assertEqual(canvas.model.next_atom_id, 8)
        self.assertEqual(canvas.last_smiles_input, "after")

    def test_scene_item_commands_create_remove_and_restore_items(self) -> None:
        canvas = _FakeCanvas()
        add_command = AddSceneItemsCommand(item_states=[{"kind": "note"}])
        delete_command = DeleteSceneItemsCommand(item_states=[{"kind": "arrow"}])

        add_command.redo(canvas)
        add_item = add_command.items[0]
        add_command.undo(canvas)
        add_command.redo(canvas)

        delete_command.undo(canvas)
        delete_item = delete_command.items[0]
        delete_command.redo(canvas)
        delete_command.undo(canvas)

        self.assertIn(("create_scene_item_from_state", {"kind": "note"}), canvas.calls)
        self.assertIn(("remove_scene_item", add_item), canvas.calls)
        self.assertIn(("restore_scene_item", add_item), canvas.calls)
        self.assertIn(("create_scene_item_from_state", {"kind": "arrow"}), canvas.calls)
        self.assertIn(("remove_scene_item", delete_item), canvas.calls)
        self.assertIn(("restore_scene_item", delete_item), canvas.calls)

    def test_scene_item_commands_skip_none_items_when_restoring_existing_pool(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        add_command = AddSceneItemsCommand(item_states=[], items=[None, "note-item"])
        delete_command = DeleteSceneItemsCommand(
            item_states=[], items=[None, "arrow-item"]
        )

        add_command.redo(canvas)
        delete_command.undo(canvas)

        self.assertEqual(
            canvas.calls,
            [
                ("restore_scene_item", "note-item"),
                ("restore_scene_item", "arrow-item"),
            ],
        )

    def test_scene_item_commands_prefer_scene_item_controller_when_available(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.services.scene_view.scene_item_controller = _FakeSceneItemController(
            canvas
        )
        add_command = AddSceneItemsCommand(item_states=[{"kind": "note"}])
        delete_command = DeleteSceneItemsCommand(item_states=[{"kind": "arrow"}])
        update_command = UpdateSceneItemCommand("item", {"x": 1}, {"x": 2})
        delete_atoms_command = DeleteAtomsCommand(
            atom_states={},
            mark_states=[{"kind": "plus"}],
            before_next_atom_id=1,
            after_next_atom_id=1,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        add_command.redo(canvas)
        add_item = add_command.items[0]
        add_command.undo(canvas)
        add_command.redo(canvas)

        delete_command.undo(canvas)
        delete_item = delete_command.items[0]
        delete_command.redo(canvas)
        delete_command.undo(canvas)

        update_command.undo(canvas)
        update_command.redo(canvas)
        delete_atoms_command.undo(canvas)

        self.assertIn(
            ("controller_create_scene_item_from_state", {"kind": "note"}), canvas.calls
        )
        self.assertIn(("controller_remove_scene_item", add_item), canvas.calls)
        self.assertIn(("controller_restore_scene_item", add_item), canvas.calls)
        self.assertIn(
            ("controller_create_scene_item_from_state", {"kind": "arrow"}), canvas.calls
        )
        self.assertIn(("controller_remove_scene_item", delete_item), canvas.calls)
        self.assertIn(("controller_restore_scene_item", delete_item), canvas.calls)
        self.assertIn(
            ("controller_apply_scene_item_state", "item", {"x": 1}), canvas.calls
        )
        self.assertIn(
            ("controller_apply_scene_item_state", "item", {"x": 2}), canvas.calls
        )
        self.assertEqual(canvas.calls.count(("refresh_selection_outline",)), 2)
        self.assertIn(
            ("controller_restore_mark_from_state", {"kind": "plus"}), canvas.calls
        )
        self.assertNotIn(
            ("create_scene_item_from_state", {"kind": "note"}), canvas.calls
        )
        self.assertNotIn(("apply_scene_item_state", "item", {"x": 1}), canvas.calls)
        self.assertNotIn(("restore_mark_from_state", {"kind": "plus"}), canvas.calls)

    def test_change_atom_label_command_replays_label_state_without_recording(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        command = ChangeAtomLabelCommand(
            atom_id=5,
            before_element="C",
            after_element="N",
            before_explicit_label=False,
            after_explicit_label=True,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before")
        command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after")

        self.assertEqual(
            canvas.calls[0],
            ("add_or_update_atom_label", 5, "C", False, False, False, False),
        )
        self.assertEqual(
            canvas.calls[1],
            ("add_or_update_atom_label", 5, "N", False, False, False, True),
        )

    def test_change_atom_label_command_prefers_atom_label_service_when_available(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas.services.atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: (
                service_calls.append((atom_id, text, kwargs))
            )
        )
        command = ChangeAtomLabelCommand(
            atom_id=7,
            before_element="C",
            after_element="Cl",
            before_explicit_label=False,
            after_explicit_label=False,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        command.redo(canvas)

        self.assertEqual(
            service_calls,
            [
                (
                    7,
                    "Cl",
                    {
                        "clear_smiles": False,
                        "record": False,
                        "allow_merge": False,
                        "show_carbon": False,
                    },
                )
            ],
        )
        self.assertEqual(canvas.calls, [])
        self.assertEqual(canvas.last_smiles_input, "after")

    def test_bond_commands_remove_trim_and_restore(self) -> None:
        canvas = _FakeCanvas()
        add_command = AddBondCommand(
            bond_id=2,
            bond_state={"order": 1},
            previous_bond_count=5,
            before_smiles_input="before-add",
            after_smiles_input="after-add",
        )
        delete_command = DeleteBondCommand(
            bond_id=3,
            bond_state={"order": 2},
            before_smiles_input="before-delete",
            after_smiles_input="after-delete",
        )
        update_command = UpdateBondCommand(
            bond_id=4,
            before_state={"order": 1},
            after_state={"order": 3},
            before_smiles_input="before-update",
            after_smiles_input="after-update",
        )

        add_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before-add")
        add_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after-add")

        delete_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before-delete")
        delete_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after-delete")

        update_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before-update")
        update_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after-update")

        self.assertIn(("remove_bond_for_history", 2), canvas.calls)
        self.assertIn(("trim_bonds_for_history", 5), canvas.calls)
        self.assertIn(("restore_bond_from_state", 2, {"order": 1}), canvas.calls)
        self.assertIn(("restore_bond_from_state", 3, {"order": 2}), canvas.calls)
        self.assertIn(("restore_bond_from_state", 4, {"order": 1}), canvas.calls)
        self.assertIn(("restore_bond_from_state", 4, {"order": 3}), canvas.calls)


if __name__ == "__main__":
    unittest.main()
