import copy
import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.core.history import SetAtomPositionsCommand
from chemvas.domain.document import Atom, Bond, MoleculeModel

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.ui.atom_coords_access import CanvasAtomCoords3DState
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.selection_collection_access import selected_ids_for
from chemvas.ui.selection_outline_state import selection_outlines_for
from chemvas.ui.selection_rotation_controller import SelectionRotationController
from chemvas.ui.selection_rotation_preview_transaction import (
    _CoreStateSnapshot,
    run_rotation_preview_update,
)
from chemvas.ui.structure_mutation_access import (
    add_atom_for,
    add_benzene_ring_for,
    add_bond_for,
)
from PyQt6 import sip
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
)


class _BrokenAddNoteInterrupt(KeyboardInterrupt):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


class _BrokenAddNoteSystemExit(SystemExit):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


class _BrokenAddNoteLookupInterrupt(KeyboardInterrupt):
    def __getattribute__(self, name: str):
        if name == "add_note":
            raise SystemExit("add_note lookup failed")
        return super().__getattribute__(name)


class _BrokenAddNoteLookupSystemExit(SystemExit):
    def __getattribute__(self, name: str):
        if name == "add_note":
            raise KeyboardInterrupt("add_note lookup failed")
        return super().__getattribute__(name)


class _CountingBonds(list):
    def __init__(self, bonds) -> None:
        super().__init__(bonds)
        self.iteration_count = 0
        self.yield_count = 0

    def __iter__(self):
        self.iteration_count += 1
        for bond in super().__iter__():
            self.yield_count += 1
            yield bond

    def reset_counts(self) -> None:
        self.iteration_count = 0
        self.yield_count = 0


def _fail_once_property_holder(attribute: str, value: object):
    def read(holder):
        holder.read_count += 1
        if holder.read_count == 1:
            raise AttributeError(f"{attribute} live property failed")
        return holder.value

    holder_type = type(
        f"_FailOnce_{attribute}",
        (),
        {attribute: property(read)},
    )
    holder = holder_type()
    holder.read_count = 0
    holder.value = value
    return holder


def _fail_once_method_property_item(
    base_type,
    attribute: str,
    *constructor_args,
):
    base_method = getattr(base_type, attribute)

    def read(item):
        item.attribute_reads += 1
        if item.attribute_failures:
            item.attribute_failures -= 1
            raise AttributeError(f"{attribute} live property failed")
        return lambda: base_method(item)

    item_type = type(
        f"_FailOnce_{base_type.__name__}_{attribute}",
        (base_type,),
        {attribute: property(read)},
    )
    item = item_type(*constructor_args)
    item.attribute_reads = 0
    item.attribute_failures = 0
    return item


class _FailOnceHistoryState:
    def __init__(
        self,
        fail_field: str,
        history: list,
        redo_stack: list,
    ) -> None:
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
    def __init__(
        self,
        fail_field: str,
        *,
        history: list,
        redo_stack: list,
    ) -> None:
        self.fail_field = fail_field
        self.state_reads = 0
        self._state = _FailOnceHistoryState(
            fail_field,
            history,
            redo_stack,
        )
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


class _FakeSceneItem:
    def __init__(self, kind: str, payload=None) -> None:
        self.kind = kind
        self.payload = payload
        self._selected = True
        self._scene = None
        self._pos = QPointF()
        self.set_pos_error: BaseException | None = None

    def data(self, key: int):
        if key == 0:
            return self.kind
        if key == 1:
            return self.payload
        if key == 2 and self.kind == "ring":
            return self.payload
        return None

    def isSelected(self) -> bool:
        return self._selected

    def setSelected(self, selected: bool) -> None:
        self._selected = selected

    def scene(self):
        return self._scene

    def pos(self) -> QPointF:
        return QPointF(self._pos)

    def setPos(self, pos: QPointF) -> None:
        if self.set_pos_error is not None:
            raise self.set_pos_error
        self._pos = QPointF(pos)


class _StackingFakeSceneItem(_FakeSceneItem):
    def parentItem(self):
        return None

    def zValue(self) -> float:
        return 0.0


class _FakeScene:
    def __init__(self, selected_items: list[_FakeSceneItem] | None = None) -> None:
        self._selected_items = list(selected_items or [])
        self.items_call_count = 0
        self.selected_items_call_count = 0
        self._signals_blocked = False
        self.signals_blocked_error: BaseException | None = None
        self.block_signals_calls: list[bool] = []
        self.block_signals_errors: dict[bool, BaseException] = {}
        for item in self._selected_items:
            item._scene = self

    def selectedItems(self) -> list[_FakeSceneItem]:
        self.selected_items_call_count += 1
        return [item for item in self._selected_items if item.isSelected()]

    def items(self) -> list[_FakeSceneItem]:
        self.items_call_count += 1
        return list(self._selected_items)

    def addItem(self, item: _FakeSceneItem) -> None:
        if item not in self._selected_items:
            # QGraphicsScene.items() is top-most first; a newly attached
            # equal-z item stacks above existing siblings.
            self._selected_items.insert(0, item)
        item._scene = self

    def removeItem(self, item: _FakeSceneItem) -> None:
        if item in self._selected_items:
            self._selected_items.remove(item)
        item._scene = None

    def signalsBlocked(self) -> bool:
        if self.signals_blocked_error is not None:
            raise self.signals_blocked_error
        return self._signals_blocked

    def blockSignals(self, blocked: bool) -> bool:
        previous = self._signals_blocked
        self._signals_blocked = blocked
        self.block_signals_calls.append(blocked)
        error = self.block_signals_errors.get(blocked)
        if error is not None:
            raise error
        return previous


class _RestoreRetryScene(_FakeScene):
    def __init__(self, *, mutate_before_raise: bool) -> None:
        super().__init__()
        self.mutate_before_raise = mutate_before_raise
        self.restore_failures = 1

    def blockSignals(self, blocked: bool) -> bool:
        if not blocked and self.restore_failures:
            self.restore_failures -= 1
            if self.mutate_before_raise:
                super().blockSignals(blocked)
            else:
                self.block_signals_calls.append(blocked)
            raise SystemExit("scene signal restoration failed once")
        return super().blockSignals(blocked)


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
                2: Atom("O", 20.0, 5.0),
            },
            bonds=[Bond(0, 1), Bond(1, 2)],
        )
        self.atom_coords_3d_state = CanvasAtomCoords3DState(
            atom_coords_3d={
                0: (0.0, 0.0, 0.0),
                1: (10.0, 0.0, 0.0),
                2: (20.0, 5.0, 3.0),
            }
        )
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self._scene = _FakeScene()
        self._selected_atom_ids: set[int] = set()
        self._selected_bond_ids: set[int] = set()
        self.axis_hint_response: tuple[int, set[int]] | None = None
        self.flattened_coords: dict[int, tuple[float, float, float]] | None = None

        self.rotation_state = CanvasRotationState(
            projection_center_3d=(100.0, 200.0, 300.0),
            projection_anchor_2d=(50.0, 60.0),
            start_coords_3d={999: (1.0, 1.0, 1.0)},
            coord_atom_ids={999},
        )

        self.axis_hint_calls: list[tuple[int, set[int], QPointF | None]] = []
        self.flatten_calls: list[
            tuple[set[int], dict[int, tuple[float, float, float]]]
        ] = []
        self.average_bond_length_calls: list[
            tuple[set[int], dict[int, tuple[float, float, float]]]
        ] = []
        self.unproject_calls: list[
            tuple[
                tuple[float, float],
                float,
                tuple[float, float, float],
                tuple[float, float],
            ]
        ] = []
        self.apply_projected_calls: list[
            tuple[set[int], dict[int, tuple[float, float, float]]]
        ] = []
        self.redraw_calls: list[set[int]] = []
        self.ring_fill_calls: list[set[int]] = []
        self.selection_outline_updates = 0
        self.rotate_axis_calls: list[
            tuple[
                tuple[float, float, float],
                tuple[float, float, float],
                tuple[float, float, float],
                float,
            ]
        ] = []
        self.pushed_commands: list[SetAtomPositionsCommand] = []
        self.history_state = SimpleNamespace(
            history=self.pushed_commands,
            redo_stack=[],
            enabled=True,
            limit=100,
        )
        self.history_service = SimpleNamespace(
            state=self.history_state,
            push=self.push_command,
        )
        self.restore_selection_calls: list[tuple[set[int], set[int]]] = []
        self.selection_info_emits = 0
        self.services = canvas_runtime_services(
            history_service=self.history_service,
            move_controller=SimpleNamespace(
                redraw_bonds_for_atoms=self.record_redraw_bonds_for_atoms
            ),
            canvas_graph_service=SimpleNamespace(
                axis_from_rotation_hint=self.axis_from_rotation_hint
            ),
        )

    def scene(self) -> _FakeScene:
        return self._scene

    @property
    def atom_coords_3d(self):
        return self.atom_coords_3d_state.atom_coords_3d

    @atom_coords_3d.setter
    def atom_coords_3d(self, value) -> None:
        self.atom_coords_3d_state.atom_coords_3d = value

    @property
    def selected_atom_ids(self) -> set[int]:
        return set(self._selected_atom_ids)

    @selected_atom_ids.setter
    def selected_atom_ids(self, atom_ids: set[int]) -> None:
        self._selected_atom_ids = set(atom_ids)
        self._sync_selection_scene()

    @property
    def selected_bond_ids(self) -> set[int]:
        return set(self._selected_bond_ids)

    @selected_bond_ids.setter
    def selected_bond_ids(self, bond_ids: set[int]) -> None:
        self._selected_bond_ids = set(bond_ids)
        self._sync_selection_scene()

    def _sync_selection_scene(self) -> None:
        self._scene = _FakeScene(
            [
                _FakeSceneItem("atom", atom_id)
                for atom_id in sorted(self._selected_atom_ids)
            ]
            + [
                _FakeSceneItem("bond", bond_id)
                for bond_id in sorted(self._selected_bond_ids)
            ]
        )

    def axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        press_pos: QPointF | None = None,
    ) -> tuple[int, set[int]] | None:
        self.axis_hint_calls.append((axis_hint, set(rotation_atom_ids), press_pos))
        return self.axis_hint_response

    def record_redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        self.redraw_calls.append(set(atom_ids))

    def refresh_selection_outline(self) -> None:
        self.selection_outline_updates += 1

    def push_command(self, command: SetAtomPositionsCommand) -> None:
        self.pushed_commands.append(command)

    def restore_selection_from_ids(
        self, atom_ids: set[int], bond_ids: set[int]
    ) -> None:
        self.restore_selection_calls.append((set(atom_ids), set(bond_ids)))

    def emit_selection_info(self) -> None:
        self.selection_info_emits += 1


class _FailOnceSceneFakeCanvas(_FakeCanvas):
    def __init__(self) -> None:
        self.scene_property_failures = 0
        self.scene_property_reads = 0
        super().__init__()

    @property
    def scene(self):
        self.scene_property_reads += 1
        if self.scene_property_failures:
            self.scene_property_failures -= 1
            raise AttributeError("scene live property failed")
        return lambda: self._scene


class _FailOnceSceneCanvasView(CanvasView):
    def __init__(self) -> None:
        self.scene_property_failures = 0
        self.scene_property_reads = 0
        super().__init__()

    @property
    def scene(self):
        self.scene_property_reads += 1
        if self.scene_property_failures:
            self.scene_property_failures -= 1
            raise AttributeError("scene live property failed")
        return super().scene


class _FakeSelectionRotationPorts:
    def __init__(self, canvas: _FakeCanvas) -> None:
        self.canvas = canvas

    def selected_ids(self):
        return self.canvas.selected_atom_ids, self.canvas.selected_bond_ids

    def selected_scene_items(self):
        return self.canvas.scene().selectedItems()

    @property
    def atoms(self):
        return self.canvas.model.atoms

    @property
    def bonds(self):
        return self.canvas.model.bonds

    def atom(self, atom_id: int):
        return self.canvas.model.atoms.get(atom_id)

    def bond(self, bond_id: int):
        if (
            not isinstance(bond_id, int)
            or bond_id < 0
            or bond_id >= len(self.canvas.model.bonds)
        ):
            return None
        return self.canvas.model.bonds[bond_id]

    def atom_positions(self, atom_ids: set[int]) -> dict[int, tuple[float, float]]:
        return {
            atom_id: (atom.x, atom.y)
            for atom_id in atom_ids
            for atom in [self.atom(atom_id)]
            if atom is not None
        }

    def axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        *,
        press_pos: QPointF | None = None,
    ) -> tuple[int, set[int]] | None:
        return self.canvas.axis_from_rotation_hint(
            axis_hint, rotation_atom_ids, press_pos=press_pos
        )

    def current_atom_coords_3d(self, atom_id: int):
        atom = self.atom(atom_id)
        if atom is None:
            return None
        return self.canvas.atom_coords_3d.get(atom_id, (atom.x, atom.y, 0.0))

    def flatten_planar_fragments(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> dict[int, tuple[float, float, float]]:
        self.canvas.flatten_calls.append((set(atom_ids), dict(coords)))
        if self.canvas.flattened_coords is not None:
            return dict(self.canvas.flattened_coords)
        return dict(coords)

    def average_bond_length_for_atoms(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> float:
        self.canvas.average_bond_length_calls.append((set(atom_ids), dict(coords)))
        return 12.5

    def unproject_scene_point_3d(
        self,
        point: QPointF,
        z: float,
        *,
        center_3d: tuple[float, float, float],
        anchor_2d: tuple[float, float],
    ) -> tuple[float, float, float]:
        self.canvas.unproject_calls.append(
            ((point.x(), point.y()), z, center_3d, anchor_2d)
        )
        return (point.x() + 0.5, point.y() - 0.25, z + 1.0)

    def apply_projected_atom_positions(
        self,
        atom_ids: set[int],
        rotated_coords: dict[int, tuple[float, float, float]],
    ) -> None:
        self.canvas.apply_projected_calls.append((set(atom_ids), dict(rotated_coords)))
        for atom_id, (x, y, z) in rotated_coords.items():
            self.canvas.atom_coords_3d[atom_id] = (x, y, z)
            atom = self.canvas.model.atoms[atom_id]
            atom.x = x
            atom.y = y

    def refresh_atom_geometry(self, atom_ids: set[int]) -> None:
        self.canvas.record_redraw_bonds_for_atoms(atom_ids)
        self.canvas.ring_fill_calls.append(set(atom_ids))
        self.canvas.refresh_selection_outline()

    def rotate_point_around_axis(
        self,
        coords: tuple[float, float, float],
        axis_start: tuple[float, float, float],
        axis_end: tuple[float, float, float],
        angle: float,
    ) -> tuple[float, float, float]:
        self.canvas.rotate_axis_calls.append((coords, axis_start, axis_end, angle))
        return (coords[0] + angle, coords[1] - angle, coords[2] + 0.5)

    def restore_selection_from_ids(
        self, atom_ids: set[int], bond_ids: set[int]
    ) -> None:
        self.canvas.restore_selection_from_ids(atom_ids, bond_ids)

    def emit_selection_info(self) -> None:
        self.canvas.emit_selection_info()


def _controller_for(canvas: _FakeCanvas) -> SelectionRotationController:
    controller = SelectionRotationController(
        canvas,
        move_controller=canvas.services.interaction.move_controller,
        graph_service=canvas.services.graph.canvas_graph_service,
        history_service=canvas.services.history_service,
    )
    ports = _FakeSelectionRotationPorts(canvas)
    for name in (
        "selected_ids",
        "selected_scene_items",
        "atom",
        "bond",
        "atom_positions",
        "axis_from_rotation_hint",
        "current_atom_coords_3d",
        "flatten_planar_fragments",
        "average_bond_length_for_atoms",
        "unproject_scene_point_3d",
        "apply_projected_atom_positions",
        "refresh_atom_geometry",
        "rotate_point_around_axis",
        "restore_selection_from_ids",
        "emit_selection_info",
    ):
        setattr(controller, name, getattr(ports, name))
    return controller


class SelectionRotationControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_begin_selection_3d_rotation_returns_false_without_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=1)

        self.assertFalse(rotating)
        self.assertEqual(
            canvas.rotation_state.start_coords_3d,
            {999: (1.0, 1.0, 1.0)},
        )
        self.assertEqual(canvas.rotation_state.coord_atom_ids, {999})
        self.assertEqual(canvas.axis_hint_calls, [])

    def test_begin_selection_3d_rotation_skips_non_mark_and_invalid_mark_items(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas._scene = _FakeScene(
            [
                _FakeSceneItem("atom"),
                _FakeSceneItem("mark", {"atom_id": "bad"}),
                _FakeSceneItem("mark", {"atom_id": 2}),
            ]
        )
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [])
        self.assertEqual(canvas.rotation_state.atom_ids, {2})

    def test_begin_selection_3d_rotation_uses_axis_hint_bond_path(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (0, {2})
        canvas.flattened_coords = {
            0: (0.0, 0.0, 1.0),
            1: (10.0, 0.0, 3.0),
            2: (22.0, 7.0, 5.0),
        }
        controller = _controller_for(canvas)
        press_pos = QPointF(14.0, 9.0)

        rotating = controller.begin_selection_3d_rotation(
            axis_hint=7, press_pos=press_pos
        )

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(7, {2}, press_pos)])
        self.assertEqual(canvas.rotation_state.mode, "bond")
        self.assertEqual(canvas.rotation_state.axis_bond_id, 0)
        self.assertEqual(canvas.rotation_state.axis_atoms, (0, 1))
        self.assertEqual(canvas.rotation_state.atom_ids, {2})
        self.assertEqual(canvas.rotation_state.selection_ids, ({2}, set()))
        self.assertEqual(canvas.rotation_state.start_positions, {2: (20.0, 5.0)})
        self.assertEqual(canvas.rotation_state.center_3d, (5.0, 0.0, 2.0))
        self.assertEqual(canvas.rotation_state.projection_center_3d, (5.0, 0.0, 2.0))
        self.assertEqual(canvas.rotation_state.projection_anchor_2d, (5.0, 0.0))
        self.assertEqual(
            canvas.rotation_state.start_projection_center_3d, (100.0, 200.0, 300.0)
        )
        self.assertEqual(canvas.rotation_state.start_projection_anchor_2d, (50.0, 60.0))
        self.assertEqual(canvas.rotation_state.coord_atom_ids, {0, 1, 2})
        self.assertEqual(canvas.rotation_state.base_coords, canvas.flattened_coords)
        self.assertEqual(canvas.atom_coords_3d[2], (22.0, 7.0, 5.0))
        self.assertEqual(
            canvas.average_bond_length_calls,
            [({0, 1, 2}, dict(canvas.flattened_coords))],
        )

    def test_begin_selection_3d_rotation_falls_back_to_rigid_mode(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {0}
        canvas.selected_bond_ids = {1}
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation(
            axis_hint=4, press_pos=QPointF(2.0, 3.0)
        )

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(4, {0, 1, 2}, QPointF(2.0, 3.0))])
        self.assertEqual(canvas.rotation_state.mode, "rigid")
        self.assertIsNone(canvas.rotation_state.axis_bond_id)
        self.assertIsNone(canvas.rotation_state.axis_atoms)
        self.assertEqual(canvas.rotation_state.atom_ids, {0, 1, 2})
        self.assertEqual(canvas.rotation_state.selection_ids, ({0}, {1}))
        self.assertEqual(canvas.rotation_state.center_3d, (10.0, 2.5, 1.0))
        self.assertEqual(canvas.rotation_state.projection_center_3d, (10.0, 2.5, 1.0))
        self.assertEqual(canvas.rotation_state.projection_anchor_2d, (10.0, 2.5))
        self.assertEqual(
            canvas.rotation_state.start_positions,
            {0: (0.0, 0.0), 1: (10.0, 0.0), 2: (20.0, 5.0)},
        )
        self.assertEqual(
            canvas.unproject_calls,
            [
                ((0.0, 0.0), 0.0, (10.0, 2.5, 1.0), (10.0, 2.5)),
                ((10.0, 0.0), 0.0, (10.0, 2.5, 1.0), (10.0, 2.5)),
                ((20.0, 5.0), 3.0, (10.0, 2.5, 1.0), (10.0, 2.5)),
            ],
        )
        self.assertEqual(canvas.rotation_state.base_coords[0], (0.5, -0.25, 1.0))
        self.assertEqual(canvas.rotation_state.base_coords[2], (20.5, 4.75, 4.0))
        self.assertEqual(
            canvas.average_bond_length_calls,
            [({0, 1, 2}, dict(canvas.rotation_state.base_coords))],
        )

    def test_begin_selection_3d_rotation_promotes_selected_marks_to_atom_ids(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas._scene = _FakeScene([_FakeSceneItem("mark", {"atom_id": 2})])
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [])
        self.assertEqual(canvas.rotation_state.mode, "rigid")
        self.assertEqual(canvas.rotation_state.atom_ids, {2})
        self.assertEqual(canvas.rotation_state.selection_ids, (set(), set()))
        self.assertEqual(canvas.rotation_state.start_positions, {2: (20.0, 5.0)})
        self.assertEqual(canvas.rotation_state.coord_atom_ids, {2})
        self.assertEqual(canvas.rotation_state.center_3d, (20.0, 5.0, 3.0))
        self.assertEqual(canvas.rotation_state.projection_anchor_2d, (20.0, 5.0))
        self.assertEqual(canvas.rotation_state.base_coords, {2: (20.5, 4.75, 4.0)})
        self.assertEqual(canvas.atom_coords_3d[2], (20.5, 4.75, 4.0))
        self.assertEqual(
            canvas.average_bond_length_calls,
            [({2}, dict(canvas.rotation_state.base_coords))],
        )

    def test_begin_selection_3d_rotation_returns_false_for_missing_axis_bond(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (1, {2})
        canvas.model.bonds[1] = None
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=3)

        self.assertFalse(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(3, {2}, None)])
        self.assertIsNone(canvas.rotation_state.selection_ids)
        self.assertEqual(canvas.rotation_state.atom_ids, set())

    def test_begin_selection_3d_rotation_uses_axis_center_anchor_when_axis_atom_is_missing(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (0, {2, 99})
        del canvas.model.atoms[1]
        canvas.flattened_coords = {
            0: (0.0, 0.0, 1.0),
            1: (10.0, 0.0, 3.0),
            2: (22.0, 7.0, 5.0),
        }
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=6)

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(6, {2}, None)])
        self.assertEqual(canvas.rotation_state.atom_ids, {2, 99})
        self.assertNotIn(99, canvas.rotation_state.base_coords)
        self.assertEqual(canvas.rotation_state.projection_anchor_2d, (5.0, 0.0))
        self.assertEqual(
            canvas.average_bond_length_calls,
            [({0, 1, 2, 99}, dict(canvas.flattened_coords))],
        )

    def test_begin_selection_3d_rotation_returns_false_when_axis_path_flattens_to_empty(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (0, {2})
        canvas.flattened_coords = {}
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=1)

        self.assertFalse(rotating)
        self.assertEqual(canvas.rotation_state.coord_atom_ids, {999})
        self.assertEqual(canvas.rotation_state.base_coords, {})
        self.assertEqual(canvas.rotation_state.atom_ids, set())

    def test_begin_selection_3d_rotation_returns_false_without_projectable_coords(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.selected_bond_ids = {1, 99}
        canvas.model.bonds[1] = None
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertFalse(rotating)
        self.assertIsNone(canvas.rotation_state.selection_ids)
        self.assertEqual(
            canvas.rotation_state.start_coords_3d,
            {999: (1.0, 1.0, 1.0)},
        )

    def test_begin_selection_3d_rotation_uses_planar_coords_when_rotation_atoms_have_no_stored_coords(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {0}
        canvas.atom_coords_3d = {}
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertEqual(canvas.rotation_state.selection_ids, ({0}, set()))
        self.assertEqual(canvas.rotation_state.start_coords_3d, {0: (0.0, 0.0, 0.0)})
        self.assertEqual(canvas.rotation_state.coord_atom_ids, {0})
        self.assertEqual(canvas.rotation_state.atom_ids, {0})
        self.assertEqual(canvas.rotation_state.mode, "rigid")
        self.assertEqual(canvas.atom_coords_3d[0], (0.5, -0.25, 1.0))

    def test_begin_selection_3d_rotation_skips_missing_atoms_during_rigid_unprojection(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {1, 2}
        del canvas.model.atoms[1]
        controller = _controller_for(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertNotIn(1, canvas.rotation_state.base_coords)
        self.assertIn(2, canvas.rotation_state.base_coords)

    def test_update_selection_3d_rotation_noops_without_atoms_and_updates_rigid_rotation(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)

        controller.update_selection_3d_rotation(40.0, 25.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_state.atom_ids = {0, 2}
        canvas.rotation_state.mode = "rigid"
        canvas.rotation_state.center_3d = (0.0, 0.0, 0.0)
        canvas.rotation_state.base_coords = {
            0: (1.0, 0.0, 0.0),
            2: (0.0, 2.0, 0.0),
        }

        controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertAlmostEqual(canvas.rotation_state.free_angle_x, 0.1)
        self.assertAlmostEqual(canvas.rotation_state.free_angle_y, 0.2)
        self.assertEqual(len(canvas.apply_projected_calls), 1)
        atom_ids, rotated = canvas.apply_projected_calls[0]
        self.assertEqual(atom_ids, {0, 2})
        cos_y = math.cos(0.2)
        sin_y = math.sin(0.2)
        cos_x = math.cos(0.1)
        sin_x = math.sin(0.1)
        expected_atom_0 = (
            1.0 * cos_y,
            -(-1.0 * sin_y) * sin_x,
            (-1.0 * sin_y) * cos_x,
        )
        expected_atom_2 = (
            0.0,
            2.0 * cos_x,
            2.0 * sin_x,
        )
        self.assertAlmostEqual(rotated[0][0], expected_atom_0[0])
        self.assertAlmostEqual(rotated[0][1], expected_atom_0[1])
        self.assertAlmostEqual(rotated[0][2], expected_atom_0[2])
        self.assertAlmostEqual(rotated[2][0], expected_atom_2[0])
        self.assertAlmostEqual(rotated[2][1], expected_atom_2[1])
        self.assertAlmostEqual(rotated[2][2], expected_atom_2[2])
        self.assertEqual(canvas.redraw_calls, [{0, 2}])
        self.assertEqual(canvas.ring_fill_calls, [{0, 2}])
        self.assertEqual(canvas.selection_outline_updates, 1)
        self.assertEqual(canvas.scene().items_call_count, 1)

    def test_preview_session_scans_full_document_once_for_many_frames(self) -> None:
        canvas = _FakeCanvas()
        for atom_id in range(3, 1_000):
            canvas.model.atoms[atom_id] = Atom(
                "C",
                float(atom_id),
                float(atom_id % 17),
            )
            canvas.atom_coords_3d[atom_id] = (
                float(atom_id),
                float(atom_id % 17),
                0.0,
            )
        canvas.selected_atom_ids = {2}
        scene = canvas.scene()
        controller = _controller_for(canvas)

        with mock.patch.object(
            _CoreStateSnapshot,
            "capture",
            wraps=_CoreStateSnapshot.capture,
        ) as full_capture:
            self.assertTrue(controller.begin_selection_3d_rotation())
            for _frame in range(100):
                controller.update_selection_3d_rotation(1.0, 1.0)

        self.assertEqual(full_capture.call_count, 1)
        self.assertEqual(scene.items_call_count, 1)
        self.assertEqual(len(canvas.apply_projected_calls), 100)

    def test_actual_preview_frames_scan_only_selected_bond_adjacency(self) -> None:
        canvas = CanvasView()
        try:
            previous_atom_id = add_atom_for(canvas, "C", 0.0, 0.0)
            for atom_index in range(1, 1_001):
                atom_id = add_atom_for(
                    canvas,
                    "C",
                    float(atom_index * 20),
                    0.0,
                )
                add_bond_for(canvas, previous_atom_id, atom_id)
                previous_atom_id = atom_id

            counting_bonds = _CountingBonds(canvas.model.bonds)
            canvas.model.bonds = counting_bonds
            selected_item = visible_atom_item_for(canvas, 0)
            self.assertIsNotNone(selected_item)
            selected_item.setSelected(True)
            self.app.processEvents()
            controller = canvas.services.interaction.selection_rotation_controller

            counting_bonds.reset_counts()
            self.assertTrue(controller.begin_selection_3d_rotation())
            # Session setup may validate/rebuild the document-wide graph once.
            self.assertLessEqual(counting_bonds.yield_count, 1_000)

            counting_bonds.reset_counts()
            for _frame in range(100):
                controller.update_selection_3d_rotation(1.0, 1.0)

            # One selected endpoint has degree one. Across 100 frames the
            # bond work must stay O(frames * selected degree), never O(document).
            self.assertLessEqual(counting_bonds.yield_count, 100)
            controller.end_selection_3d_rotation()
        finally:
            schedule_canvas_deletion_for(canvas)
            self.app.processEvents()

    def test_preview_failure_restores_last_successful_rolling_checkpoint(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        controller = _controller_for(canvas)
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        rotation_before_failure = copy.deepcopy(canvas.rotation_state)
        atom_2_before_failure = copy.deepcopy(canvas.model.atoms[2])
        coords_before_failure = canvas.atom_coords_3d[2]
        atom_0_before_failure = copy.deepcopy(canvas.model.atoms[0])
        coords_0_before_failure = canvas.atom_coords_3d[0]
        successful_refresh = controller.refresh_atom_geometry
        primary = KeyboardInterrupt("rolling preview callback failed")

        def poison_unrelated_state_then_fail(_atom_ids: set[int]) -> None:
            canvas.model.atoms[0].x = 999.0
            canvas.model.atoms[0].y = 888.0
            canvas.atom_coords_3d[0] = (999.0, 888.0, 777.0)
            raise primary

        controller.refresh_atom_geometry = poison_unrelated_state_then_fail
        with self.assertRaises(KeyboardInterrupt) as raised:
            controller.update_selection_3d_rotation(30.0, 15.0)

        self.assertIs(raised.exception, primary)
        self.assertEqual(canvas.rotation_state, rotation_before_failure)
        self.assertEqual(canvas.model.atoms[2], atom_2_before_failure)
        self.assertEqual(canvas.atom_coords_3d[2], coords_before_failure)
        self.assertEqual(canvas.model.atoms[0], atom_0_before_failure)
        self.assertEqual(canvas.atom_coords_3d[0], coords_0_before_failure)
        self.assertIsNone(controller._rotation_preview_authority)
        self.assertIsNone(controller._rotation_transaction.preview)

        controller.refresh_atom_geometry = successful_refresh
        controller.update_selection_3d_rotation(30.0, 15.0)
        self.assertAlmostEqual(
            canvas.rotation_state.free_angle_x,
            rotation_before_failure.free_angle_x + 0.075,
        )
        self.assertAlmostEqual(
            canvas.rotation_state.free_angle_y,
            rotation_before_failure.free_angle_y + 0.15,
        )

    def test_rolling_checkpoint_restores_replaced_outline_membership_and_order(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        unaffected = _StackingFakeSceneItem("shape")
        initial_outline = _StackingFakeSceneItem("selection_outline")
        scene = _FakeScene([unaffected, initial_outline])
        canvas._scene = scene
        initial_outlines = [initial_outline]
        outline_state = SimpleNamespace(outlines=initial_outlines)
        canvas.selection_outline_state = outline_state
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        controller = _controller_for(canvas)
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (20.0, 5.0, 3.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}
        generated: list[_StackingFakeSceneItem] = []
        primary = KeyboardInterrupt("outline replacement failed")

        def replace_outline(_atom_ids: set[int]) -> None:
            for outline in list(outline_state.outlines):
                scene.removeItem(outline)
            replacement = _StackingFakeSceneItem("selection_outline")
            generated.append(replacement)
            scene.addItem(replacement)
            outline_state.outlines = [replacement]
            if len(generated) == 2:
                raise primary

        controller.refresh_atom_geometry = replace_outline
        controller.update_selection_3d_rotation(20.0, 10.0)
        successful_outlines = outline_state.outlines
        successful_outline = generated[0]
        order_before_failure = list(scene.items())

        with self.assertRaises(KeyboardInterrupt) as raised:
            controller.update_selection_3d_rotation(30.0, 15.0)

        self.assertIs(raised.exception, primary)
        self.assertIs(outline_state.outlines, successful_outlines)
        self.assertEqual(outline_state.outlines, [successful_outline])
        self.assertIs(successful_outline.scene(), scene)
        self.assertIsNone(initial_outline.scene())
        self.assertIsNone(generated[1].scene())
        self.assertEqual(scene.items(), order_before_failure)

    def test_refresh_atom_geometry_updates_bonds_in_place_when_port_is_available(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        update_geometries = mock.Mock()
        redraw_bonds = mock.Mock(
            side_effect=AssertionError("rotation should not replace bond items")
        )
        controller.move_controller = SimpleNamespace(
            update_bond_geometries_for_atoms=update_geometries,
            redraw_bonds_for_atoms=redraw_bonds,
        )

        with (
            mock.patch(
                "chemvas.ui.selection_rotation_controller.update_ring_fills_for_atoms_for"
            ) as update_rings,
            mock.patch(
                "chemvas.ui.selection_rotation_controller.refresh_selection_outline_for"
            ) as refresh_outline,
        ):
            SelectionRotationController.refresh_atom_geometry(controller, {0, 2})

        update_geometries.assert_called_once_with({0, 2})
        redraw_bonds.assert_not_called()
        update_rings.assert_called_once_with(canvas, {0, 2})
        refresh_outline.assert_called_once_with(canvas)

    def test_update_selection_3d_rotation_rotates_bond_mode_atoms(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {2}
        canvas.rotation_state.mode = "bond"
        canvas.rotation_state.axis_atoms = (0, 1)
        canvas.rotation_state.base_coords = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
            2: (20.0, 5.0, 3.0),
        }

        controller.update_selection_3d_rotation(30.0, 10.0)

        self.assertAlmostEqual(canvas.rotation_state.total_angle, 0.15)
        self.assertEqual(
            canvas.rotate_axis_calls,
            [((20.0, 5.0, 3.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), 0.15)],
        )
        self.assertEqual(len(canvas.apply_projected_calls), 1)
        atom_ids, rotated = canvas.apply_projected_calls[0]
        self.assertEqual(atom_ids, {2})
        self.assertEqual(rotated, {2: (20.15, 4.85, 3.5)})
        self.assertEqual(canvas.redraw_calls, [{2}])
        self.assertEqual(canvas.ring_fill_calls, [{2}])
        self.assertEqual(canvas.selection_outline_updates, 1)

    def test_update_selection_3d_rotation_handles_zero_angles_and_missing_axis_data(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {0}

        canvas.rotation_state.mode = "rigid"
        canvas.rotation_state.center_3d = (0.0, 0.0, 0.0)
        canvas.rotation_state.base_coords = {0: (1.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(0.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_state.atom_ids = {0, 9}
        canvas.rotation_state.base_coords = {0: (1.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(len(canvas.apply_projected_calls), 1)
        atom_ids, rotated = canvas.apply_projected_calls[0]
        self.assertEqual(atom_ids, {0, 9})
        self.assertEqual(set(rotated), {0})

        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {0}
        canvas.rotation_state.mode = "rigid"
        canvas.rotation_state.center_3d = None
        canvas.rotation_state.base_coords = {0: (1.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

    def test_update_selection_3d_rotation_handles_bond_mode_zero_delta_and_missing_axis_data(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {2}
        canvas.rotation_state.mode = "bond"
        canvas.rotation_state.axis_atoms = (0, 1)

        controller.update_selection_3d_rotation(0.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_state.axis_atoms = None
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_state.axis_atoms = (0, 1)
        canvas.rotation_state.base_coords = {0: (0.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_state.base_coords = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        canvas.rotation_state.atom_ids = {2, 9}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(len(canvas.apply_projected_calls), 1)
        atom_ids, rotated = canvas.apply_projected_calls[0]
        self.assertEqual(atom_ids, {2, 9})
        self.assertEqual(rotated, {})

        zero_canvas = _FakeCanvas()
        zero_controller = _controller_for(zero_canvas)
        zero_canvas.rotation_state.atom_ids = {2}
        zero_canvas.rotation_state.mode = "bond"
        zero_canvas.rotation_state.axis_atoms = (0, 1)
        zero_controller.update_selection_3d_rotation(0.0, 0.0)
        self.assertEqual(zero_canvas.apply_projected_calls, [])

        missing_axis_canvas = _FakeCanvas()
        missing_axis_controller = _controller_for(missing_axis_canvas)
        missing_axis_canvas.rotation_state.atom_ids = {2}
        missing_axis_canvas.rotation_state.mode = "bond"
        missing_axis_canvas.rotation_state.axis_atoms = (0, 1)
        missing_axis_canvas.rotation_state.base_coords = {0: (0.0, 0.0, 0.0)}
        missing_axis_controller.update_selection_3d_rotation(10.0, 5.0)
        self.assertEqual(missing_axis_canvas.apply_projected_calls, [])

        partial_coords_canvas = _FakeCanvas()
        partial_coords_controller = _controller_for(partial_coords_canvas)
        partial_coords_canvas.rotation_state.atom_ids = {0, 2}
        partial_coords_canvas.rotation_state.mode = "bond"
        partial_coords_canvas.rotation_state.axis_atoms = (0, 1)
        partial_coords_canvas.rotation_state.base_coords = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        partial_coords_controller.update_selection_3d_rotation(10.0, 5.0)
        self.assertEqual(
            partial_coords_canvas.apply_projected_calls[-1],
            ({0, 2}, {0: (0.05, -0.05, 0.5)}),
        )

    def test_preview_update_failures_restore_rigid_and_bond_state_before_retry(
        self,
    ) -> None:
        cases = (
            ("rigid", "apply", KeyboardInterrupt),
            ("rigid", "refresh", SystemExit),
            ("bond", "apply", SystemExit),
            ("bond", "refresh", KeyboardInterrupt),
        )
        for mode, failure_stage, error_type in cases:
            with self.subTest(mode=mode, failure_stage=failure_stage):
                canvas = _FakeCanvas()
                controller = _controller_for(canvas)
                state = canvas.rotation_state
                if mode == "rigid":
                    canvas.selected_atom_ids = {0, 2}
                    state.atom_ids = {0, 2}
                    state.mode = "rigid"
                    state.center_3d = (0.0, 0.0, 0.0)
                    state.base_coords = {
                        0: (1.0, 0.0, 0.0),
                        2: (0.0, 2.0, 0.0),
                    }
                    delta = (40.0, 20.0)
                else:
                    canvas.selected_atom_ids = {2}
                    state.atom_ids = {2}
                    state.mode = "bond"
                    state.axis_atoms = (0, 1)
                    state.base_coords = {
                        0: (0.0, 0.0, 0.0),
                        1: (10.0, 0.0, 0.0),
                        2: (20.0, 5.0, 3.0),
                    }
                    delta = (30.0, 10.0)

                selected_item = canvas.scene().selectedItems()[0]
                scene = canvas.scene()
                canvas.atom_graphics_state = SimpleNamespace(
                    atom_items={selected_item.payload: selected_item},
                    atom_dots={},
                )
                affected_bond_id = 0 if mode == "rigid" else 1
                old_bond_item = _FakeSceneItem("bond", affected_bond_id)
                old_bond_item.setPos(QPointF(10.0, 11.0))
                old_bond_items = [old_bond_item]
                bond_mapping = {affected_bond_id: old_bond_items}
                canvas.bond_graphics_state = SimpleNamespace(bond_items=bond_mapping)
                old_outline = _FakeSceneItem("selection_outline")
                old_outline.setPos(QPointF(12.0, 13.0))
                old_outlines = [old_outline]
                canvas.selection_outline_state = SimpleNamespace(outlines=old_outlines)
                ring_item = _FakeSceneItem("ring", list(state.atom_ids))
                ring_item.setPos(QPointF(14.0, 15.0))
                canvas.scene_items_state = SimpleNamespace(ring_items=[ring_item])
                canvas.selection_info_state = SimpleNamespace(
                    signature="before",
                    pending_signature="pending-before",
                    cache=("formula", "mass"),
                    rdkit_warmup_pending=True,
                    last_interaction_time=1.25,
                )
                for runtime_item in (old_bond_item, old_outline, ring_item):
                    scene.addItem(runtime_item)
                scene_items_before = scene.items()
                scene.items_call_count = 0
                scene.selected_items_call_count = 0
                rotation_before = copy.deepcopy(state)
                positions_before = controller.atom_positions(set(state.atom_ids))
                coords_object = canvas.atom_coords_3d
                coords_before = dict(coords_object)
                real_apply = controller.apply_projected_atom_positions
                real_refresh = controller.refresh_atom_geometry
                transient_items: list[_FakeSceneItem] = []
                injected_error = error_type(
                    f"injected {mode} {failure_stage} preview failure"
                )

                def mutate_scene_runtime(
                    rotation_state=state,
                    scene_item=selected_item,
                    scene_ref=scene,
                ) -> None:
                    rotation_state.projection_center_3d = (999.0, 998.0, 997.0)
                    rotation_state.projection_anchor_2d = (996.0, 995.0)
                    scene_item.setSelected(False)
                    scene_item.setPos(QPointF(991.0, 992.0))
                    scene_ref.removeItem(scene_item)

                def mutate_refresh_runtime(
                    scene_ref=scene,
                    mapping=bond_mapping,
                    bond_id=affected_bond_id,
                    bond_item=old_bond_item,
                    outline=old_outline,
                    outline_state=canvas.selection_outline_state,
                    ring=ring_item,
                    selection_info=canvas.selection_info_state,
                    created=transient_items,
                ) -> None:
                    new_bond_item = _FakeSceneItem("bond", bond_id)
                    new_outline = _FakeSceneItem("selection_outline")
                    created.extend((new_bond_item, new_outline))
                    bond_item.setPos(QPointF(981.0, 982.0))
                    outline.setPos(QPointF(983.0, 984.0))
                    ring.setPos(QPointF(985.0, 986.0))
                    scene_ref.removeItem(bond_item)
                    scene_ref.removeItem(outline)
                    mapping[bond_id] = [new_bond_item]
                    outline_state.outlines = [new_outline]
                    scene_ref.addItem(new_bond_item)
                    scene_ref.addItem(new_outline)
                    selection_info.signature = "after"
                    selection_info.pending_signature = "pending-after"
                    selection_info.cache = ("changed", "changed")
                    selection_info.rdkit_warmup_pending = False
                    selection_info.last_interaction_time = 99.0

                def apply_then_fail(
                    atom_ids,
                    rotated_coords,
                    apply_positions=real_apply,
                    error=injected_error,
                ) -> None:
                    first_atom_id = min(rotated_coords)
                    apply_positions(
                        {first_atom_id},
                        {first_atom_id: rotated_coords[first_atom_id]},
                    )
                    mutate_scene_runtime()
                    raise error

                def refresh_then_fail(
                    atom_ids,
                    refresh=real_refresh,
                    error=injected_error,
                ) -> None:
                    refresh(atom_ids)
                    mutate_refresh_runtime()
                    mutate_scene_runtime()
                    raise error

                if failure_stage == "apply":
                    controller.apply_projected_atom_positions = apply_then_fail
                else:
                    controller.refresh_atom_geometry = refresh_then_fail

                with self.assertRaisesRegex(error_type, "preview failure") as raised:
                    controller.update_selection_3d_rotation(*delta)

                self.assertIs(raised.exception, injected_error)
                self.assertEqual(state, rotation_before)
                self.assertEqual(
                    controller.atom_positions(set(state.atom_ids)),
                    positions_before,
                )
                self.assertIs(canvas.atom_coords_3d, coords_object)
                self.assertEqual(canvas.atom_coords_3d, coords_before)
                # Exact stacking rollback captures the complete ordered scene;
                # the exceptional path then scans and verifies that authority.
                self.assertGreaterEqual(scene.items_call_count, 2)
                self.assertEqual(scene.selected_items_call_count, 0)
                self.assertFalse(scene.signalsBlocked())
                self.assertEqual(
                    scene.block_signals_calls,
                    [True, False],
                )
                self.assertEqual(
                    {id(item) for item in scene.items()},
                    {id(item) for item in scene_items_before},
                )
                self.assertIs(selected_item.scene(), scene)
                self.assertTrue(selected_item.isSelected())
                self.assertEqual(selected_item.pos(), QPointF())
                self.assertIs(canvas.bond_graphics_state.bond_items, bond_mapping)
                self.assertIs(bond_mapping[affected_bond_id], old_bond_items)
                self.assertEqual(old_bond_items, [old_bond_item])
                self.assertEqual(old_bond_item.pos(), QPointF(10.0, 11.0))
                self.assertIs(canvas.selection_outline_state.outlines, old_outlines)
                self.assertEqual(old_outlines, [old_outline])
                self.assertEqual(old_outline.pos(), QPointF(12.0, 13.0))
                self.assertEqual(ring_item.pos(), QPointF(14.0, 15.0))
                self.assertEqual(canvas.selection_info_state.signature, "before")
                self.assertEqual(
                    canvas.selection_info_state.pending_signature,
                    "pending-before",
                )
                self.assertEqual(
                    canvas.selection_info_state.cache,
                    ("formula", "mass"),
                )
                self.assertTrue(canvas.selection_info_state.rdkit_warmup_pending)
                self.assertEqual(
                    canvas.selection_info_state.last_interaction_time,
                    1.25,
                )
                for transient_item in transient_items:
                    self.assertIsNone(transient_item.scene())

                controller.apply_projected_atom_positions = real_apply
                controller.refresh_atom_geometry = real_refresh
                controller.update_selection_3d_rotation(*delta)

                if mode == "rigid":
                    self.assertAlmostEqual(state.free_angle_x, 0.1)
                    self.assertAlmostEqual(state.free_angle_y, 0.2)
                else:
                    self.assertAlmostEqual(state.total_angle, 0.15)
                self.assertNotEqual(
                    controller.atom_positions(set(state.atom_ids)),
                    positions_before,
                )

    def test_preview_rollback_preserves_primary_and_continues_after_persistent_failures(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.selected_atom_ids = {2}
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (0.0, 0.0, 0.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}

        selected_item = canvas.scene().selectedItems()[0]
        selected_item.setPos(QPointF(1.0, 2.0))
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: selected_item},
            atom_dots={},
        )
        ring_item = _FakeSceneItem("ring", [2])
        ring_item.setPos(QPointF(3.0, 4.0))
        canvas.scene_items_state = SimpleNamespace(ring_items=[ring_item])
        canvas.scene().addItem(ring_item)
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])

        rotation_before = copy.deepcopy(state)
        positions_before = controller.atom_positions({2})
        coords_object = canvas.atom_coords_3d
        coords_before = dict(coords_object)
        scene = canvas.scene()
        signal_error = SystemExit("signal blocking mutate-then-failure")
        scene.block_signals_errors[True] = signal_error
        graphics_error = SystemExit("persistent graphics restore failure")
        primary_error = KeyboardInterrupt("primary rotation preview failure")
        real_apply = controller.apply_projected_atom_positions

        def apply_then_fail(atom_ids, rotated_coords) -> None:
            real_apply(atom_ids, rotated_coords)
            selected_item._pos = QPointF(91.0, 92.0)
            selected_item.set_pos_error = graphics_error
            ring_item._pos = QPointF(93.0, 94.0)
            raise primary_error

        controller.apply_projected_atom_positions = apply_then_fail

        with self.assertRaises(KeyboardInterrupt) as raised:
            controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertIs(raised.exception, primary_error)
        self.assertEqual(state, rotation_before)
        self.assertEqual(controller.atom_positions({2}), positions_before)
        self.assertIs(canvas.atom_coords_3d, coords_object)
        self.assertEqual(canvas.atom_coords_3d, coords_before)
        self.assertFalse(scene.signalsBlocked())
        self.assertGreaterEqual(scene.block_signals_calls.count(True), 1)
        self.assertGreaterEqual(scene.block_signals_calls.count(False), 1)
        self.assertEqual(selected_item.pos(), QPointF(91.0, 92.0))
        self.assertEqual(ring_item.pos(), QPointF(3.0, 4.0))
        notes = getattr(primary_error, "__notes__", [])
        self.assertTrue(
            any("signal blocking mutate-then-failure" in note for note in notes)
        )
        self.assertTrue(
            any(
                "restoring rotation-preview graphics" in note
                and "persistent graphics restore failure" in note
                for note in notes
            )
        )

        scene.block_signals_errors.clear()
        selected_item.set_pos_error = None
        controller.apply_projected_atom_positions = real_apply
        controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertAlmostEqual(state.free_angle_x, 0.1)
        self.assertAlmostEqual(state.free_angle_y, 0.2)

    def test_preview_failure_scan_continues_after_unreadable_fake_transient(
        self,
    ) -> None:
        class _UnreadableTransient(_FakeSceneItem):
            def data(self, key: int):
                raise SystemExit(f"persistent fake data failure for role {key}")

        class _UnreadableLookupTransient(_FakeSceneItem):
            @property
            def data(self):
                raise KeyboardInterrupt("persistent fake data lookup failure")

        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        controller = _controller_for(canvas)
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (0.0, 0.0, 0.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}
        selected_item = canvas.scene().selectedItems()[0]
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: selected_item},
            atom_dots={},
        )
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        scene = canvas.scene()
        unreadable = _UnreadableTransient("bond", 1)
        lookup_unreadable = _UnreadableLookupTransient("bond", 1)
        removable = _FakeSceneItem("selection_outline")
        primary_error = KeyboardInterrupt("primary fake preview failure")

        def refresh_then_fail(_atom_ids) -> None:
            # addItem prepends, so the unreadable item is scanned first.
            scene.addItem(removable)
            scene.addItem(unreadable)
            scene.addItem(lookup_unreadable)
            raise primary_error

        controller.refresh_atom_geometry = refresh_then_fail

        with self.assertRaises(KeyboardInterrupt) as raised:
            controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertIs(raised.exception, primary_error)
        self.assertIsNone(removable.scene())
        # The full ordered-scene savepoint removes post-capture objects by
        # identity even when their role metadata cannot be classified.
        self.assertIsNone(unreadable.scene())
        self.assertIsNone(lookup_unreadable.scene())

    def test_fake_live_ring_data_failure_aborts_before_preview_mutation(self) -> None:
        class _FailOnceRing(_FakeSceneItem):
            failures = 1

            def data(self, key: int):
                if key == 2 and self.failures:
                    self.failures -= 1
                    raise RuntimeError("fake live ring data capture failed")
                return super().data(key)

        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        controller = _controller_for(canvas)
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (0.0, 0.0, 0.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}
        selected_item = canvas.scene().selectedItems()[0]
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: selected_item},
            atom_dots={},
        )
        ring = _FailOnceRing("ring", [2])
        canvas.scene().addItem(ring)
        canvas.scene_items_state = SimpleNamespace(ring_items=[ring])
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        positions_before = controller.atom_positions({2})
        real_apply = controller.apply_projected_atom_positions
        controller.apply_projected_atom_positions = mock.Mock(side_effect=real_apply)

        with self.assertRaisesRegex(RuntimeError, "fake live ring data capture failed"):
            controller.update_selection_3d_rotation(40.0, 20.0)

        controller.apply_projected_atom_positions.assert_not_called()
        self.assertEqual(controller.atom_positions({2}), positions_before)

        controller.update_selection_3d_rotation(40.0, 20.0)

        controller.apply_projected_atom_positions.assert_called_once()
        self.assertNotEqual(controller.atom_positions({2}), positions_before)

    def test_real_qt_ring_capture_aborts_live_failure_and_skips_deleted_wrapper(
        self,
    ) -> None:
        class _FailOnceRing(QGraphicsPolygonItem):
            failures = 1

            def data(self, role: int):
                if role == 2 and self.failures:
                    self.failures -= 1
                    raise TypeError("live Qt ring data capture failed")
                return super().data(role)

        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        scene = QGraphicsScene()
        canvas._scene = scene
        controller = _controller_for(canvas)
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (0.0, 0.0, 0.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}
        atom_item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        atom_item.setData(0, "atom")
        atom_item.setData(1, 2)
        scene.addItem(atom_item)
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: atom_item},
            atom_dots={},
        )
        ring = _FailOnceRing(
            QPolygonF(
                [
                    QPointF(0.0, 0.0),
                    QPointF(5.0, 0.0),
                    QPointF(2.5, 4.0),
                ]
            )
        )
        ring.setData(0, "ring")
        ring.setData(2, [2])
        scene.addItem(ring)
        deleted_ring = QGraphicsPolygonItem()
        deleted_ring.setData(0, "ring")
        deleted_ring.setData(2, [2])
        sip.delete(deleted_ring)
        canvas.scene_items_state = SimpleNamespace(ring_items=[ring, deleted_ring])
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        positions_before = controller.atom_positions({2})
        real_apply = controller.apply_projected_atom_positions
        controller.apply_projected_atom_positions = mock.Mock(side_effect=real_apply)

        with self.assertRaisesRegex(TypeError, "live Qt ring data capture failed"):
            controller.update_selection_3d_rotation(40.0, 20.0)

        controller.apply_projected_atom_positions.assert_not_called()
        self.assertEqual(controller.atom_positions({2}), positions_before)

        controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertTrue(sip.isdeleted(deleted_ring))
        controller.apply_projected_atom_positions.assert_called_once()
        self.assertNotEqual(controller.atom_positions({2}), positions_before)

    def test_preview_capture_rejects_present_unreadable_state_descriptors(
        self,
    ) -> None:
        capture_fields = (
            ("bond_graphics_state", "bond_items"),
            ("selection_outline_state", "outlines"),
            ("atom_graphics_state", "atom_items"),
            ("atom_graphics_state", "atom_dots"),
            ("mark_registry", "by_atom"),
            ("scene_items_state", "ring_items"),
            ("selection_info_state", "signature"),
            ("selection_info_state", "pending_signature"),
            ("selection_info_state", "cache"),
            ("selection_info_state", "rdkit_warmup_pending"),
            ("selection_info_state", "last_interaction_time"),
        )

        for canvas_kind in ("fake", "actual"):
            with self.subTest(canvas=canvas_kind):
                if canvas_kind == "fake":
                    canvas = _FailOnceSceneFakeCanvas()
                    canvas.bond_graphics_state = SimpleNamespace(bond_items={})
                    canvas.selection_outline_state = SimpleNamespace(outlines=[])
                    canvas.atom_graphics_state = SimpleNamespace(
                        atom_items={},
                        atom_dots={},
                    )
                    canvas.mark_registry = SimpleNamespace(by_atom={})
                    canvas.scene_items_state = SimpleNamespace(ring_items=[])
                    canvas.selection_info_state = SimpleNamespace(
                        signature=None,
                        pending_signature=None,
                        cache=("", ""),
                        rdkit_warmup_pending=False,
                        last_interaction_time=0.0,
                    )
                    controller = _controller_for(canvas)
                    state_owner = canvas
                else:
                    canvas = _FailOnceSceneCanvasView()
                    controller = (
                        canvas.services.interaction.selection_rotation_controller
                    )
                    state_owner = canvas.runtime_state

                scene = canvas.scene()
                canvas.scene_property_reads = 0
                canvas.scene_property_failures = 1
                apply = mock.Mock()
                try:
                    with self.assertRaisesRegex(
                        AttributeError,
                        "scene",
                    ):
                        run_rotation_preview_update(controller, set(), apply)

                    apply.assert_not_called()
                    self.assertEqual(canvas.scene_property_reads, 1)
                    self.assertFalse(scene.signalsBlocked())
                    if isinstance(scene, _FakeScene):
                        self.assertEqual(scene.block_signals_calls, [])

                    run_rotation_preview_update(controller, set(), apply)

                    apply.assert_called_once_with()
                    self.assertEqual(canvas.scene_property_reads, 2)
                    self.assertFalse(scene.signalsBlocked())

                    for state_name, attribute in capture_fields:
                        with self.subTest(
                            canvas=canvas_kind,
                            state=state_name,
                            attribute=attribute,
                        ):
                            original_state = getattr(state_owner, state_name)
                            holder = _fail_once_property_holder(
                                attribute,
                                getattr(original_state, attribute),
                            )
                            setattr(state_owner, state_name, holder)
                            apply = mock.Mock()
                            try:
                                with self.assertRaisesRegex(
                                    AttributeError,
                                    f"{attribute} live property failed",
                                ):
                                    run_rotation_preview_update(
                                        controller,
                                        set(),
                                        apply,
                                    )

                                apply.assert_not_called()
                                self.assertEqual(holder.read_count, 1)
                                self.assertFalse(scene.signalsBlocked())
                                if isinstance(scene, _FakeScene):
                                    self.assertEqual(scene.block_signals_calls, [])

                                run_rotation_preview_update(
                                    controller,
                                    set(),
                                    apply,
                                )

                                apply.assert_called_once_with()
                                self.assertEqual(holder.read_count, 2)
                                self.assertFalse(scene.signalsBlocked())
                            finally:
                                setattr(state_owner, state_name, original_state)
                finally:
                    if canvas_kind == "actual":
                        schedule_canvas_deletion_for(canvas)
                        self.app.processEvents()

    def test_preview_capture_rejects_present_unreadable_item_methods(self) -> None:
        for canvas_kind in ("fake", "actual"):
            for attribute in ("parentItem", "zValue", "isSelected", "scene"):
                with self.subTest(canvas=canvas_kind, attribute=attribute):
                    if canvas_kind == "fake":
                        canvas = _FakeCanvas()
                        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
                        canvas.atom_graphics_state = SimpleNamespace(
                            atom_items={},
                            atom_dots={},
                        )
                        canvas.mark_registry = SimpleNamespace(by_atom={})
                        canvas.scene_items_state = SimpleNamespace(ring_items=[])
                        canvas.selection_info_state = SimpleNamespace()
                        outline_state = SimpleNamespace(outlines=[])
                        canvas.selection_outline_state = outline_state
                        controller = _controller_for(canvas)
                        scene = canvas.scene()
                        item = _fail_once_method_property_item(
                            _StackingFakeSceneItem,
                            attribute,
                            "selection_outline",
                        )
                    else:
                        canvas = CanvasView()
                        controller = (
                            canvas.services.interaction.selection_rotation_controller
                        )
                        scene = canvas.scene()
                        outline_state = canvas.runtime_state.selection_outline_state
                        item = _fail_once_method_property_item(
                            QGraphicsRectItem,
                            attribute,
                            0.0,
                            0.0,
                            10.0,
                            10.0,
                        )

                    scene.addItem(item)
                    original_outlines = outline_state.outlines
                    outline_state.outlines = [item]
                    item.attribute_reads = 0
                    item.attribute_failures = 1
                    apply = mock.Mock()
                    try:
                        if canvas_kind == "actual" and attribute == "parentItem":
                            run_rotation_preview_update(controller, set(), apply)

                            apply.assert_called_once_with()
                            self.assertEqual(item.attribute_reads, 0)
                            self.assertFalse(scene.signalsBlocked())
                            continue
                        with self.assertRaisesRegex(
                            AttributeError,
                            f"{attribute} live property failed",
                        ):
                            run_rotation_preview_update(controller, set(), apply)

                        apply.assert_not_called()
                        self.assertEqual(item.attribute_reads, 1)
                        self.assertFalse(scene.signalsBlocked())
                        if isinstance(scene, _FakeScene):
                            self.assertEqual(scene.block_signals_calls, [])

                        run_rotation_preview_update(controller, set(), apply)

                        apply.assert_called_once_with()
                        self.assertGreaterEqual(item.attribute_reads, 2)
                        self.assertFalse(scene.signalsBlocked())
                    finally:
                        outline_state.outlines = original_outlines
                        scene.removeItem(item)
                        if canvas_kind == "actual":
                            schedule_canvas_deletion_for(canvas)
                            self.app.processEvents()

    def test_preview_capture_allows_truly_absent_optional_fake_state(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        apply = mock.Mock()
        scene = canvas.scene()

        run_rotation_preview_update(controller, set(), apply)

        apply.assert_called_once_with()
        self.assertFalse(scene.signalsBlocked())
        self.assertEqual(scene.block_signals_calls, [])

    def test_preview_capture_fails_closed_when_signal_state_is_unreadable(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.selected_atom_ids = {2}
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (0.0, 0.0, 0.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}
        selected_item = canvas.scene().selectedItems()[0]
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: selected_item},
            atom_dots={},
        )
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        scene = canvas.scene()
        scene.signals_blocked_error = RuntimeError("signal-state unavailable")
        scene.block_signals_errors[True] = SystemExit(
            "blockSignals would mutate before raising"
        )
        apply = mock.Mock()
        controller.apply_projected_atom_positions = apply

        with self.assertRaisesRegex(RuntimeError, "signal-state unavailable"):
            controller.update_selection_3d_rotation(40.0, 20.0)

        apply.assert_not_called()
        self.assertFalse(scene._signals_blocked)
        self.assertEqual(scene.block_signals_calls, [])

    def test_actual_preview_failure_restores_auto_scene_rect_last_and_retries(
        self,
    ) -> None:
        class FailOnceAutomaticRestoreScene(QGraphicsScene):
            fail_null_restores = 0

            def setSceneRect(self, *args) -> None:
                if len(args) == 1:
                    rect = args[0]
                else:
                    rect = tuple(args)
                super().setSceneRect(*args)
                candidate = rect if hasattr(rect, "isNull") else None
                if (
                    candidate is not None
                    and candidate.isNull()
                    and self.fail_null_restores
                ):
                    self.fail_null_restores -= 1
                    raise SystemExit(
                        "automatic scene rect restore failed after mutation"
                    )

        canvas = _FakeCanvas()
        scene = FailOnceAutomaticRestoreScene()
        atom_item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        atom_item.setData(0, "atom")
        atom_item.setData(1, 2)
        scene.addItem(atom_item)
        canvas._scene = scene
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: atom_item},
            atom_dots={},
        )
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        canvas.selection_info_state = SimpleNamespace()
        controller = _controller_for(canvas)
        baseline_rect = scene.sceneRect()
        baseline_pos = atom_item.pos()
        primary = KeyboardInterrupt("preview terminated after far mutation")

        def move_far_then_interrupt() -> None:
            atom_item.setPos(25_000.0, 0.0)
            # While the guard is active, even an eager Qt read cannot poison
            # the grow-only automatic cache with the temporary far geometry.
            self.assertEqual(scene.sceneRect(), baseline_rect)
            scene.fail_null_restores = 1
            raise primary

        with self.assertRaises(KeyboardInterrupt) as raised:
            run_rotation_preview_update(
                controller,
                {2},
                move_far_then_interrupt,
            )

        self.assertIs(raised.exception, primary)
        self.assertEqual(atom_item.pos(), baseline_pos)
        self.assertEqual(scene.sceneRect(), baseline_rect)
        self.assertTrue(scene._chemvas_scene_rect_automatic)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)
        self.assertTrue(
            any(
                "restoring the rotation-preview scene rect" in note
                for note in getattr(primary, "__notes__", [])
            )
        )

        future = scene.addRect(50_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 50_000.0)
        scene.removeItem(future)

        run_rotation_preview_update(
            controller,
            {2},
            lambda: atom_item.setPos(30_000.0, 0.0),
        )
        self.assertGreater(scene.sceneRect().right(), 30_000.0)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

    def test_preview_signal_restore_confirms_state_and_retries_once(self) -> None:
        cases = (
            (
                False,
                _BrokenAddNoteLookupInterrupt("preview interrupted"),
                [True, False, True, False],
            ),
            (True, RuntimeError("preview failed"), [True, False]),
        )
        for mutate_before_raise, primary_error, expected_calls in cases:
            with self.subTest(mutate_before_raise=mutate_before_raise):
                canvas = _FakeCanvas()
                scene = _RestoreRetryScene(
                    mutate_before_raise=mutate_before_raise,
                )
                canvas._scene = scene
                controller = _controller_for(canvas)

                def fail_preview(error: BaseException = primary_error) -> None:
                    raise error

                with self.assertRaises(type(primary_error)) as raised:
                    run_rotation_preview_update(controller, set(), fail_preview)

                self.assertIs(raised.exception, primary_error)
                self.assertFalse(scene.signalsBlocked())
                self.assertEqual(
                    scene.block_signals_calls,
                    expected_calls,
                )
                self.assertEqual(scene.restore_failures, 0)
                if isinstance(primary_error, RuntimeError):
                    self.assertTrue(
                        any(
                            "scene signal restoration failed once" in note
                            for note in primary_error.__notes__
                        )
                    )

                update = mock.Mock()
                run_rotation_preview_update(controller, set(), update)
                update.assert_called_once_with()

    def test_real_qt_stacking_rollback_continues_after_broken_first_item(self) -> None:
        class _BrokenFirstItem(QGraphicsRectItem):
            parent_lookup_broken = False

            def parentItem(self):
                if self.parent_lookup_broken:
                    raise KeyboardInterrupt("persistent first parent lookup failure")
                return super().parentItem()

        canvas = CanvasView()
        scene = canvas.scene()
        controller = canvas.services.interaction.selection_rotation_controller
        first = _BrokenFirstItem(0.0, 0.0, 10.0, 10.0)
        later = QGraphicsRectItem(20.0, 0.0, 10.0, 10.0)
        highest = QGraphicsRectItem(40.0, 0.0, 10.0, 10.0)
        items = [first, later, highest]
        for item in items:
            item.setZValue(5.0)
            scene.addItem(item)
        outline_state = canvas.runtime_state.selection_outline_state
        original_outlines = outline_state.outlines
        outline_state.outlines = items
        before_later_order = [
            item for item in scene.items() if item in {later, highest}
        ]
        primary_error = _BrokenAddNoteLookupSystemExit("actual preview terminated")

        def reorder_then_fail() -> None:
            for item in items:
                scene.removeItem(item)
            for item in reversed(items):
                scene.addItem(item)
            later.setParentItem(highest)
            later.setZValue(-3.0)
            highest.setZValue(9.0)
            first.parent_lookup_broken = True
            raise primary_error

        try:
            with self.assertRaises(_BrokenAddNoteLookupSystemExit) as raised:
                run_rotation_preview_update(
                    controller,
                    set(),
                    reorder_then_fail,
                )

            self.assertIs(raised.exception, primary_error)
            self.assertTrue(first.parent_lookup_broken)
            self.assertEqual(
                [item for item in scene.items() if item in {later, highest}],
                before_later_order,
            )
            self.assertIsNone(later.parentItem())
            self.assertEqual(later.zValue(), 5.0)
            self.assertEqual(highest.zValue(), 5.0)
            self.assertFalse(scene.signalsBlocked())

            first.parent_lookup_broken = False
            update = mock.Mock()
            run_rotation_preview_update(controller, set(), update)
            update.assert_called_once_with()
        finally:
            first.parent_lookup_broken = False
            outline_state.outlines = original_outlines
            schedule_canvas_deletion_for(canvas)
            self.app.processEvents()

    def test_real_qt_rollback_removes_unpublished_bond_and_restores_stacking(
        self,
    ) -> None:
        class _FailingTransientBondItem(QGraphicsRectItem):
            def __init__(self) -> None:
                super().__init__(0.0, 0.0, 30.0, 30.0)
                self.membership_failures = 1

            def data(self, role: int):
                if role == 0:
                    raise SystemExit("live Qt transient data failure")
                return super().data(role)

            def scene(self):
                if self.membership_failures:
                    self.membership_failures -= 1
                    raise KeyboardInterrupt("live Qt transient membership failure")
                return super().scene()

        canvas = _FakeCanvas()
        scene = QGraphicsScene()
        canvas._scene = scene
        controller = _controller_for(canvas)
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.mode = "rigid"
        state.center_3d = (0.0, 0.0, 0.0)
        state.base_coords = {2: (20.0, 5.0, 3.0)}

        atom_item = QGraphicsRectItem(0.0, 0.0, 30.0, 30.0)
        atom_item.setData(0, "atom")
        atom_item.setData(1, 2)
        scene.addItem(atom_item)
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: atom_item},
            atom_dots={},
        )

        old_bond_item = QGraphicsRectItem(0.0, 0.0, 30.0, 30.0)
        old_bond_item.setData(0, "bond")
        old_bond_item.setData(1, 1)
        unrelated_bond_item = QGraphicsRectItem(0.0, 0.0, 30.0, 30.0)
        unrelated_bond_item.setData(0, "bond")
        unrelated_bond_item.setData(1, 0)
        scene.addItem(old_bond_item)
        scene.addItem(unrelated_bond_item)
        old_bond_items = [old_bond_item]
        bond_mapping = {0: [unrelated_bond_item], 1: old_bond_items}
        canvas.bond_graphics_state = SimpleNamespace(bond_items=bond_mapping)
        old_outline = QGraphicsRectItem(0.0, 0.0, 30.0, 30.0)
        old_outline.setData(0, "selection_outline")
        old_outline.setZValue(19.0)
        higher_outline = QGraphicsRectItem(0.0, 0.0, 30.0, 30.0)
        higher_outline.setData(0, "selection_outline")
        higher_outline.setZValue(19.0)
        scene.addItem(old_outline)
        scene.addItem(higher_outline)
        old_outlines = [old_outline, higher_outline]
        outline_state = SimpleNamespace(outlines=old_outlines)
        canvas.selection_outline_state = outline_state
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        before_order = [
            item for item in scene.items() if item in {old_outline, higher_outline}
        ]
        transient_bond_item = _FailingTransientBondItem()
        transient_bond_item.setData(0, "bond")
        transient_bond_item.setData(1, 1)
        transient_outline = QGraphicsRectItem(0.0, 0.0, 30.0, 30.0)
        transient_outline.setData(0, "selection_outline")
        transient_outline.setZValue(19.0)
        primary_error = RuntimeError("publish interrupted")

        def refresh_then_fail(_atom_ids) -> None:
            bond_mapping[1] = []
            # BondGraphicsBuildService attaches every primitive before it
            # publishes the completed list to bond_items.  This models a later
            # primitive failing after an earlier one already reached the scene.
            scene.addItem(transient_bond_item)
            scene.removeItem(old_outline)
            outline_state.outlines = []
            scene.addItem(transient_outline)
            raise primary_error

        controller.refresh_atom_geometry = refresh_then_fail

        with self.assertRaises(RuntimeError) as raised:
            controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertIs(raised.exception, primary_error)
        self.assertIsNone(transient_bond_item.scene())
        self.assertIsNone(transient_outline.scene())
        self.assertIs(old_bond_item.scene(), scene)
        self.assertIs(old_outline.scene(), scene)
        self.assertIs(bond_mapping[1], old_bond_items)
        self.assertIs(outline_state.outlines, old_outlines)
        self.assertEqual(
            [item for item in scene.items() if item in {old_outline, higher_outline}],
            before_order,
        )

    def test_end_selection_3d_rotation_pushes_command_and_restores_selection(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {0, 2}
        canvas.rotation_state.center_3d = (3.0, 4.0, 5.0)
        canvas.rotation_state.selection_ids = ({0, 2}, {1})
        canvas.rotation_state.base_coords = {0: (0.0, 0.0, 0.0)}
        canvas.rotation_state.total_angle = 1.2
        canvas.rotation_state.mode = "rigid"
        canvas.rotation_state.free_angle_x = 0.3
        canvas.rotation_state.free_angle_y = 0.4
        canvas.rotation_state.base_bond_length = 9.0
        canvas.rotation_state.axis_bond_id = 1
        canvas.rotation_state.axis_atoms = (1, 2)
        canvas.rotation_state.start_positions = {0: (0.0, 0.0), 2: (20.0, 5.0)}
        canvas.rotation_state.start_coords_3d = {
            0: (0.0, 0.0, 0.0),
            2: (20.0, 5.0, 3.0),
        }
        canvas.rotation_state.start_projection_center_3d = (1.0, 2.0, 3.0)
        canvas.rotation_state.start_projection_anchor_2d = (4.0, 5.0)
        canvas.rotation_state.coord_atom_ids = {0, 2}
        canvas.rotation_state.projection_center_3d = (7.0, 8.0, 9.0)
        canvas.rotation_state.projection_anchor_2d = (11.0, 12.0)
        canvas.atom_coords_3d[0] = (1.0, 1.5, 2.0)
        canvas.atom_coords_3d[2] = (22.0, 6.5, 4.5)
        canvas.model.atoms[0].x = 1.0
        canvas.model.atoms[0].y = 1.5
        canvas.model.atoms[2].x = 22.0
        canvas.model.atoms[2].y = 6.5

        controller.end_selection_3d_rotation()

        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, SetAtomPositionsCommand)
        self.assertEqual(command.before_positions, {0: (0.0, 0.0), 2: (20.0, 5.0)})
        self.assertEqual(command.after_positions, {0: (1.0, 1.5), 2: (22.0, 6.5)})
        self.assertEqual(
            command.before_coords_3d, {0: (0.0, 0.0, 0.0), 2: (20.0, 5.0, 3.0)}
        )
        self.assertEqual(
            command.after_coords_3d, {0: (1.0, 1.5, 2.0), 2: (22.0, 6.5, 4.5)}
        )
        self.assertTrue(command.restore_projection_state)
        self.assertEqual(command.before_projection_center_3d, (1.0, 2.0, 3.0))
        self.assertEqual(command.after_projection_center_3d, (7.0, 8.0, 9.0))
        self.assertEqual(command.before_projection_anchor_2d, (4.0, 5.0))
        self.assertEqual(command.after_projection_anchor_2d, (11.0, 12.0))
        self.assertEqual(canvas.restore_selection_calls, [({0, 2}, {1})])
        self.assertEqual(canvas.selection_info_emits, 1)
        self.assertEqual(canvas.rotation_state.atom_ids, set())
        self.assertIsNone(canvas.rotation_state.center_3d)
        self.assertEqual(canvas.rotation_state.base_coords, {})
        self.assertEqual(canvas.rotation_state.total_angle, 0.0)
        self.assertIsNone(canvas.rotation_state.mode)
        self.assertEqual(canvas.rotation_state.free_angle_x, 0.0)
        self.assertEqual(canvas.rotation_state.free_angle_y, 0.0)
        self.assertIsNone(canvas.rotation_state.base_bond_length)
        self.assertIsNone(canvas.rotation_state.selection_ids)
        self.assertIsNone(canvas.rotation_state.axis_bond_id)
        self.assertIsNone(canvas.rotation_state.axis_atoms)
        self.assertEqual(canvas.rotation_state.start_positions, {})
        self.assertEqual(canvas.rotation_state.start_coords_3d, {})
        self.assertIsNone(canvas.rotation_state.start_projection_center_3d)
        self.assertIsNone(canvas.rotation_state.start_projection_anchor_2d)
        self.assertEqual(canvas.rotation_state.coord_atom_ids, set())

    def test_actual_end_accepts_final_outline_publication_and_rolls_back_failure(
        self,
    ) -> None:
        canvas = CanvasView()
        controller = canvas.services.interaction.selection_rotation_controller
        try:
            atom_ids = [
                add_atom_for(canvas, "C", 0.0, 0.0),
                add_atom_for(canvas, "O", 20.0, 0.0),
                add_atom_for(canvas, "N", 40.0, 10.0),
            ]
            add_bond_for(canvas, atom_ids[0], atom_ids[1])
            add_bond_for(canvas, atom_ids[1], atom_ids[2])
            for atom_id in atom_ids[1:]:
                atom_item = visible_atom_item_for(canvas, atom_id)
                self.assertIsNotNone(atom_item)
                atom_item.setSelected(True)
            self.app.processEvents()

            self.assertTrue(controller.begin_selection_3d_rotation())
            controller.update_selection_3d_rotation(40.0, 20.0)
            rolling_state = copy.deepcopy(controller.rotation)
            rolling_outline_list = selection_outlines_for(canvas)
            rolling_outlines = tuple(rolling_outline_list)
            rolling_scene_order = list(canvas.scene().items())
            self.assertTrue(rolling_outlines)

            primary = KeyboardInterrupt(
                "actual final selection publication interrupted"
            )
            real_emit_selection_info = controller.emit_selection_info

            def interrupt_after_selection_publication() -> None:
                raise primary

            controller.emit_selection_info = interrupt_after_selection_publication
            with self.assertRaises(KeyboardInterrupt) as raised:
                controller.end_selection_3d_rotation()

            self.assertIs(raised.exception, primary)
            self.assertEqual(controller.rotation, rolling_state)
            self.assertIs(selection_outlines_for(canvas), rolling_outline_list)
            self.assertEqual(
                tuple(selection_outlines_for(canvas)),
                rolling_outlines,
            )
            self.assertEqual(canvas.scene().items(), rolling_scene_order)
            self.assertTrue(
                all(outline.scene() is canvas.scene() for outline in rolling_outlines)
            )
            self.assertEqual(
                canvas.services.history_service.state.history,
                [],
            )

            controller.emit_selection_info = real_emit_selection_info
            controller.end_selection_3d_rotation()

            final_outline_list = selection_outlines_for(canvas)
            self.assertIsNot(final_outline_list, rolling_outline_list)
            self.assertTrue(final_outline_list)
            self.assertTrue(
                all(outline.scene() is None for outline in rolling_outlines)
            )
            self.assertTrue(
                all(outline.scene() is canvas.scene() for outline in final_outline_list)
            )
            self.assertEqual(
                len(canvas.services.history_service.state.history),
                1,
            )
            self.assertEqual(controller.rotation.atom_ids, set())
            self.assertIsNone(controller._rotation_transaction)
            self.assertIsNone(controller._rotation_preview_authority)
        finally:
            schedule_canvas_deletion_for(canvas)
            self.app.processEvents()

    def test_actual_end_accepts_ring_selection_republication(self) -> None:
        canvas = CanvasView()
        controller = canvas.services.interaction.selection_rotation_controller
        try:
            add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
            ring_item = ring_items_for(canvas)[0]
            ring_atom_ids = ring_item.data(2)
            self.assertIsInstance(ring_atom_ids, list)
            ring_item.setSelected(True)
            self.app.processEvents()
            history_count = len(canvas.services.history_service.state.history)

            self.assertEqual(len(canvas.scene().selectedItems()), 1)
            self.assertTrue(
                controller.begin_selection_3d_rotation(
                    press_pos=QPointF(0.0, 20.0),
                )
            )
            controller.update_selection_3d_rotation(80.0, 50.0)

            # Finalization republishes the semantic ring selection through its
            # atom graphics. That is an expected final selection generation,
            # not an external mutation of the rotation preview.
            controller.end_selection_3d_rotation()

            selected_atom_ids, selected_bond_ids = selected_ids_for(canvas)
            self.assertEqual(selected_atom_ids, set(ring_atom_ids))
            self.assertEqual(selected_bond_ids, set())
            self.assertEqual(controller.rotation.atom_ids, set())
            self.assertIsNone(controller._rotation_transaction)
            self.assertEqual(
                len(canvas.services.history_service.state.history),
                history_count + 1,
            )
        finally:
            schedule_canvas_deletion_for(canvas)
            self.app.processEvents()

    def test_end_rotation_uses_begin_bound_history_authority(self) -> None:
        def active_rotation():
            canvas = _FakeCanvas()
            history: list[object] = []
            redo_marker = object()
            redo_stack: list[object] = [redo_marker]
            history_state = SimpleNamespace(
                history=history,
                redo_stack=redo_stack,
            )
            push_calls: list[object] = []

            def begin_bound_push(command) -> None:
                push_calls.append(command)
                history_state.history.append(command)
                history_state.redo_stack.clear()

            history_service = SimpleNamespace(
                state=history_state,
                push=begin_bound_push,
            )
            controller = _controller_for(canvas)
            controller.history = history_service
            canvas.selected_atom_ids = {2}
            self.assertTrue(controller.begin_selection_3d_rotation())
            controller.update_selection_3d_rotation(20.0, 10.0)
            return (
                canvas,
                controller,
                history_service,
                history_state,
                history,
                redo_stack,
                redo_marker,
                push_calls,
            )

        (
            _canvas,
            controller,
            history_service,
            _history_state,
            history,
            redo_stack,
            _redo_marker,
            push_calls,
        ) = active_rotation()
        replacement_push_calls: list[object] = []
        history_service.push = replacement_push_calls.append

        controller.end_selection_3d_rotation()

        self.assertEqual(len(push_calls), 1)
        self.assertEqual(replacement_push_calls, [])
        self.assertEqual(len(history), 1)
        self.assertEqual(redo_stack, [])

        for mutation in ("owner", "state", "history", "redo"):
            with self.subTest(mutation=mutation):
                (
                    canvas,
                    controller,
                    history_service,
                    history_state,
                    history,
                    redo_stack,
                    redo_marker,
                    _push_calls,
                ) = active_rotation()
                runtime_before = copy.deepcopy(canvas.rotation_state)
                replacement_history: list[object] = [object()]
                replacement_redo: list[object] = [object()]
                replacement_state = SimpleNamespace(
                    history=replacement_history,
                    redo_stack=replacement_redo,
                )
                replacement_service = SimpleNamespace(
                    state=replacement_state,
                    push=lambda command, target=replacement_history: target.append(
                        command
                    ),
                )
                if mutation == "owner":
                    controller.history = replacement_service
                elif mutation == "state":
                    history_service.state = replacement_state
                elif mutation == "history":
                    history_state.history = replacement_history
                else:
                    history_state.redo_stack = replacement_redo

                with self.assertRaisesRegex(RuntimeError, "changed|identity"):
                    controller.end_selection_3d_rotation()

                self.assertEqual(canvas.rotation_state, runtime_before)
                self.assertIs(history_service.state, history_state)
                self.assertIs(history_state.history, history)
                self.assertIs(history_state.redo_stack, redo_stack)
                self.assertEqual(history, [])
                self.assertEqual(redo_stack, [redo_marker])
                self.assertEqual(replacement_history, replacement_state.history)
                self.assertEqual(replacement_redo, replacement_state.redo_stack)

                controller.history = history_service
                controller.end_selection_3d_rotation()
                self.assertEqual(len(history), 1)
                self.assertEqual(redo_stack, [])

    def test_end_rotation_rejects_successful_push_stack_corruption(self) -> None:
        canvas = _FakeCanvas()
        history: list[object] = []
        redo_marker = object()
        redo_stack: list[object] = [redo_marker]
        state = SimpleNamespace(history=history, redo_stack=redo_stack)
        should_corrupt = True
        push_calls: list[object] = []

        def push_then_corrupt(command) -> None:
            push_calls.append(command)
            history.append(command)
            redo_stack.clear()
            if should_corrupt:
                history.clear()
                redo_stack.append(object())

        service = SimpleNamespace(state=state, push=push_then_corrupt)
        controller = _controller_for(canvas)
        controller.history = service
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        runtime_before = copy.deepcopy(canvas.rotation_state)

        with self.assertRaisesRegex(RuntimeError, "contents changed"):
            controller.end_selection_3d_rotation()

        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])
        self.assertEqual(len(push_calls), 1)

        should_corrupt = False
        controller.end_selection_3d_rotation()
        self.assertEqual(len(history), 1)
        self.assertEqual(redo_stack, [])

    def test_end_rotation_rejects_successful_push_command_payload_mutation(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        history: list[object] = []
        redo_marker = object()
        redo_stack: list[object] = [redo_marker]
        state = SimpleNamespace(history=history, redo_stack=redo_stack)
        published: list[SetAtomPositionsCommand] = []
        expected_after: dict[int, tuple[float, float]] = {}

        def push_then_corrupt(command: SetAtomPositionsCommand) -> bool:
            published.append(command)
            history.append(command)
            redo_stack.clear()
            expected_after.update(command.after_positions)
            command.after_positions.clear()
            command.after_positions[2] = (999.0, 999.0)
            return True

        controller = _controller_for(canvas)
        controller.history = SimpleNamespace(state=state, push=push_then_corrupt)
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        runtime_before = copy.deepcopy(canvas.rotation_state)

        with self.assertRaisesRegex(RuntimeError, "history command field"):
            controller.end_selection_3d_rotation()

        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertEqual(published[0].after_positions, expected_after)
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])
        self.assertEqual(len(published), 1)

    def test_rotation_rejects_truthy_push_without_exact_stack_contract(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        push_calls: list[object] = []
        controller.history = SimpleNamespace(
            state=SimpleNamespace(history=(), redo_stack=()),
            push=lambda command: push_calls.append(command) or True,
        )
        canvas.selected_atom_ids = {2}
        runtime_before = copy.deepcopy(canvas.rotation_state)

        with self.assertRaisesRegex(RuntimeError, "exact mutable history stacks"):
            controller.begin_selection_3d_rotation()

        self.assertEqual(push_calls, [])
        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertIsNone(controller._rotation_transaction)
        self.assertIsNone(controller._rotation_preview_authority)

    def test_end_rotation_rollback_uses_local_preview_after_token_field_deleted(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        history: list[object] = []
        redo_marker = object()
        redo_stack = [redo_marker]
        history_state = SimpleNamespace(
            history=history,
            redo_stack=redo_stack,
            enabled=True,
            limit=100,
        )

        def push_then_delete_preview(command) -> None:
            history.append(command)
            redo_stack.clear()
            token = controller._rotation_transaction
            assert token is not None
            token.preview = None

        history_service = SimpleNamespace(
            state=history_state,
            push=push_then_delete_preview,
        )
        controller.history = history_service
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        runtime_before = copy.deepcopy(canvas.rotation_state)

        with self.assertRaisesRegex(RuntimeError, "preview authority changed"):
            controller.end_selection_3d_rotation()

        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])
        self.assertIsNotNone(controller._rotation_transaction)

        def push(command) -> None:
            history.append(command)
            redo_stack.clear()

        history_service.push = push
        token = controller._rotation_transaction
        assert token is not None
        token.history_push = push
        controller.end_selection_3d_rotation()
        self.assertEqual(len(history), 1)
        self.assertEqual(redo_stack, [])

    def test_end_rotation_uses_published_authority_after_token_stack_deleted(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        history: list[object] = []
        redo_marker = object()
        redo_stack = [redo_marker]
        history_state = SimpleNamespace(
            history=history,
            redo_stack=redo_stack,
            enabled=True,
            limit=100,
        )

        def push_then_delete_stack_authority(command) -> None:
            history.append(command)
            redo_stack.clear()
            token = controller._rotation_transaction
            assert token is not None
            token.history_stacks = None

        history_service = SimpleNamespace(
            state=history_state,
            push=push_then_delete_stack_authority,
        )
        controller.history = history_service
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        runtime_before = copy.deepcopy(canvas.rotation_state)

        with self.assertRaisesRegex(RuntimeError, "stack authority changed"):
            controller.end_selection_3d_rotation()

        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])
        token = controller._rotation_transaction
        assert token is not None
        self.assertIsNotNone(token.history_stacks)

        def push(command) -> None:
            history.append(command)
            redo_stack.clear()

        history_service.push = push
        token.history_push = push
        controller.end_selection_3d_rotation()
        self.assertEqual(len(history), 1)
        self.assertEqual(redo_stack, [])

    def test_rotation_rejects_and_restores_history_policy_drift(self) -> None:
        for stage in ("push", "selection", "selection_info"):
            with self.subTest(stage=stage):
                canvas = _FakeCanvas()
                history: list[object] = []
                redo_marker = object()
                redo_stack: list[object] = [redo_marker]
                state = SimpleNamespace(
                    history=history,
                    redo_stack=redo_stack,
                    enabled=True,
                    limit=100,
                )
                corruption = {"active": True}

                def corrupt_policy(_state=state) -> None:
                    _state.enabled = False
                    _state.limit = 0

                def push(
                    command,
                    _history=history,
                    _redo_stack=redo_stack,
                    _stage=stage,
                    _corruption=corruption,
                    _corrupt_policy=corrupt_policy,
                ) -> bool:
                    _history.append(command)
                    _redo_stack.clear()
                    if _stage == "push" and _corruption["active"]:
                        _corrupt_policy()
                    return True

                service = SimpleNamespace(state=state, push=push)
                controller = _controller_for(canvas)
                controller.history = service
                canvas.selected_atom_ids = {2}
                self.assertTrue(controller.begin_selection_3d_rotation())
                controller.update_selection_3d_rotation(20.0, 10.0)
                runtime_before = copy.deepcopy(canvas.rotation_state)

                real_restore_selection = controller.restore_selection_from_ids

                def restore_selection(
                    atom_ids,
                    bond_ids,
                    _restore=real_restore_selection,
                    _stage=stage,
                    _corruption=corruption,
                    _corrupt_policy=corrupt_policy,
                ) -> None:
                    _restore(atom_ids, bond_ids)
                    if _stage == "selection" and _corruption["active"]:
                        _corrupt_policy()

                controller.restore_selection_from_ids = restore_selection
                real_emit_selection_info = controller.emit_selection_info

                def emit_selection_info(
                    _emit=real_emit_selection_info,
                    _stage=stage,
                    _corruption=corruption,
                    _corrupt_policy=corrupt_policy,
                ) -> None:
                    _emit()
                    if _stage == "selection_info" and _corruption["active"]:
                        _corrupt_policy()

                controller.emit_selection_info = emit_selection_info

                with self.assertRaisesRegex(RuntimeError, "policy"):
                    controller.end_selection_3d_rotation()

                self.assertEqual(canvas.rotation_state, runtime_before)
                self.assertEqual(history, [])
                self.assertEqual(redo_stack, [redo_marker])
                self.assertTrue(state.enabled)
                self.assertEqual(state.limit, 100)

                corruption["active"] = False
                controller.end_selection_3d_rotation()
                self.assertEqual(len(history), 1)
                self.assertEqual(redo_stack, [])
                self.assertTrue(state.enabled)
                self.assertEqual(state.limit, 100)

    def test_rotation_policy_reader_cannot_replace_verified_stack_root(self) -> None:
        class PoisoningPolicyState:
            def __init__(self, history, redo_stack) -> None:
                self.history = history
                self.redo_stack = redo_stack
                self.enabled = True
                self.limit = 100
                self.poison_policy_read = False

            def __getattribute__(self, name):
                if name == "enabled" and object.__getattribute__(
                    self, "poison_policy_read"
                ):
                    object.__setattr__(self, "history", [object()])
                return object.__getattribute__(self, name)

        canvas = _FakeCanvas()
        history: list[object] = []
        redo_stack: list[object] = [object()]
        state = PoisoningPolicyState(history, redo_stack)

        def push(command) -> None:
            history.append(command)
            redo_stack.clear()

        controller = _controller_for(canvas)
        controller.history = SimpleNamespace(state=state, push=push)
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        token = controller._rotation_transaction
        assert token is not None

        state.poison_policy_read = True
        with self.assertRaisesRegex(RuntimeError, "list identity"):
            controller._verify_bound_history_authority(
                token,
                checkpoint=token.begin_history_checkpoint,
            )

        state.poison_policy_read = False
        state.history = history
        controller.end_selection_3d_rotation()
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)

    def test_rotation_policy_reader_cannot_poison_earlier_policy(self) -> None:
        class CrossPolicyState:
            def __init__(self, history, redo_stack) -> None:
                self.history = history
                self.redo_stack = redo_stack
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

        canvas = _FakeCanvas()
        history: list[object] = []
        redo_stack: list[object] = [object()]
        state = CrossPolicyState(history, redo_stack)

        def push(command) -> None:
            history.append(command)
            redo_stack.clear()

        controller = _controller_for(canvas)
        controller.history = SimpleNamespace(state=state, push=push)
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        token = controller._rotation_transaction
        assert token is not None

        state.poison_enabled = True
        with self.assertRaisesRegex(RuntimeError, "policy 'enabled' changed"):
            controller._verify_bound_history_authority(
                token,
                checkpoint=token.begin_history_checkpoint,
            )

        state.poison_enabled = False
        state.enabled = True
        controller.end_selection_3d_rotation()
        self.assertEqual(len(history), 1)
        self.assertEqual(redo_stack, [])

    def test_rotation_rollback_rechecks_history_after_preview_verification(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        history: list[object] = []
        redo_marker = object()
        redo_stack: list[object] = [redo_marker]
        state = SimpleNamespace(
            history=history,
            redo_stack=redo_stack,
            enabled=True,
            limit=100,
        )
        primary = KeyboardInterrupt("history push interrupted")

        def mutate_then_interrupt(command) -> None:
            history.append(command)
            redo_stack.clear()
            raise primary

        service = SimpleNamespace(state=state, push=mutate_then_interrupt)
        controller = _controller_for(canvas)
        controller.history = service
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        runtime_before = copy.deepcopy(canvas.rotation_state)
        token = controller._rotation_transaction
        assert token is not None
        preview = token.preview
        assert preview is not None
        preview_type = type(preview)
        original_verify = preview_type.verify_current_global
        verify_calls = 0

        def verify_then_corrupt_history(
            target_preview,
            *args,
            **kwargs,
        ) -> None:
            nonlocal verify_calls
            original_verify(target_preview, *args, **kwargs)
            verify_calls += 1
            if verify_calls == 1:
                history.append(object())
                state.enabled = False
                state.limit = 0

        with mock.patch.object(
            preview_type,
            "verify_current_global",
            new=verify_then_corrupt_history,
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                controller.end_selection_3d_rotation()

        self.assertIs(caught.exception, primary)
        self.assertEqual(verify_calls, 2)
        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertIs(state.history, history)
        self.assertIs(state.redo_stack, redo_stack)
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 100)

    def test_end_rotation_reentrant_owner_replacement_rolls_back_a_and_preserves_b(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        history: list[object] = []
        redo_marker = object()
        redo_stack: list[object] = [redo_marker]
        history_state = SimpleNamespace(
            history=history,
            redo_stack=redo_stack,
        )
        controller = _controller_for(canvas)
        replacement: dict[str, object] = {}

        def replace_owner_then_append(command) -> None:
            controller._rotation_transaction = None
            controller._rotation_preview_authority = None
            owner_b = controller._reserve_rotation_transaction(begin_bound=True)
            state_b = CanvasRotationState(
                atom_ids={1},
                selection_ids=({1}, set()),
                mode="rigid",
                center_3d=(55.0, 66.0, 0.0),
                base_coords={1: (55.0, 66.0, 0.0)},
                start_positions={1: (10.0, 0.0)},
                start_coords_3d={1: (10.0, 0.0, 0.0)},
                coord_atom_ids={1},
            )
            controller.rotation = state_b
            canvas.rotation_state = state_b
            canvas.model.atoms[1].x = 55.0
            canvas.model.atoms[1].y = 66.0
            canvas.atom_coords_3d[1] = (55.0, 66.0, 0.0)
            preview_b = controller._capture_rotation_preview_for_token(
                owner_b,
                {1},
            )
            replacement.update(
                owner=owner_b,
                state=state_b,
                state_value=copy.deepcopy(state_b),
                preview=preview_b,
            )
            history_state.history.append(command)
            history_state.redo_stack.clear()

        history_service = SimpleNamespace(
            state=history_state,
            push=replace_owner_then_append,
        )
        controller.history = history_service
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)

        with self.assertRaisesRegex(RuntimeError, "owner changed"):
            controller.end_selection_3d_rotation()

        owner_b = replacement["owner"]
        state_b = replacement["state"]
        preview_b = replacement["preview"]
        self.assertIs(controller._rotation_transaction, owner_b)
        self.assertIs(controller._rotation_preview_authority, preview_b)
        self.assertIs(controller.rotation, state_b)
        self.assertIs(canvas.rotation_state, state_b)
        self.assertEqual(state_b, replacement["state_value"])
        self.assertEqual(
            (canvas.model.atoms[1].x, canvas.model.atoms[1].y),
            (55.0, 66.0),
        )
        self.assertEqual(canvas.atom_coords_3d[1], (55.0, 66.0, 0.0))
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])

    def test_rotation_rollback_observer_published_owner_b_is_final_runtime_writer(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        history: list[object] = []
        redo_marker = object()
        redo_stack: list[object] = [redo_marker]
        history_state = SimpleNamespace(
            history=history,
            redo_stack=redo_stack,
        )
        controller = _controller_for(canvas)
        primary = KeyboardInterrupt("history push interrupted before publication")
        replacement: dict[str, object] = {}

        def push_then_interrupt(command) -> None:
            history.append(command)
            redo_stack.clear()
            raise primary

        def publish_owner_b_during_rollback() -> None:
            if replacement:
                return
            controller._rotation_transaction = None
            controller._rotation_preview_authority = None
            owner_b = controller._reserve_rotation_transaction(begin_bound=True)
            state_b = CanvasRotationState(
                atom_ids={1},
                selection_ids=({1}, set()),
                mode="rigid",
                center_3d=(55.0, 66.0, 0.0),
                base_coords={1: (55.0, 66.0, 0.0)},
                start_positions={1: (10.0, 0.0)},
                start_coords_3d={1: (10.0, 0.0, 0.0)},
                coord_atom_ids={1},
            )
            controller.rotation = state_b
            canvas.rotation_state = state_b
            canvas.model.atoms[1].x = 55.0
            canvas.model.atoms[1].y = 66.0
            canvas.atom_coords_3d[1] = (55.0, 66.0, 0.0)
            preview_b = controller._capture_rotation_preview_for_token(
                owner_b,
                {1},
            )
            replacement.update(
                owner=owner_b,
                state=state_b,
                state_value=copy.deepcopy(state_b),
                preview=preview_b,
            )

        history_service = SimpleNamespace(
            state=history_state,
            push=push_then_interrupt,
            notify_change=publish_owner_b_during_rollback,
        )
        controller.history = history_service
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)

        with self.assertRaises(KeyboardInterrupt) as caught:
            controller.end_selection_3d_rotation()

        self.assertIs(caught.exception, primary)
        owner_b = replacement["owner"]
        state_b = replacement["state"]
        preview_b = replacement["preview"]
        self.assertIs(controller._rotation_transaction, owner_b)
        self.assertIs(controller._rotation_preview_authority, preview_b)
        self.assertIs(controller.rotation, state_b)
        self.assertIs(canvas.rotation_state, state_b)
        self.assertEqual(state_b, replacement["state_value"])
        self.assertEqual(
            (canvas.model.atoms[1].x, canvas.model.atoms[1].y),
            (55.0, 66.0),
        )
        self.assertEqual(canvas.atom_coords_3d[1], (55.0, 66.0, 0.0))
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])

    def test_end_rotation_global_verification_rejects_unrelated_runtime_poison(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        history: list[object] = []
        redo_marker = object()
        redo_stack: list[object] = [redo_marker]
        history_state = SimpleNamespace(
            history=history,
            redo_stack=redo_stack,
        )

        def push(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()

        controller = _controller_for(canvas)
        controller.history = SimpleNamespace(state=history_state, push=push)
        canvas.selected_atom_ids = {2}
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        runtime_before = copy.deepcopy(canvas.rotation_state)
        atom_0_before = copy.deepcopy(canvas.model.atoms[0])
        coords_0_before = canvas.atom_coords_3d[0]

        def poison_unrelated_runtime() -> None:
            canvas.model.atoms[0].x = 999.0
            canvas.atom_coords_3d[0] = (999.0, 999.0, 999.0)

        controller.emit_selection_info = poison_unrelated_runtime
        with self.assertRaises(BaseExceptionGroup):
            controller.end_selection_3d_rotation()

        self.assertEqual(canvas.rotation_state, runtime_before)
        self.assertEqual(canvas.model.atoms[0], atom_0_before)
        self.assertEqual(canvas.atom_coords_3d[0], coords_0_before)
        self.assertEqual(history, [])
        self.assertEqual(redo_stack, [redo_marker])

        controller.emit_selection_info = mock.Mock()
        controller.end_selection_3d_rotation()
        self.assertEqual(len(history), 1)
        self.assertEqual(redo_stack, [])

    def _assert_end_rotation_failure_retry(self, failure_stage: str) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {0, 2}
        canvas.rotation_state.selection_ids = ({0, 2}, {1})
        canvas.rotation_state.base_coords = {0: (0.0, 0.0, 0.0)}
        canvas.rotation_state.mode = "rigid"
        canvas.rotation_state.start_positions = {
            0: (0.0, 0.0),
            2: (20.0, 5.0),
        }
        canvas.rotation_state.start_coords_3d = {
            0: (0.0, 0.0, 0.0),
            2: (20.0, 5.0, 3.0),
        }
        canvas.rotation_state.coord_atom_ids = {0, 2}
        canvas.model.atoms[0].x = 1.0
        canvas.model.atoms[2].x = 22.0
        canvas.atom_coords_3d[0] = (1.0, 0.0, 1.0)
        canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
        rotation_before = copy.deepcopy(canvas.rotation_state)

        redo_marker = object()
        history_state = SimpleNamespace(
            history=canvas.pushed_commands,
            redo_stack=[redo_marker],
        )
        history_list = history_state.history
        redo_list = history_state.redo_stack
        attempts = {"history": 0, "selection": 0, "selection_info": 0}

        def push(command) -> None:
            attempts["history"] += 1
            history_state.history.append(command)
            history_state.redo_stack.clear()
            if failure_stage == "history" and attempts["history"] == 1:
                raise RuntimeError("injected history failure")

        history_service = SimpleNamespace(state=history_state, push=push)
        controller.history = history_service

        real_restore_selection = controller.restore_selection_from_ids

        def restore_selection(atom_ids, bond_ids) -> None:
            attempts["selection"] += 1
            real_restore_selection(atom_ids, bond_ids)
            if failure_stage == "selection" and attempts["selection"] == 1:
                raise RuntimeError("injected selection failure")

        controller.restore_selection_from_ids = restore_selection
        real_emit_selection_info = controller.emit_selection_info

        def emit_selection_info() -> None:
            attempts["selection_info"] += 1
            real_emit_selection_info()
            if failure_stage == "selection_info" and attempts["selection_info"] == 1:
                raise RuntimeError("injected selection-info failure")

        controller.emit_selection_info = emit_selection_info

        with self.assertRaisesRegex(RuntimeError, "injected"):
            controller.end_selection_3d_rotation()

        self.assertEqual(canvas.rotation_state, rotation_before)
        self.assertIs(history_state.history, history_list)
        self.assertIs(history_state.redo_stack, redo_list)
        self.assertEqual(history_state.history, [])
        self.assertEqual(history_state.redo_stack, [redo_marker])

        controller.end_selection_3d_rotation()

        self.assertEqual(len(history_state.history), 1)
        self.assertIsInstance(history_state.history[0], SetAtomPositionsCommand)
        self.assertEqual(history_state.redo_stack, [])
        self.assertEqual(canvas.rotation_state.atom_ids, set())
        self.assertIsNone(canvas.rotation_state.selection_ids)

    def test_end_rotation_failure_keeps_session_and_retry_records_exactly_one_command(
        self,
    ) -> None:
        for failure_stage in ("history", "selection", "selection_info"):
            with self.subTest(failure_stage=failure_stage):
                self._assert_end_rotation_failure_retry(failure_stage)

    def test_end_rotation_selection_restore_requires_verified_authority(self) -> None:
        for scene_kind in ("fake", "actual"):
            for restore_behavior in ("fail_once", "no_op"):
                with self.subTest(
                    scene=scene_kind,
                    restore=restore_behavior,
                ):
                    primary = KeyboardInterrupt(
                        f"{scene_kind} selection-info finalization interrupted"
                    )
                    canvas = _FakeCanvas()
                    if scene_kind == "fake":

                        class SelectionItem(_FakeSceneItem):
                            def __init__(
                                self,
                                kind: str,
                                payload,
                                behavior: str,
                            ) -> None:
                                super().__init__(kind, payload)
                                self.restore_calls = 0
                                self.restore_behavior = behavior

                            def setSelected(self, selected: bool) -> None:
                                if selected:
                                    self.restore_calls += 1
                                    if self.restore_behavior == "no_op":
                                        return
                                    if self.restore_calls == 1:
                                        raise SystemExit(
                                            "fake selected setter failed once"
                                        )
                                super().setSelected(selected)

                        selected_item = SelectionItem(
                            "atom",
                            2,
                            restore_behavior,
                        )
                        selected_item._selected = True
                        canvas._scene = _FakeScene([selected_item])
                    else:

                        class SelectionItem(QGraphicsRectItem):
                            def __init__(
                                self,
                                x: float,
                                y: float,
                                width: float,
                                height: float,
                                behavior: str,
                            ) -> None:
                                super().__init__(x, y, width, height)
                                self.restore_calls = 0
                                self.restore_behavior = behavior

                            def setSelected(self, selected: bool) -> None:
                                if selected:
                                    self.restore_calls += 1
                                    if self.restore_behavior == "no_op":
                                        return
                                    if self.restore_calls == 1:
                                        raise SystemExit(
                                            "Qt selected setter failed once"
                                        )
                                QGraphicsRectItem.setSelected(self, selected)

                        scene = QGraphicsScene()
                        selected_item = SelectionItem(
                            0.0,
                            0.0,
                            10.0,
                            10.0,
                            restore_behavior,
                        )
                        selected_item.setFlag(
                            selected_item.GraphicsItemFlag.ItemIsSelectable,
                            True,
                        )
                        scene.addItem(selected_item)
                        QGraphicsRectItem.setSelected(selected_item, True)
                        canvas._scene = scene

                    controller = _controller_for(canvas)
                    canvas.rotation_state.atom_ids = {2}
                    canvas.rotation_state.selection_ids = ({2}, set())
                    canvas.rotation_state.start_positions = {2: (20.0, 5.0)}
                    canvas.rotation_state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
                    canvas.rotation_state.coord_atom_ids = {2}
                    canvas.model.atoms[2].x = 22.0
                    canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
                    rotation_before = copy.deepcopy(canvas.rotation_state)
                    history_state = SimpleNamespace(history=[], redo_stack=[])

                    def push(
                        command,
                        _history_state=history_state,
                    ) -> None:
                        _history_state.history.append(command)

                    controller.history = SimpleNamespace(
                        state=history_state,
                        push=push,
                    )

                    def mutate_selection_then_interrupt(
                        _scene_kind=scene_kind,
                        _selected_item=selected_item,
                        _primary=primary,
                    ) -> None:
                        if _scene_kind == "fake":
                            _FakeSceneItem.setSelected(_selected_item, False)
                        else:
                            QGraphicsRectItem.setSelected(_selected_item, False)
                        raise _primary

                    controller.emit_selection_info = mutate_selection_then_interrupt

                    with self.assertRaises(KeyboardInterrupt) as raised:
                        controller.end_selection_3d_rotation()

                    self.assertIs(raised.exception, primary)
                    self.assertEqual(history_state.history, [])
                    if restore_behavior == "fail_once":
                        self.assertTrue(selected_item.isSelected())
                        self.assertEqual(canvas.rotation_state, rotation_before)
                        controller.emit_selection_info = mock.Mock()
                        controller.end_selection_3d_rotation()
                        self.assertEqual(len(history_state.history), 1)
                        self.assertEqual(canvas.rotation_state.atom_ids, set())
                    else:
                        self.assertFalse(selected_item.isSelected())
                        self.assertEqual(canvas.rotation_state.atom_ids, set())
                        self.assertIsNone(canvas.rotation_state.selection_ids)
                        self.assertTrue(
                            any(
                                "selection" in note
                                for note in getattr(primary, "__notes__", [])
                            )
                        )

    def test_end_rotation_history_descriptor_capture_and_control_flow_retry(
        self,
    ) -> None:
        cases = (
            ("state", KeyboardInterrupt),
            ("history", SystemExit),
            ("redo_stack", KeyboardInterrupt),
        )
        for fail_field, error_type in cases:
            with self.subTest(field=fail_field, error=error_type.__name__):
                canvas = _FakeCanvas()
                controller = _controller_for(canvas)
                canvas.rotation_state.atom_ids = {2}
                canvas.rotation_state.selection_ids = ({2}, set())
                canvas.rotation_state.start_positions = {2: (20.0, 5.0)}
                canvas.rotation_state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
                canvas.rotation_state.coord_atom_ids = {2}
                canvas.model.atoms[2].x = 22.0
                canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
                rotation_before = copy.deepcopy(canvas.rotation_state)
                old_history_entry = object()
                old_redo_entry = object()
                history = [old_history_entry]
                redo_stack = [old_redo_entry]
                history_service = _FailOnceHistoryService(
                    fail_field,
                    history=history,
                    redo_stack=redo_stack,
                )
                controller.history = history_service

                with self.assertRaisesRegex(
                    AttributeError,
                    f"{fail_field} capture failed",
                ):
                    controller.end_selection_3d_rotation()

                self.assertEqual(history_service.push_calls, 0)
                self.assertIs(history_service._state._history, history)
                self.assertIs(history_service._state._redo_stack, redo_stack)
                self.assertEqual(history, [old_history_entry])
                self.assertEqual(redo_stack, [old_redo_entry])
                self.assertEqual(canvas.rotation_state, rotation_before)

                primary_error = error_type("history push interrupted")
                history_service.push_error = primary_error
                with self.assertRaises(error_type) as raised:
                    controller.end_selection_3d_rotation()

                self.assertIs(raised.exception, primary_error)
                self.assertIs(history_service._state._history, history)
                self.assertIs(history_service._state._redo_stack, redo_stack)
                self.assertEqual(history, [old_history_entry])
                self.assertEqual(redo_stack, [old_redo_entry])
                self.assertEqual(canvas.rotation_state, rotation_before)

                controller.end_selection_3d_rotation()

                self.assertEqual(len(history), 2)
                self.assertIsInstance(history[-1], SetAtomPositionsCommand)
                self.assertEqual(redo_stack, [])
                self.assertEqual(canvas.rotation_state.atom_ids, set())

    def test_end_rotation_preserves_original_error_when_runtime_rollback_also_fails(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {2}
        canvas.rotation_state.selection_ids = ({2}, set())
        canvas.rotation_state.start_positions = {2: (20.0, 5.0)}
        canvas.rotation_state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
        canvas.rotation_state.coord_atom_ids = {2}
        canvas.model.atoms[2].x = 22.0
        canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
        rotation_before = copy.deepcopy(canvas.rotation_state)
        history_error = RuntimeError("original history failure")
        history_state = SimpleNamespace(history=[], redo_stack=["redo"])
        history_list = history_state.history
        redo_list = history_state.redo_stack

        def append_then_raise(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            raise history_error

        controller.history = SimpleNamespace(
            state=history_state, push=append_then_raise
        )

        with (
            mock.patch(
                "chemvas.ui.selection_rotation_preview_transaction._UpdateSnapshot.restore",
                side_effect=RuntimeError("scene rollback failure"),
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            controller.end_selection_3d_rotation()

        self.assertIs(raised.exception, history_error)
        self.assertNotEqual(canvas.rotation_state, rotation_before)
        self.assertEqual(canvas.rotation_state.atom_ids, set())
        self.assertIs(history_state.history, history_list)
        self.assertIs(history_state.redo_stack, redo_list)
        self.assertEqual(history_state.history, [])
        self.assertEqual(history_state.redo_stack, ["redo"])
        self.assertTrue(
            any("scene rollback failure" in note for note in history_error.__notes__)
        )

    def test_end_rotation_broken_add_note_preserves_control_flow_primary_and_retry(
        self,
    ) -> None:
        for error_type in (
            _BrokenAddNoteInterrupt,
            _BrokenAddNoteSystemExit,
            _BrokenAddNoteLookupInterrupt,
            _BrokenAddNoteLookupSystemExit,
        ):
            with self.subTest(error_type=error_type.__name__):
                canvas = _FakeCanvas()
                controller = _controller_for(canvas)
                canvas.rotation_state.atom_ids = {2}
                canvas.rotation_state.selection_ids = ({2}, set())
                canvas.rotation_state.start_positions = {2: (20.0, 5.0)}
                canvas.rotation_state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
                canvas.rotation_state.coord_atom_ids = {2}
                canvas.model.atoms[2].x = 22.0
                canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
                rotation_before = copy.deepcopy(canvas.rotation_state)
                primary_error = error_type("rotation history interrupted")
                history_state = SimpleNamespace(history=[], redo_stack=["redo"])
                history_list = history_state.history
                redo_list = history_state.redo_stack

                def append_then_raise(
                    command,
                    error: BaseException = primary_error,
                    state=history_state,
                ) -> None:
                    state.history.append(command)
                    state.redo_stack.clear()
                    raise error

                controller.history = SimpleNamespace(
                    state=history_state,
                    push=append_then_raise,
                )

                with self.assertRaises(error_type) as raised:
                    controller.end_selection_3d_rotation()

                self.assertIs(raised.exception, primary_error)
                self.assertEqual(canvas.rotation_state, rotation_before)
                self.assertIs(history_state.history, history_list)
                self.assertIs(history_state.redo_stack, redo_list)
                self.assertEqual(history_state.history, [])
                self.assertEqual(history_state.redo_stack, ["redo"])

                def push(command, state=history_state) -> None:
                    state.history.append(command)
                    state.redo_stack.clear()

                controller.history.push = push
                controller.end_selection_3d_rotation()
                self.assertEqual(len(history_state.history), 1)
                self.assertEqual(history_state.redo_stack, [])
                self.assertEqual(canvas.rotation_state.atom_ids, set())
                self.assertIsNone(canvas.rotation_state.selection_ids)

    def test_end_selection_3d_rotation_without_changes_skips_command_and_emits_selection(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {2}
        canvas.rotation_state.center_3d = (3.0, 4.0, 5.0)
        canvas.rotation_state.selection_ids = ({2}, set())
        canvas.rotation_state.base_coords = {2: (20.0, 5.0, 3.0)}
        canvas.rotation_state.mode = "bond"
        canvas.rotation_state.axis_bond_id = 1
        canvas.rotation_state.axis_atoms = (1, 2)
        canvas.rotation_state.start_positions = {2: (20.0, 5.0)}
        canvas.rotation_state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
        canvas.rotation_state.coord_atom_ids = {2}
        canvas.atom_coords_3d[2] = (20.0, 5.0, 3.0)
        canvas.model.atoms[2].x = 20.0
        canvas.model.atoms[2].y = 5.0

        controller.end_selection_3d_rotation()

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.restore_selection_calls, [({2}, set())])
        self.assertEqual(canvas.selection_info_emits, 1)
        self.assertEqual(canvas.rotation_state.atom_ids, set())
        self.assertIsNone(canvas.rotation_state.center_3d)
        self.assertEqual(canvas.rotation_state.base_coords, {})
        self.assertIsNone(canvas.rotation_state.mode)
        self.assertIsNone(canvas.rotation_state.selection_ids)
        self.assertIsNone(canvas.rotation_state.axis_bond_id)
        self.assertIsNone(canvas.rotation_state.axis_atoms)
        self.assertEqual(canvas.rotation_state.start_positions, {})
        self.assertEqual(canvas.rotation_state.start_coords_3d, {})
        self.assertEqual(canvas.rotation_state.coord_atom_ids, set())

    def test_end_selection_3d_rotation_without_selection_ids_only_emits_selection_info(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        canvas.rotation_state.atom_ids = {2}
        canvas.rotation_state.center_3d = (3.0, 4.0, 5.0)
        canvas.rotation_state.selection_ids = None
        canvas.rotation_state.base_coords = {2: (20.0, 5.0, 3.0)}
        canvas.rotation_state.mode = "bond"
        canvas.rotation_state.axis_bond_id = 1
        canvas.rotation_state.axis_atoms = (1, 2)
        canvas.rotation_state.start_positions = {2: (20.0, 5.0)}
        canvas.rotation_state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
        canvas.rotation_state.coord_atom_ids = {2}
        canvas.atom_coords_3d[2] = (20.0, 5.0, 3.0)

        controller.end_selection_3d_rotation()

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.restore_selection_calls, [])
        self.assertEqual(canvas.selection_info_emits, 1)

    def test_preview_exact_core_restores_replaced_roots_and_complete_contents(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        atom = canvas.model.atoms[2]
        atoms = canvas.model.atoms
        coords_state = canvas.atom_coords_3d_state
        coords = coords_state.atom_coords_3d
        rotation = canvas.rotation_state
        rotation.atom_ids = {2}
        rotation.base_coords = {2: (20.0, 5.0, 3.0)}
        rotation.mode = "rigid"
        replacement_coords = CanvasAtomCoords3DState(dict(coords))
        replacement_rotation = CanvasRotationState(atom_ids={999})
        primary = KeyboardInterrupt("preview replaced exact roots")

        def replace_every_root_then_fail() -> None:
            atom.x = 999.0
            atoms.pop(2)
            coords[999] = (9.0, 9.0, 9.0)
            canvas.atom_coords_3d_state = replacement_coords
            replacement_coords.atom_coords_3d[2] = (99.0, 99.0, 99.0)
            rotation.atom_ids.clear()
            rotation.base_coords.clear()
            rotation.mode = None
            controller.rotation = replacement_rotation
            raise primary

        with self.assertRaises(KeyboardInterrupt) as raised:
            run_rotation_preview_update(
                controller,
                {2},
                replace_every_root_then_fail,
            )

        self.assertIs(raised.exception, primary)
        self.assertIs(canvas.model.atoms, atoms)
        self.assertIs(atoms[2], atom)
        self.assertEqual(atom.x, 20.0)
        self.assertNotIn(999, coords)
        self.assertIs(canvas.atom_coords_3d_state, coords_state)
        self.assertIs(coords_state.atom_coords_3d, coords)
        self.assertIs(controller.rotation, rotation)
        self.assertIs(canvas.rotation_state, rotation)
        self.assertEqual(rotation.atom_ids, {2})
        self.assertEqual(rotation.base_coords, {2: (20.0, 5.0, 3.0)})
        self.assertEqual(rotation.mode, "rigid")

    def test_preview_rect_callback_cannot_recontaminate_restored_model(self) -> None:
        canvas = _FakeCanvas()
        scene = QGraphicsScene()
        canvas._scene = scene
        controller = _controller_for(canvas)
        atom = canvas.model.atoms[2]
        poisoned = False

        def poison_model(_rect) -> None:
            if poisoned:
                atom.x = 777.0

        scene.sceneRectChanged.connect(poison_model)
        primary = SystemExit("preview stopped before rect restore")

        def mutate_then_fail() -> None:
            nonlocal poisoned
            atom.x = 999.0
            poisoned = True
            raise primary

        with self.assertRaises(SystemExit) as raised:
            run_rotation_preview_update(controller, {2}, mutate_then_fail)

        self.assertIs(raised.exception, primary)
        self.assertEqual(atom.x, 20.0)

    def test_preview_exact_restore_recovers_fail_once_selection_setter(self) -> None:
        class FailOnceSelectionItem(_FakeSceneItem):
            fail_restore = False
            restore_calls = 0

            def setSelected(self, selected: bool) -> None:
                if selected:
                    self.restore_calls += 1
                    if self.fail_restore:
                        self.fail_restore = False
                        raise SystemExit("selection restore failed once")
                super().setSelected(selected)

        canvas = _FakeCanvas()
        item = FailOnceSelectionItem("atom", 2)
        canvas._scene = _FakeScene([item])
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: item},
            atom_dots={},
        )
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        controller = _controller_for(canvas)
        primary = KeyboardInterrupt("preview changed selection")

        def mutate_then_fail() -> None:
            _FakeSceneItem.setSelected(item, False)
            item.fail_restore = True
            raise primary

        with self.assertRaises(KeyboardInterrupt) as raised:
            run_rotation_preview_update(controller, {2}, mutate_then_fail)

        self.assertIs(raised.exception, primary)
        self.assertTrue(item.isSelected())
        self.assertGreaterEqual(item.restore_calls, 2)
        self.assertFalse(
            any(
                "remained non-authoritative" in note
                for note in getattr(primary, "__notes__", [])
            )
        )

    def test_preview_restores_actual_scene_order_against_unaffected_sibling(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        scene = QGraphicsScene()
        affected = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        unaffected = QGraphicsRectItem(20.0, 0.0, 10.0, 10.0)
        scene.addItem(affected)
        scene.addItem(unaffected)
        canvas._scene = scene
        canvas.atom_graphics_state = SimpleNamespace(
            atom_items={2: affected},
            atom_dots={},
        )
        canvas.bond_graphics_state = SimpleNamespace(bond_items={})
        canvas.selection_outline_state = SimpleNamespace(outlines=[])
        canvas.scene_items_state = SimpleNamespace(ring_items=[])
        controller = _controller_for(canvas)
        before = list(scene.items())
        primary = KeyboardInterrupt("scene stacking changed")

        def reorder_then_fail() -> None:
            scene.removeItem(affected)
            scene.addItem(affected)
            raise primary

        with self.assertRaises(KeyboardInterrupt):
            run_rotation_preview_update(controller, {2}, reorder_then_fail)

        self.assertEqual(scene.items(), before)

    def test_preview_persistent_scene_rect_restore_uses_only_two_attempts(
        self,
    ) -> None:
        class PersistentRestoreScene(QGraphicsScene):
            fail_restores = False
            restore_calls = 0

            def setSceneRect(self, *args) -> None:
                if self.fail_restores:
                    self.restore_calls += 1
                    raise SystemExit("persistent scene rect restore failure")
                super().setSceneRect(*args)

        canvas = _FakeCanvas()
        scene = PersistentRestoreScene()
        canvas._scene = scene
        controller = _controller_for(canvas)
        primary = KeyboardInterrupt("preview failed before rect rollback")

        def fail_preview() -> None:
            scene.fail_restores = True
            raise primary

        with self.assertRaises(KeyboardInterrupt) as raised:
            run_rotation_preview_update(controller, set(), fail_preview)

        self.assertIs(raised.exception, primary)
        self.assertEqual(scene.restore_calls, 2)
        self.assertTrue(
            any(
                "non-authoritative" in note
                for note in getattr(primary, "__notes__", [])
            )
        )
        scene.fail_restores = False

    def test_end_rotation_bypasses_history_list_override_and_keeps_retryable_session(
        self,
    ) -> None:
        class NoOpHistoryList(list):
            no_op = False

            def __setitem__(self, key, value) -> None:
                if self.no_op and isinstance(key, slice):
                    return
                super().__setitem__(key, value)

        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        state = canvas.rotation_state
        state.atom_ids = {2}
        state.selection_ids = ({2}, set())
        state.start_positions = {2: (20.0, 5.0)}
        state.start_coords_3d = {2: (20.0, 5.0, 3.0)}
        state.coord_atom_ids = {2}
        canvas.model.atoms[2].x = 22.0
        canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
        history = NoOpHistoryList()
        history_state = SimpleNamespace(history=history, redo_stack=[])
        primary = RuntimeError("history push failed after append")

        def push_then_fail(command) -> None:
            history.append(command)
            history.no_op = True
            raise primary

        controller.history = SimpleNamespace(
            state=history_state,
            push=push_then_fail,
        )

        with self.assertRaises(RuntimeError) as raised:
            controller.end_selection_3d_rotation()

        self.assertIs(raised.exception, primary)
        self.assertEqual(history, [])
        self.assertEqual(state.atom_ids, {2})
        self.assertEqual(state.selection_ids, ({2}, set()))

        history.no_op = False
        controller.history.push = history.append
        controller.end_selection_3d_rotation()
        self.assertEqual(len(history), 1)

    def test_end_rotation_clear_session_failure_rolls_back_for_one_retry(self) -> None:
        class FailOnceClearRotationState(CanvasRotationState):
            clear_failures = 1

            def clear_session(self) -> None:
                self.atom_ids.clear()
                if self.clear_failures:
                    self.clear_failures -= 1
                    raise SystemExit("clear session failed after mutation")
                super().clear_session()

        canvas = _FakeCanvas()
        state = FailOnceClearRotationState(
            atom_ids={2},
            selection_ids=({2}, set()),
            start_positions={2: (20.0, 5.0)},
            start_coords_3d={2: (20.0, 5.0, 3.0)},
            coord_atom_ids={2},
        )
        canvas.rotation_state = state
        canvas.model.atoms[2].x = 22.0
        canvas.atom_coords_3d[2] = (22.0, 5.0, 4.0)
        controller = _controller_for(canvas)
        history_state = SimpleNamespace(history=[], redo_stack=[])
        controller.history = SimpleNamespace(
            state=history_state,
            push=history_state.history.append,
        )

        with self.assertRaisesRegex(SystemExit, "clear session failed"):
            controller.end_selection_3d_rotation()

        self.assertEqual(history_state.history, [])
        self.assertEqual(state.atom_ids, {2})
        self.assertEqual(state.selection_ids, ({2}, set()))

        controller.end_selection_3d_rotation()
        self.assertEqual(len(history_state.history), 1)
        self.assertEqual(state.atom_ids, set())
        self.assertIsNone(state.selection_ids)


if __name__ == "__main__":
    unittest.main()
