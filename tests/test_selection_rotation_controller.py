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
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.selection_rotation_controller import SelectionRotationController
from chemvas.ui.selection_rotation_preview_transaction import (
    capture_rotation_preview_authority,
)
from chemvas.ui.structure_mutation_access import (
    add_atom_for,
    add_bond_for,
)
from PyQt6 import sip
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsPolygonItem,
)


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
            graph_service=SimpleNamespace(
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
        graph_service=canvas.services.graph_service,
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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, set(canvas.rotation_state.atom_ids)
        )

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
        self.assertEqual(canvas.scene().items_call_count, 0)

    def test_preview_session_scans_scene_once_for_many_frames(self) -> None:
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

        self.assertTrue(controller.begin_selection_3d_rotation())
        for _frame in range(100):
            controller.update_selection_3d_rotation(1.0, 1.0)

        self.assertLessEqual(scene.items_call_count, 1)
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

    def test_preview_frame_failure_reverts_frame_and_gesture_continues(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        controller = _controller_for(canvas)
        self.assertTrue(controller.begin_selection_3d_rotation())
        controller.update_selection_3d_rotation(20.0, 10.0)
        rotation_before_failure = copy.deepcopy(canvas.rotation_state)
        atom_before_failure = copy.deepcopy(canvas.model.atoms[2])
        coords_before_failure = canvas.atom_coords_3d[2]
        successful_refresh = controller.refresh_atom_geometry
        primary = RuntimeError("rolling preview callback failed")

        def failing_refresh(_atom_ids: set[int]) -> None:
            raise primary

        controller.refresh_atom_geometry = failing_refresh
        with self.assertRaises(RuntimeError) as raised:
            controller.update_selection_3d_rotation(30.0, 15.0)
        controller.refresh_atom_geometry = successful_refresh

        self.assertIs(raised.exception, primary)
        self.assertEqual(canvas.rotation_state, rotation_before_failure)
        self.assertEqual(canvas.model.atoms[2], atom_before_failure)
        self.assertEqual(canvas.atom_coords_3d[2], coords_before_failure)
        self.assertEqual(canvas.pushed_commands, [])

        controller.update_selection_3d_rotation(30.0, 15.0)
        self.assertAlmostEqual(
            canvas.rotation_state.free_angle_x,
            rotation_before_failure.free_angle_x + 0.075,
        )
        controller.end_selection_3d_rotation()
        self.assertEqual(len(canvas.pushed_commands), 1)

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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, set(canvas.rotation_state.atom_ids)
        )

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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, set(canvas.rotation_state.atom_ids)
        )
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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, set(canvas.rotation_state.atom_ids)
        )
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
        partial_coords_controller._rotation_preview_authority = (
            capture_rotation_preview_authority(partial_coords_controller, {0, 2})
        )
        partial_coords_controller.update_selection_3d_rotation(10.0, 5.0)
        self.assertEqual(
            partial_coords_canvas.apply_projected_calls[-1],
            ({0, 2}, {0: (0.05, -0.05, 0.5)}),
        )

    def test_actual_failed_end_resyncs_label_items_to_start_positions(self) -> None:
        canvas = CanvasView()
        try:
            first = add_atom_for(canvas, "C", 0.0, 0.0)
            second = add_atom_for(canvas, "O", 40.0, 0.0)
            add_bond_for(canvas, first, second, 1)
            canvas.services.structure.structure_build_service.render_model()
            label_item = visible_atom_item_for(canvas, second)
            self.assertIsNotNone(label_item)
            for item in canvas.scene().items():
                item.setSelected(True)
            controller = canvas.services.interaction.selection_rotation_controller

            label_pos_before = label_item.pos()
            self.assertTrue(controller.begin_selection_3d_rotation())
            controller.update_selection_3d_rotation(30.0, 20.0)

            with mock.patch.object(
                type(canvas.services.history_service),
                "push",
                side_effect=RuntimeError("simulated rotation push failure"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "simulated rotation push failure"
                ):
                    controller.end_selection_3d_rotation()

            atom = canvas.model.atoms[second]
            self.assertAlmostEqual(atom.x, 40.0)
            self.assertAlmostEqual(atom.y, 0.0)
            self.assertAlmostEqual(label_item.pos().x(), label_pos_before.x())
            self.assertAlmostEqual(label_item.pos().y(), label_pos_before.y())
        finally:
            schedule_canvas_deletion_for(canvas)
            self.app.processEvents()

    def test_gesture_capture_skips_deleted_ring_wrappers(self) -> None:
        canvas = _FakeCanvas()
        live_ring = QGraphicsPolygonItem(
            QPolygonF(
                [
                    QPointF(0.0, 0.0),
                    QPointF(5.0, 0.0),
                    QPointF(2.5, 4.0),
                ]
            )
        )
        live_ring.setData(0, "ring")
        live_ring.setData(2, [2])
        deleted_ring = QGraphicsPolygonItem()
        deleted_ring.setData(0, "ring")
        deleted_ring.setData(2, [2])
        sip.delete(deleted_ring)
        canvas.scene_items_state = SimpleNamespace(ring_items=[live_ring, deleted_ring])
        controller = _controller_for(canvas)

        preview = capture_rotation_preview_authority(controller, {2})

        self.assertEqual(preview.affected_ring_items, (live_ring,))
        preview.release()

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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, {0, 2}
        )

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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, {2}
        )

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
        controller._rotation_preview_authority = capture_rotation_preview_authority(
            controller, {2}
        )

        controller.end_selection_3d_rotation()

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.restore_selection_calls, [])
        self.assertEqual(canvas.selection_info_emits, 1)


if __name__ == "__main__":
    unittest.main()
