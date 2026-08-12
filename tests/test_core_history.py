import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
    MoveAtomsCommand,
    RestoreOutcome,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    SetSmilesInputCommand,
    UpdateAtomColorCommand,
    UpdateBondCommand,
    UpdateBondLengthCommand,
)
from chemvas.domain.document import Atom
from chemvas.ui.atom_coords_access import (
    CanvasAtomCoords3DState,
    atom_coords_3d_for,
    set_atom_coords_3d_for,
)
from chemvas.ui.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_smiles_input_state import (
    CanvasSmilesInputState,
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
from tests.runtime_state import canvas_runtime_state


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
        self.runtime_state = canvas_runtime_state(
            smiles_input_state=CanvasSmilesInputState(),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            atom_graphics_state=CanvasAtomGraphicsState(),
            bond_graphics_state=CanvasBondGraphicsState(),
            mark_registry=SimpleNamespace(get_for_atom=lambda _atom_id: []),
            rotation_state=CanvasRotationState(
                projection_center_3d="before-center",
                projection_anchor_2d="before-anchor",
            ),
        )
        self.last_smiles_input = None
        self.model = SimpleNamespace(
            next_atom_id=0, atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]
        )
        self.atom_coords_3d = {}
        self._scene_obj = object()
        self.renderer = _FakeRenderer(self)
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
        self.runtime_state.rotation_state = CanvasRotationState()


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

    def release_history_transaction_for_history(
        self,
        _canvas,
        _snapshot,
    ) -> None:
        pass

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
            ) -> RestoreOutcome:
                del canvas, snapshot
                self.restore_calls += 1
                return RestoreOutcome(
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
            ) -> RestoreOutcome:
                canvas.bonds = deepcopy(snapshot["bonds"])
                canvas.smiles_input = snapshot["smiles_input"]
                return RestoreOutcome(
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
            ) -> RestoreOutcome:
                # Simulate a full best-effort pass that restored one absolute
                # field but hit a persistent critical setter on another.
                canvas.smiles_input = snapshot["smiles_input"]
                return RestoreOutcome(
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
                self.release_calls = 0

            def capture_history_transaction_for_history(self, canvas, **_kwargs):
                self.capture_calls += 1
                return canvas.bond_length

            def restore_history_transaction_for_history(
                self,
                canvas,
                snapshot,
            ) -> RestoreOutcome:
                canvas.bond_length = snapshot
                return RestoreOutcome(authoritative=True)

            def release_history_transaction_for_history(
                self,
                _canvas,
                _snapshot,
            ) -> None:
                self.release_calls += 1

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
        self.assertEqual(port.release_calls, 2)

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

    def test_history_service_drops_mixed_composite_after_failed_child(
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

        # The document savepoint cannot prove coverage of an unknown child,
        # so the conservative policy drops the command and clears redo.
        self.assertEqual(_atomic_canvas_snapshot(canvas), before)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

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
            ) -> RestoreOutcome:
                del canvas, snapshot
                return RestoreOutcome(
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

        with (
            mock.patch("chemvas.core.history._history_canvas_port", return_value=port),
            mock.patch(
                "chemvas.ui.history_canvas_access."
                "restore_history_transaction_for_history",
                return_value=RestoreOutcome(
                    authoritative=False,
                    fallback_to_inverse=False,
                    errors=(RuntimeError("persistent exact restore failure"),),
                ),
            ),
        ):
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
        self.assertEqual(
            canvas.runtime_state.rotation_state.projection_center_3d, (5.0, 6.0, 7.0)
        )
        self.assertEqual(
            canvas.runtime_state.rotation_state.projection_anchor_2d, (8.0, 9.0)
        )

        command.undo(canvas)
        self.assertIsNone(canvas.runtime_state.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.runtime_state.rotation_state.projection_anchor_2d)

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
        self.assertIsNone(canvas.runtime_state.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.runtime_state.rotation_state.projection_anchor_2d)

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
        self.assertEqual(
            canvas.runtime_state.rotation_state.projection_center_3d, (1.0, 2.0, 3.0)
        )
        self.assertEqual(
            canvas.runtime_state.rotation_state.projection_anchor_2d, (1.0, 2.0)
        )
        self.assertEqual(atom_coords_3d_for(canvas)[3], (1.0, 2.0, 3.0))

        command.redo(canvas)
        self.assertIsNone(canvas.runtime_state.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.runtime_state.rotation_state.projection_anchor_2d)

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
