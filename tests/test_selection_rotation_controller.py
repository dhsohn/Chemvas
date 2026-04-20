import math
import sys
import unittest
from pathlib import Path

from PyQt6.QtCore import QPointF


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.history import SetAtomPositionsCommand
from core.model import Atom, Bond, MoleculeModel
from ui.selection_rotation_controller import SelectionRotationController


class _FakeSceneItem:
    def __init__(self, kind: str, payload: dict | None = None) -> None:
        self.kind = kind
        self.payload = payload or {}

    def data(self, key: int):
        if key == 0:
            return self.kind
        if key == 1:
            return self.payload
        return None


class _FakeScene:
    def __init__(self, selected_items: list[_FakeSceneItem] | None = None) -> None:
        self._selected_items = list(selected_items or [])

    def selectedItems(self) -> list[_FakeSceneItem]:
        return list(self._selected_items)


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
        self.atom_coords_3d = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
            2: (20.0, 5.0, 3.0),
        }
        self._scene = _FakeScene()
        self.selected_atom_ids: set[int] = set()
        self.selected_bond_ids: set[int] = set()
        self.axis_hint_response: tuple[int, set[int]] | None = None
        self.flattened_coords: dict[int, tuple[float, float, float]] | None = None

        self._projection_center_3d = (100.0, 200.0, 300.0)
        self._projection_anchor_2d = (50.0, 60.0)
        self._rotation_start_coords_3d = {999: (1.0, 1.0, 1.0)}
        self._rotation_coord_atom_ids = {999}
        self._rotation_selection_ids = None
        self._rotation_base_coords: dict[int, tuple[float, float, float]] = {}
        self._rotation_axis_bond_id = None
        self._rotation_axis_atoms = None
        self._rotation_total_angle = 0.0
        self._rotation_mode = None
        self._rotation_free_angle_x = 0.0
        self._rotation_free_angle_y = 0.0
        self._rotation_base_bond_length = None
        self.rotation_atom_ids: set[int] = set()
        self.rotation_center_3d = None
        self._rotation_start_projection_center_3d = None
        self._rotation_start_projection_anchor_2d = None
        self._rotation_start_positions: dict[int, tuple[float, float]] = {}

        self.axis_hint_calls: list[tuple[int, set[int], QPointF | None]] = []
        self.flatten_calls: list[tuple[set[int], dict[int, tuple[float, float, float]]]] = []
        self.average_bond_length_calls: list[tuple[set[int], dict[int, tuple[float, float, float]]]] = []
        self.unproject_calls: list[tuple[tuple[float, float], float, tuple[float, float, float], tuple[float, float]]] = []
        self.apply_projected_calls: list[tuple[set[int], dict[int, tuple[float, float, float]]]] = []
        self.redraw_calls: list[set[int]] = []
        self.ring_fill_calls: list[set[int]] = []
        self.selection_outline_updates = 0
        self.rotate_axis_calls: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]] = []
        self.pushed_commands: list[SetAtomPositionsCommand] = []
        self.restore_selection_calls: list[tuple[set[int], set[int]]] = []
        self.selection_info_emits = 0

    def scene(self) -> _FakeScene:
        return self._scene

    def _selected_ids(self) -> tuple[set[int], set[int]]:
        return set(self.selected_atom_ids), set(self.selected_bond_ids)

    def _axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        press_pos: QPointF | None = None,
    ) -> tuple[int, set[int]] | None:
        self.axis_hint_calls.append((axis_hint, set(rotation_atom_ids), press_pos))
        return self.axis_hint_response

    def _current_atom_coords_3d(self, atom_id: int) -> tuple[float, float, float] | None:
        return self.atom_coords_3d.get(atom_id)

    def _flatten_planar_fragments(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> dict[int, tuple[float, float, float]]:
        self.flatten_calls.append((set(atom_ids), dict(coords)))
        if self.flattened_coords is not None:
            return dict(self.flattened_coords)
        return dict(coords)

    def _average_bond_length_for_atoms(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> float:
        self.average_bond_length_calls.append((set(atom_ids), dict(coords)))
        return 12.5

    def _unproject_scene_point_3d(
        self,
        point: QPointF,
        z: float,
        *,
        center_3d: tuple[float, float, float],
        anchor_2d: tuple[float, float],
    ) -> tuple[float, float, float]:
        self.unproject_calls.append(((point.x(), point.y()), z, center_3d, anchor_2d))
        return (point.x() + 0.5, point.y() - 0.25, z + 1.0)

    def _apply_projected_atom_positions(
        self,
        atom_ids: set[int],
        rotated_coords: dict[int, tuple[float, float, float]],
    ) -> None:
        self.apply_projected_calls.append((set(atom_ids), dict(rotated_coords)))
        for atom_id, (x, y, z) in rotated_coords.items():
            self.atom_coords_3d[atom_id] = (x, y, z)
            atom = self.model.atoms[atom_id]
            atom.x = x
            atom.y = y

    def _redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        self.redraw_calls.append(set(atom_ids))

    def _update_ring_fills_for_atoms(self, atom_ids: set[int]) -> None:
        self.ring_fill_calls.append(set(atom_ids))

    def _update_selection_outline(self) -> None:
        self.selection_outline_updates += 1

    def _rotate_point_around_axis(
        self,
        coords: tuple[float, float, float],
        axis_start: tuple[float, float, float],
        axis_end: tuple[float, float, float],
        angle: float,
    ) -> tuple[float, float, float]:
        self.rotate_axis_calls.append((coords, axis_start, axis_end, angle))
        return (coords[0] + angle, coords[1] - angle, coords[2] + 0.5)

    def _push_command(self, command: SetAtomPositionsCommand) -> None:
        self.pushed_commands.append(command)

    def _restore_selection_from_ids(self, atom_ids: set[int], bond_ids: set[int]) -> None:
        self.restore_selection_calls.append((set(atom_ids), set(bond_ids)))

    def _emit_selection_info(self) -> None:
        self.selection_info_emits += 1


class SelectionRotationControllerTest(unittest.TestCase):
    def test_begin_selection_3d_rotation_returns_false_without_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=1)

        self.assertFalse(rotating)
        self.assertEqual(canvas._rotation_start_coords_3d, {})
        self.assertEqual(canvas._rotation_coord_atom_ids, set())
        self.assertEqual(canvas.axis_hint_calls, [])

    def test_begin_selection_3d_rotation_skips_non_mark_and_invalid_mark_items(self) -> None:
        canvas = _FakeCanvas()
        canvas._scene = _FakeScene(
            [
                _FakeSceneItem("atom"),
                _FakeSceneItem("mark", {"atom_id": "bad"}),
                _FakeSceneItem("mark", {"atom_id": 2}),
            ]
        )
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [])
        self.assertEqual(canvas.rotation_atom_ids, {2})

    def test_begin_selection_3d_rotation_uses_axis_hint_bond_path(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (0, {2})
        canvas.flattened_coords = {
            0: (0.0, 0.0, 1.0),
            1: (10.0, 0.0, 3.0),
            2: (22.0, 7.0, 5.0),
        }
        controller = SelectionRotationController(canvas)
        press_pos = QPointF(14.0, 9.0)

        rotating = controller.begin_selection_3d_rotation(axis_hint=7, press_pos=press_pos)

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(7, {2}, press_pos)])
        self.assertEqual(canvas._rotation_mode, "bond")
        self.assertEqual(canvas._rotation_axis_bond_id, 0)
        self.assertEqual(canvas._rotation_axis_atoms, (0, 1))
        self.assertEqual(canvas.rotation_atom_ids, {2})
        self.assertEqual(canvas._rotation_selection_ids, ({2}, set()))
        self.assertEqual(canvas._rotation_start_positions, {2: (20.0, 5.0)})
        self.assertEqual(canvas.rotation_center_3d, (5.0, 0.0, 2.0))
        self.assertEqual(canvas._projection_center_3d, (5.0, 0.0, 2.0))
        self.assertEqual(canvas._projection_anchor_2d, (5.0, 0.0))
        self.assertEqual(canvas._rotation_start_projection_center_3d, (100.0, 200.0, 300.0))
        self.assertEqual(canvas._rotation_start_projection_anchor_2d, (50.0, 60.0))
        self.assertEqual(canvas._rotation_coord_atom_ids, {0, 1, 2})
        self.assertEqual(canvas._rotation_base_coords, canvas.flattened_coords)
        self.assertEqual(canvas.atom_coords_3d[2], (22.0, 7.0, 5.0))
        self.assertEqual(canvas.average_bond_length_calls, [({0, 1, 2}, dict(canvas.flattened_coords))])

    def test_begin_selection_3d_rotation_falls_back_to_rigid_mode(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {0}
        canvas.selected_bond_ids = {1}
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=4, press_pos=QPointF(2.0, 3.0))

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(4, {0, 1, 2}, QPointF(2.0, 3.0))])
        self.assertEqual(canvas._rotation_mode, "rigid")
        self.assertIsNone(canvas._rotation_axis_bond_id)
        self.assertIsNone(canvas._rotation_axis_atoms)
        self.assertEqual(canvas.rotation_atom_ids, {0, 1, 2})
        self.assertEqual(canvas._rotation_selection_ids, ({0}, {1}))
        self.assertEqual(canvas.rotation_center_3d, (10.0, 2.5, 1.0))
        self.assertEqual(canvas._projection_center_3d, (10.0, 2.5, 1.0))
        self.assertEqual(canvas._projection_anchor_2d, (10.0, 2.5))
        self.assertEqual(canvas._rotation_start_positions, {0: (0.0, 0.0), 1: (10.0, 0.0), 2: (20.0, 5.0)})
        self.assertEqual(
            canvas.unproject_calls,
            [
                ((0.0, 0.0), 0.0, (10.0, 2.5, 1.0), (10.0, 2.5)),
                ((10.0, 0.0), 0.0, (10.0, 2.5, 1.0), (10.0, 2.5)),
                ((20.0, 5.0), 3.0, (10.0, 2.5, 1.0), (10.0, 2.5)),
            ],
        )
        self.assertEqual(canvas._rotation_base_coords[0], (0.5, -0.25, 1.0))
        self.assertEqual(canvas._rotation_base_coords[2], (20.5, 4.75, 4.0))
        self.assertEqual(canvas.average_bond_length_calls, [({0, 1, 2}, dict(canvas._rotation_base_coords))])

    def test_begin_selection_3d_rotation_promotes_selected_marks_to_atom_ids(self) -> None:
        canvas = _FakeCanvas()
        canvas._scene = _FakeScene([_FakeSceneItem("mark", {"atom_id": 2})])
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [])
        self.assertEqual(canvas._rotation_mode, "rigid")
        self.assertEqual(canvas.rotation_atom_ids, {2})
        self.assertEqual(canvas._rotation_selection_ids, (set(), set()))
        self.assertEqual(canvas._rotation_start_positions, {2: (20.0, 5.0)})
        self.assertEqual(canvas._rotation_coord_atom_ids, {2})
        self.assertEqual(canvas.rotation_center_3d, (20.0, 5.0, 3.0))
        self.assertEqual(canvas._projection_anchor_2d, (20.0, 5.0))
        self.assertEqual(canvas._rotation_base_coords, {2: (20.5, 4.75, 4.0)})
        self.assertEqual(canvas.atom_coords_3d[2], (20.5, 4.75, 4.0))
        self.assertEqual(canvas.average_bond_length_calls, [({2}, dict(canvas._rotation_base_coords))])

    def test_begin_selection_3d_rotation_returns_false_for_missing_axis_bond(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (1, {2})
        canvas.model.bonds[1] = None
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=3)

        self.assertFalse(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(3, {2}, None)])
        self.assertIsNone(canvas._rotation_selection_ids)
        self.assertEqual(canvas.rotation_atom_ids, set())

    def test_begin_selection_3d_rotation_uses_axis_center_anchor_when_axis_atom_is_missing(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (0, {2, 99})
        del canvas.model.atoms[1]
        canvas.flattened_coords = {
            0: (0.0, 0.0, 1.0),
            1: (10.0, 0.0, 3.0),
            2: (22.0, 7.0, 5.0),
        }
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=6)

        self.assertTrue(rotating)
        self.assertEqual(canvas.axis_hint_calls, [(6, {2}, None)])
        self.assertEqual(canvas.rotation_atom_ids, {2, 99})
        self.assertNotIn(99, canvas._rotation_base_coords)
        self.assertEqual(canvas._projection_anchor_2d, (5.0, 0.0))
        self.assertEqual(canvas.average_bond_length_calls, [({0, 1, 2, 99}, dict(canvas.flattened_coords))])

    def test_begin_selection_3d_rotation_returns_false_when_axis_path_flattens_to_empty(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {2}
        canvas.axis_hint_response = (0, {2})
        canvas.flattened_coords = {}
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation(axis_hint=1)

        self.assertFalse(rotating)
        self.assertEqual(canvas._rotation_coord_atom_ids, {0, 1, 2})
        self.assertEqual(canvas._rotation_base_coords, {})
        self.assertEqual(canvas.rotation_atom_ids, set())

    def test_begin_selection_3d_rotation_returns_false_without_projectable_coords(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_bond_ids = {1, 99}
        canvas.model.bonds[1] = None
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertFalse(rotating)
        self.assertEqual(canvas._rotation_selection_ids, (set(), {1, 99}))
        self.assertEqual(canvas._rotation_start_coords_3d, {})

    def test_begin_selection_3d_rotation_returns_false_when_rotation_atoms_have_no_coords(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {0}
        canvas.atom_coords_3d = {}
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertFalse(rotating)
        self.assertEqual(canvas._rotation_selection_ids, ({0}, set()))
        self.assertEqual(canvas._rotation_start_coords_3d, {})
        self.assertEqual(canvas._rotation_coord_atom_ids, set())

    def test_begin_selection_3d_rotation_skips_missing_atoms_during_rigid_unprojection(self) -> None:
        canvas = _FakeCanvas()
        canvas.selected_atom_ids = {1, 2}
        del canvas.model.atoms[1]
        controller = SelectionRotationController(canvas)

        rotating = controller.begin_selection_3d_rotation()

        self.assertTrue(rotating)
        self.assertNotIn(1, canvas._rotation_base_coords)
        self.assertIn(2, canvas._rotation_base_coords)

    def test_update_selection_3d_rotation_noops_without_atoms_and_updates_rigid_rotation(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)

        controller.update_selection_3d_rotation(40.0, 25.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_atom_ids = {0, 2}
        canvas._rotation_mode = "rigid"
        canvas.rotation_center_3d = (0.0, 0.0, 0.0)
        canvas._rotation_base_coords = {
            0: (1.0, 0.0, 0.0),
            2: (0.0, 2.0, 0.0),
        }

        controller.update_selection_3d_rotation(40.0, 20.0)

        self.assertAlmostEqual(canvas._rotation_free_angle_x, 0.1)
        self.assertAlmostEqual(canvas._rotation_free_angle_y, 0.2)
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

    def test_update_selection_3d_rotation_rotates_bond_mode_atoms(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {2}
        canvas._rotation_mode = "bond"
        canvas._rotation_axis_atoms = (0, 1)
        canvas._rotation_base_coords = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
            2: (20.0, 5.0, 3.0),
        }

        controller.update_selection_3d_rotation(30.0, 10.0)

        self.assertAlmostEqual(canvas._rotation_total_angle, 0.15)
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

    def test_update_selection_3d_rotation_handles_zero_angles_and_missing_axis_data(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {0}

        canvas._rotation_mode = "rigid"
        canvas.rotation_center_3d = (0.0, 0.0, 0.0)
        canvas._rotation_base_coords = {0: (1.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(0.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas.rotation_atom_ids = {0, 9}
        canvas._rotation_base_coords = {0: (1.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(len(canvas.apply_projected_calls), 1)
        atom_ids, rotated = canvas.apply_projected_calls[0]
        self.assertEqual(atom_ids, {0, 9})
        self.assertEqual(set(rotated), {0})

        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {0}
        canvas._rotation_mode = "rigid"
        canvas.rotation_center_3d = None
        canvas._rotation_base_coords = {0: (1.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

    def test_update_selection_3d_rotation_handles_bond_mode_zero_delta_and_missing_axis_data(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {2}
        canvas._rotation_mode = "bond"
        canvas._rotation_axis_atoms = (0, 1)

        controller.update_selection_3d_rotation(0.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas._rotation_axis_atoms = None
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas._rotation_axis_atoms = (0, 1)
        canvas._rotation_base_coords = {0: (0.0, 0.0, 0.0)}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(canvas.apply_projected_calls, [])

        canvas._rotation_base_coords = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        canvas.rotation_atom_ids = {2, 9}
        controller.update_selection_3d_rotation(10.0, 0.0)
        self.assertEqual(len(canvas.apply_projected_calls), 1)
        atom_ids, rotated = canvas.apply_projected_calls[0]
        self.assertEqual(atom_ids, {2, 9})
        self.assertEqual(rotated, {})

        zero_canvas = _FakeCanvas()
        zero_controller = SelectionRotationController(zero_canvas)
        zero_canvas.rotation_atom_ids = {2}
        zero_canvas._rotation_mode = "bond"
        zero_canvas._rotation_axis_atoms = (0, 1)
        zero_controller.update_selection_3d_rotation(0.0, 0.0)
        self.assertEqual(zero_canvas.apply_projected_calls, [])

        missing_axis_canvas = _FakeCanvas()
        missing_axis_controller = SelectionRotationController(missing_axis_canvas)
        missing_axis_canvas.rotation_atom_ids = {2}
        missing_axis_canvas._rotation_mode = "bond"
        missing_axis_canvas._rotation_axis_atoms = (0, 1)
        missing_axis_canvas._rotation_base_coords = {0: (0.0, 0.0, 0.0)}
        missing_axis_controller.update_selection_3d_rotation(10.0, 5.0)
        self.assertEqual(missing_axis_canvas.apply_projected_calls, [])

        partial_coords_canvas = _FakeCanvas()
        partial_coords_controller = SelectionRotationController(partial_coords_canvas)
        partial_coords_canvas.rotation_atom_ids = {0, 2}
        partial_coords_canvas._rotation_mode = "bond"
        partial_coords_canvas._rotation_axis_atoms = (0, 1)
        partial_coords_canvas._rotation_base_coords = {
            0: (0.0, 0.0, 0.0),
            1: (10.0, 0.0, 0.0),
        }
        partial_coords_controller.update_selection_3d_rotation(10.0, 5.0)
        self.assertEqual(partial_coords_canvas.apply_projected_calls[-1], ({0, 2}, {0: (0.05, -0.05, 0.5)}))

    def test_end_selection_3d_rotation_pushes_command_and_restores_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {0, 2}
        canvas.rotation_center_3d = (3.0, 4.0, 5.0)
        canvas._rotation_selection_ids = ({0, 2}, {1})
        canvas._rotation_base_coords = {0: (0.0, 0.0, 0.0)}
        canvas._rotation_total_angle = 1.2
        canvas._rotation_mode = "rigid"
        canvas._rotation_free_angle_x = 0.3
        canvas._rotation_free_angle_y = 0.4
        canvas._rotation_base_bond_length = 9.0
        canvas._rotation_axis_bond_id = 1
        canvas._rotation_axis_atoms = (1, 2)
        canvas._rotation_start_positions = {0: (0.0, 0.0), 2: (20.0, 5.0)}
        canvas._rotation_start_coords_3d = {0: (0.0, 0.0, 0.0), 2: (20.0, 5.0, 3.0)}
        canvas._rotation_start_projection_center_3d = (1.0, 2.0, 3.0)
        canvas._rotation_start_projection_anchor_2d = (4.0, 5.0)
        canvas._rotation_coord_atom_ids = {0, 2}
        canvas._projection_center_3d = (7.0, 8.0, 9.0)
        canvas._projection_anchor_2d = (11.0, 12.0)
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
        self.assertEqual(command.before_coords_3d, {0: (0.0, 0.0, 0.0), 2: (20.0, 5.0, 3.0)})
        self.assertEqual(command.after_coords_3d, {0: (1.0, 1.5, 2.0), 2: (22.0, 6.5, 4.5)})
        self.assertTrue(command.restore_projection_state)
        self.assertEqual(command.before_projection_center_3d, (1.0, 2.0, 3.0))
        self.assertEqual(command.after_projection_center_3d, (7.0, 8.0, 9.0))
        self.assertEqual(command.before_projection_anchor_2d, (4.0, 5.0))
        self.assertEqual(command.after_projection_anchor_2d, (11.0, 12.0))
        self.assertEqual(canvas.restore_selection_calls, [({0, 2}, {1})])
        self.assertEqual(canvas.selection_info_emits, 1)
        self.assertEqual(canvas.rotation_atom_ids, set())
        self.assertIsNone(canvas.rotation_center_3d)
        self.assertEqual(canvas._rotation_base_coords, {})
        self.assertEqual(canvas._rotation_total_angle, 0.0)
        self.assertIsNone(canvas._rotation_mode)
        self.assertEqual(canvas._rotation_free_angle_x, 0.0)
        self.assertEqual(canvas._rotation_free_angle_y, 0.0)
        self.assertIsNone(canvas._rotation_base_bond_length)
        self.assertIsNone(canvas._rotation_selection_ids)
        self.assertIsNone(canvas._rotation_axis_bond_id)
        self.assertIsNone(canvas._rotation_axis_atoms)
        self.assertEqual(canvas._rotation_start_positions, {})
        self.assertEqual(canvas._rotation_start_coords_3d, {})
        self.assertIsNone(canvas._rotation_start_projection_center_3d)
        self.assertIsNone(canvas._rotation_start_projection_anchor_2d)
        self.assertEqual(canvas._rotation_coord_atom_ids, set())

    def test_end_selection_3d_rotation_without_changes_skips_command_and_emits_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {2}
        canvas.rotation_center_3d = (3.0, 4.0, 5.0)
        canvas._rotation_selection_ids = ({2}, set())
        canvas._rotation_base_coords = {2: (20.0, 5.0, 3.0)}
        canvas._rotation_mode = "bond"
        canvas._rotation_axis_bond_id = 1
        canvas._rotation_axis_atoms = (1, 2)
        canvas._rotation_start_positions = {2: (20.0, 5.0)}
        canvas._rotation_start_coords_3d = {2: (20.0, 5.0, 3.0)}
        canvas._rotation_coord_atom_ids = {2}
        canvas.atom_coords_3d[2] = (20.0, 5.0, 3.0)
        canvas.model.atoms[2].x = 20.0
        canvas.model.atoms[2].y = 5.0

        controller.end_selection_3d_rotation()

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.restore_selection_calls, [({2}, set())])
        self.assertEqual(canvas.selection_info_emits, 1)
        self.assertEqual(canvas.rotation_atom_ids, set())
        self.assertIsNone(canvas.rotation_center_3d)
        self.assertEqual(canvas._rotation_base_coords, {})
        self.assertIsNone(canvas._rotation_mode)
        self.assertIsNone(canvas._rotation_selection_ids)
        self.assertIsNone(canvas._rotation_axis_bond_id)
        self.assertIsNone(canvas._rotation_axis_atoms)
        self.assertEqual(canvas._rotation_start_positions, {})
        self.assertEqual(canvas._rotation_start_coords_3d, {})
        self.assertEqual(canvas._rotation_coord_atom_ids, set())

    def test_end_selection_3d_rotation_without_selection_ids_only_emits_selection_info(self) -> None:
        canvas = _FakeCanvas()
        controller = SelectionRotationController(canvas)
        canvas.rotation_atom_ids = {2}
        canvas.rotation_center_3d = (3.0, 4.0, 5.0)
        canvas._rotation_selection_ids = None
        canvas._rotation_base_coords = {2: (20.0, 5.0, 3.0)}
        canvas._rotation_mode = "bond"
        canvas._rotation_axis_bond_id = 1
        canvas._rotation_axis_atoms = (1, 2)
        canvas._rotation_start_positions = {2: (20.0, 5.0)}
        canvas._rotation_start_coords_3d = {2: (20.0, 5.0, 3.0)}
        canvas._rotation_coord_atom_ids = {2}
        canvas.atom_coords_3d[2] = (20.0, 5.0, 3.0)

        controller.end_selection_3d_rotation()

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.restore_selection_calls, [])
        self.assertEqual(canvas.selection_info_emits, 1)


if __name__ == "__main__":
    unittest.main()
