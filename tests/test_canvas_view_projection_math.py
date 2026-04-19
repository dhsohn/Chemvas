import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import CompositeCommand, SetAtomPositionsCommand, SetRingPolygonsCommand, UpdateBondLengthCommand
    from core.model import Atom, Bond
    from ui.canvas_view import CanvasView


class _FakeRingItem:
    def __init__(self, points) -> None:
        self._polygon = QPolygonF([QPointF(x, y) for x, y in points])

    def polygon(self):
        return QPolygonF(self._polygon)

    def setPolygon(self, polygon) -> None:
        self._polygon = QPolygonF(polygon)


class _FakeDot:
    def __init__(self) -> None:
        self.positions = []

    def setPos(self, x: float, y: float) -> None:
        self.positions.append((x, y))


class _FakeMark:
    def __init__(self, payload) -> None:
        self._payload = payload

    def data(self, key):
        if key == 1:
            return self._payload
        return None


class _FakePen:
    def __init__(self) -> None:
        self.color = None

    def setColor(self, color) -> None:
        self.color = color


class _FakeBrush:
    def __init__(self, style) -> None:
        self._style = style

    def style(self):
        return self._style


class _FakePenBrushItem:
    def __init__(self, brush_style) -> None:
        self._pen = _FakePen()
        self._brush = _FakeBrush(brush_style)
        self.pen_updates = []
        self.brush_updates = []

    def pen(self):
        return self._pen

    def setPen(self, pen) -> None:
        self.pen_updates.append(pen)

    def brush(self):
        return self._brush

    def setBrush(self, color) -> None:
        self.brush_updates.append(color)


class _FakeBrushOnlyItem:
    def __init__(self, brush_style) -> None:
        self._brush = _FakeBrush(brush_style)
        self.brush_updates = []

    def brush(self):
        return self._brush

    def setBrush(self, color) -> None:
        self.brush_updates.append(color)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewProjectionMathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_set_bond_length_rescales_model_and_pushes_composite_command(self) -> None:
        ring_item = _FakeRingItem([(0.0, 0.0), (20.0, 0.0), (10.0, 10.0)])
        style = SimpleNamespace(bond_length_px=20.0)

        def _set_renderer_bond_length(length_px: float) -> None:
            style.bond_length_px = length_px

        pushed = []
        view = SimpleNamespace(
            renderer=SimpleNamespace(style=style, set_bond_length=mock.Mock(side_effect=_set_renderer_bond_length)),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 20.0, 0.0),
                }
            ),
            ring_items=[ring_item],
            _rebuild_graphics=mock.Mock(),
            _push_command=lambda command: pushed.append(command),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        view._rescale_model = lambda scale: CanvasView._rescale_model(view, scale)

        CanvasView.set_bond_length(view, 30.0)

        self.assertEqual(style.bond_length_px, 30.0)
        self.assertAlmostEqual(view.model.atoms[1].x, -5.0)
        self.assertAlmostEqual(view.model.atoms[2].x, 25.0)
        scaled_points = [(point.x(), point.y()) for point in ring_item.polygon()]
        self.assertEqual(scaled_points, [(-5.0, 0.0), (25.0, 0.0), (10.0, 15.0)])
        view._rebuild_graphics.assert_called_once_with()
        self.assertEqual(len(pushed), 1)
        command = pushed[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(entry) for entry in command.commands], [UpdateBondLengthCommand, SetAtomPositionsCommand, SetRingPolygonsCommand])

    def test_set_bond_length_short_circuits_for_empty_model_or_same_scale(self) -> None:
        empty_style = SimpleNamespace(bond_length_px=20.0)
        empty_view = SimpleNamespace(
            renderer=SimpleNamespace(style=empty_style, set_bond_length=mock.Mock(side_effect=lambda value: setattr(empty_style, "bond_length_px", value))),
            model=SimpleNamespace(atoms={}),
            ring_items=[],
            _rescale_model=mock.Mock(),
            _rebuild_graphics=mock.Mock(),
            _push_command=mock.Mock(),
        )

        CanvasView.set_bond_length(empty_view, 30.0)

        empty_view._rescale_model.assert_not_called()
        empty_view._rebuild_graphics.assert_not_called()
        empty_view._push_command.assert_not_called()

        same_style = SimpleNamespace(bond_length_px=24.0)
        same_view = SimpleNamespace(
            renderer=SimpleNamespace(style=same_style, set_bond_length=mock.Mock(side_effect=lambda value: setattr(same_style, "bond_length_px", value))),
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}),
            ring_items=[],
            _rescale_model=mock.Mock(),
            _rebuild_graphics=mock.Mock(),
            _push_command=mock.Mock(),
        )

        CanvasView.set_bond_length(same_view, 24.0)

        same_view._rescale_model.assert_not_called()
        same_view._rebuild_graphics.assert_not_called()
        same_view._push_command.assert_not_called()

    def test_normalize_project_unproject_and_current_coords_3d_helpers(self) -> None:
        self.assertIsNone(CanvasView._normalize_3d(0.0, 0.0, 0.0))
        self.assertEqual(CanvasView._normalize_3d(0.0, 3.0, 4.0), (0.0, 0.6, 0.8))

        no_projection_view = SimpleNamespace(_projection_center_3d=None, _projection_anchor_2d=None)
        self.assertEqual(CanvasView._project_point_3d(no_projection_view, (2.0, 3.0, 4.0)), (2.0, 3.0))
        self.assertEqual(
            CanvasView._unproject_scene_point_3d(no_projection_view, QPointF(2.0, 3.0), 4.0),
            (2.0, 3.0, 4.0),
        )

        projected_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _projection_center_3d=(10.0, 20.0, 30.0),
            _projection_anchor_2d=(100.0, 200.0),
        )
        projected_view._perspective_camera_distance = lambda: CanvasView._perspective_camera_distance(projected_view)
        projected_view._project_point_3d = lambda point: CanvasView._project_point_3d(projected_view, point)

        scene_xy = CanvasView._project_point_3d(projected_view, (14.0, 26.0, 40.0))
        restored = CanvasView._unproject_scene_point_3d(projected_view, QPointF(*scene_xy), 40.0)
        self.assertAlmostEqual(restored[0], 14.0, places=6)
        self.assertAlmostEqual(restored[1], 26.0, places=6)
        self.assertAlmostEqual(restored[2], 40.0, places=6)

        projected_atom = CanvasView._project_point_3d(projected_view, (12.0, 13.0, 30.0))
        projected_view.model = SimpleNamespace(
            atoms={
                1: Atom("C", projected_atom[0], projected_atom[1]),
                2: Atom("N", 40.0, 50.0),
            }
        )
        projected_view.atom_coords_3d = {
            1: (12.0, 13.0, 30.0),
            2: (50.0, 60.0, 80.0),
        }

        coords = CanvasView._current_atom_coords_3d(projected_view, 1)
        self.assertEqual(coords, (12.0, 13.0, 30.0))
        self.assertEqual(CanvasView._current_atom_coords_3d(projected_view, 2), (40.0, 50.0, 0.0))
        self.assertIsNone(CanvasView._current_atom_coords_3d(projected_view, 99))

        projected_view.atom_coords_3d = {}
        self.assertEqual(CanvasView._current_atom_coords_3d(projected_view, 1), projected_atom + (0.0,))

    def test_projection_and_center_helpers_cover_anchor_and_empty_fallbacks(self) -> None:
        projected_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _projection_center_3d=(10.0, 20.0, 30.0),
            _projection_anchor_2d=None,
        )
        projected_view._perspective_camera_distance = lambda: CanvasView._perspective_camera_distance(projected_view)

        projected = CanvasView._project_point_3d(projected_view, (12.0, 24.0, 30.0))
        restored = CanvasView._unproject_scene_point_3d(projected_view, QPointF(*projected), 30.0)
        self.assertAlmostEqual(projected[0], 12.0)
        self.assertAlmostEqual(projected[1], 24.0)
        self.assertAlmostEqual(restored[0], 12.0)
        self.assertAlmostEqual(restored[1], 24.0)
        self.assertEqual(CanvasView._center_for_coords_3d(projected_view, set(), {}), None)
        self.assertEqual(
            CanvasView._center_for_coords_3d(projected_view, {1, 2}, {3: (1.0, 2.0, 3.0)}),
            None,
        )

        explicit_projected = CanvasView._project_point_3d(
            projected_view,
            (12.0, 24.0, 31.0),
            center_3d=(10.0, 20.0, 30.0),
            anchor_2d=(0.0, 0.0),
        )
        explicit_restored = CanvasView._unproject_scene_point_3d(
            projected_view,
            QPointF(*explicit_projected),
            31.0,
            center_3d=(10.0, 20.0, 30.0),
            anchor_2d=(0.0, 0.0),
        )
        self.assertAlmostEqual(explicit_restored[0], 12.0)
        self.assertAlmostEqual(explicit_restored[1], 24.0)

    def test_planar_fragment_helpers_detect_and_flatten_connected_planar_atoms(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 2),
                    Bond(2, 3, 1),
                    Bond(3, 4, 1),
                    Bond(4, 5, 1),
                    None,
                ]
            ),
            _atom_bond_ids={
                1: {0},
                2: {0, 1},
                3: {1, 2},
                4: {2, 3},
                5: {3},
            },
            _bond_in_cycle=lambda bond_id: bond_id in {2, 3},
        )
        view._atom_in_planar_system = lambda atom_id: CanvasView._atom_in_planar_system(view, atom_id)
        view._bond_is_planar_fragment_edge = lambda bond_id: CanvasView._bond_is_planar_fragment_edge(view, bond_id)
        view._normalize_3d = CanvasView._normalize_3d
        view._center_for_coords_3d = lambda atom_ids, coords: CanvasView._center_for_coords_3d(view, atom_ids, coords)
        view._planar_fragment_components = lambda atom_ids: CanvasView._planar_fragment_components(view, atom_ids)
        view._fragment_plane_normal = lambda atom_ids, coords: CanvasView._fragment_plane_normal(view, atom_ids, coords)

        self.assertTrue(CanvasView._atom_in_planar_system(view, 2))
        self.assertTrue(CanvasView._bond_is_planar_fragment_edge(view, 1))
        self.assertTrue(CanvasView._bond_is_planar_fragment_edge(view, 3))
        self.assertFalse(CanvasView._bond_is_planar_fragment_edge(view, 99))
        self.assertEqual(CanvasView._planar_fragment_components(view, {1, 2, 3, 4, 5}), [{1, 2, 3, 4, 5}])

        coords = {
            1: (0.0, 0.0, 0.0),
            2: (1.0, 0.0, 1.0),
            3: (2.0, 0.0, 0.0),
            4: (3.0, 1.0, 0.0),
            5: (4.0, 1.0, 2.0),
        }
        normal = CanvasView._fragment_plane_normal(view, {1, 2, 3}, coords)
        self.assertIsNotNone(normal)
        flattened = CanvasView._flatten_planar_fragments(view, {1, 2, 3, 4, 5}, coords)
        self.assertNotEqual(flattened[5], coords[5])

    def test_planar_fragment_helpers_cover_invalid_none_collinear_and_skip_paths(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[None, Bond(1, 2, 1), Bond(2, 3, 1)]),
            _atom_bond_ids={1: {0, 9}, 2: {0, 1}, 3: {2}},
            _bond_in_cycle=lambda bond_id: False,
        )
        view._atom_in_planar_system = lambda atom_id: CanvasView._atom_in_planar_system(view, atom_id)
        view._normalize_3d = CanvasView._normalize_3d

        self.assertFalse(CanvasView._atom_in_planar_system(view, 1))
        self.assertFalse(CanvasView._bond_is_planar_fragment_edge(view, 0))
        self.assertFalse(CanvasView._bond_is_planar_fragment_edge(view, 9))
        self.assertIsNone(
            CanvasView._fragment_plane_normal(
                view,
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (1.0, 0.0, 0.0),
                },
            )
        )
        self.assertEqual(
            CanvasView._fragment_plane_normal(
                view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (1.0, 0.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            ),
            (0.0, 0.0, 1.0),
        )
        self.assertEqual(
            CanvasView._flatten_planar_fragments(view, set(), {1: (1.0, 2.0, 3.0)}),
            {1: (1.0, 2.0, 3.0)},
        )

        skip_view = SimpleNamespace(
            _planar_fragment_components=lambda atom_ids: [{1, 2, 3}],
            _fragment_plane_normal=lambda atom_ids, coords: None,
            _center_for_coords_3d=lambda atom_ids, coords: (1.0, 1.0, 1.0),
        )
        coords = {1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 1.0), 3: (2.0, 0.0, 0.0)}
        self.assertEqual(CanvasView._flatten_planar_fragments(skip_view, {1, 2, 3}, coords), coords)

        centroid_skip_view = SimpleNamespace(
            _planar_fragment_components=lambda atom_ids: [{1, 2, 3}],
            _fragment_plane_normal=lambda atom_ids, coords: (0.0, 0.0, 1.0),
            _center_for_coords_3d=lambda atom_ids, coords: None,
        )
        self.assertEqual(CanvasView._flatten_planar_fragments(centroid_skip_view, {1, 2, 3}, coords), coords)

        small_component_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            _bond_is_planar_fragment_edge=lambda bond_id: True,
        )
        self.assertEqual(CanvasView._planar_fragment_components(small_component_view, {1, 2}), [])

        missing_point_view = SimpleNamespace(
            _planar_fragment_components=lambda atom_ids: [{1, 2, 3}],
            _fragment_plane_normal=lambda atom_ids, coords: (0.0, 0.0, 1.0),
            _center_for_coords_3d=lambda atom_ids, coords: (0.0, 0.0, 0.0),
        )
        flattened_missing = CanvasView._flatten_planar_fragments(
            missing_point_view,
            {1, 2, 3},
            {
                1: (0.0, 0.0, 1.0),
                2: (1.0, 0.0, 0.0),
            },
        )
        self.assertEqual(flattened_missing[1], (0.0, 0.0, 0.0))
        self.assertEqual(flattened_missing[2], (1.0, 0.0, 0.0))

    def test_apply_projected_atom_positions_updates_labels_dots_and_marks(self) -> None:
        label = object()
        dot = _FakeDot()
        mark_with_offset = _FakeMark({"dx": 2.0, "dy": -3.0})
        mark_without_offset = _FakeMark({})
        view = SimpleNamespace(
            atom_coords_3d={},
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 4.0, 5.0)}),
            atom_items={1: label},
            atom_dots={1: dot},
            _marks_by_atom={1: [mark_with_offset, mark_without_offset]},
            _position_label=mock.Mock(),
            _set_mark_center=mock.Mock(),
        )
        view._project_point_3d = lambda point: (point[0] + 10.0, point[1] - 5.0)

        CanvasView._apply_projected_atom_positions(
            view,
            {1, 2, 99},
            {
                1: (1.0, 2.0, 3.0),
                2: (5.0, 7.0, 11.0),
            },
        )

        self.assertEqual(view.atom_coords_3d[1], (1.0, 2.0, 3.0))
        self.assertEqual(view.atom_coords_3d[2], (5.0, 7.0, 11.0))
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (11.0, -3.0))
        self.assertEqual((view.model.atoms[2].x, view.model.atoms[2].y), (15.0, 2.0))
        view._position_label.assert_called_once_with(label, 11.0, -3.0)
        self.assertEqual(dot.positions, [(11.0, -3.0)])
        self.assertEqual(view._set_mark_center.call_count, 2)
        first_mark_pos = view._set_mark_center.call_args_list[0].args[1]
        second_mark_pos = view._set_mark_center.call_args_list[1].args[1]
        self.assertEqual((first_mark_pos.x(), first_mark_pos.y()), (13.0, -6.0))
        self.assertEqual((second_mark_pos.x(), second_mark_pos.y()), (11.0, -3.0))

    def test_apply_projected_positions_average_lengths_and_rotation_scale_cover_noop_cases(self) -> None:
        view = SimpleNamespace(
            atom_coords_3d={},
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            atom_items={},
            atom_dots={},
            _marks_by_atom={},
            _position_label=mock.Mock(),
            _set_mark_center=mock.Mock(),
        )
        view._project_point_3d = lambda point: (point[0], point[1])

        CanvasView._apply_projected_atom_positions(
            view,
            {1, 2},
            {
                1: (1.0, 2.0, 3.0),
                2: (4.0, 5.0, 6.0),
            },
        )
        self.assertEqual(view.atom_coords_3d[2], (4.0, 5.0, 6.0))
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (1.0, 2.0))

        sparse_view = SimpleNamespace(
            _atom_bond_ids={1: {0, 99}, 2: {0}, 3: {1}},
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None]),
            _rotation_base_bond_length=10.0,
            _rotation_base_coords={1: (0.0, 0.0, 0.0), 2: (5.0, 0.0, 0.0)},
        )
        self.assertEqual(CanvasView._bond_ids_within_atom_ids(sparse_view, set()), set())
        self.assertIsNone(
            CanvasView._average_bond_length_for_atoms(
                sparse_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    3: (0.0, 0.0, 0.0),
                },
            )
        )
        self.assertEqual(CanvasView._rotation_scale_for_coords(sparse_view, {1, 2}, {}), 2.0)
        with mock.patch.object(CanvasView, "_average_bond_length_for_atoms", return_value=float("nan")):
            self.assertEqual(CanvasView._rotation_scale_for_coords(sparse_view, {1, 2}, {}), 1.0)
        with mock.patch.object(CanvasView, "_average_bond_length_for_atoms", return_value=0.0):
            self.assertEqual(CanvasView._rotation_scale_for_coords(sparse_view, {1, 2}, {}), 1.0)

        tail_view = SimpleNamespace(
            _atom_bond_ids={1: {0, 1, 2}, 2: {0, 2}, 3: {1}},
            model=SimpleNamespace(
                bonds=[
                    None,
                    Bond(1, 3, 1),
                    Bond(1, 2, 1),
                ]
            ),
        )
        self.assertIsNone(
            CanvasView._average_bond_length_for_atoms(
                tail_view,
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (0.0, 0.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            )
        )

    def test_bond_lookup_average_scale_and_axis_rotation_helpers(self) -> None:
        indexed_view = SimpleNamespace(
            _atom_bond_ids={1: {0, 99}, 2: {0, 1}, 3: {1, 2}},
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), Bond(2, 3, 1), Bond(3, 4, 1), None]),
            _rotation_base_bond_length=10.0,
            _rotation_base_coords={1: (0.0, 0.0, 0.0), 2: (8.0, 0.0, 0.0), 3: (18.0, 0.0, 0.0)},
            _redraw_bond=mock.Mock(),
        )

        self.assertEqual(CanvasView._bond_ids_for_atom_ids(indexed_view, {1, 2, 99}), {0, 1, 99})
        self.assertEqual(CanvasView._bond_ids_within_atom_ids(indexed_view, {1, 2, 3}), {0, 1})
        self.assertAlmostEqual(
            CanvasView._average_bond_length_for_atoms(
                indexed_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (3.0, 4.0, 0.0),
                    3: (3.0, 8.0, 0.0),
                },
            ),
            4.5,
        )
        self.assertAlmostEqual(
            CanvasView._rotation_scale_for_coords(
                indexed_view,
                {2},
                {2: (6.0, 0.0, 0.0)},
                extra_atom_ids={1, 3},
            ),
            10.0 / 9.0,
        )

        redraw_view = SimpleNamespace(_atom_bond_ids={1: {0}, 2: {0, 1}}, _redraw_bond=mock.Mock())
        CanvasView._redraw_bonds_for_atoms(redraw_view, {1, 2})
        self.assertEqual({call.args[0] for call in redraw_view._redraw_bond.call_args_list}, {0, 1})

        fallback_view = SimpleNamespace(
            _atom_bond_ids={},
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(2, 3, 1)]),
        )
        self.assertEqual(CanvasView._bond_ids_within_atom_ids(fallback_view, {1, 2, 3}), {0, 2})
        self.assertIsNone(CanvasView._average_bond_length_for_atoms(fallback_view, set(), {}))

        no_scale_view = SimpleNamespace(_rotation_base_bond_length=None, _rotation_base_coords={})
        self.assertEqual(CanvasView._rotation_scale_for_coords(no_scale_view, set(), {}), 1.0)

        rotated = CanvasView._rotate_point_around_axis(
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            math.pi / 2,
        )
        self.assertAlmostEqual(rotated[0], 0.0, places=6)
        self.assertAlmostEqual(rotated[1], 1.0, places=6)
        self.assertAlmostEqual(rotated[2], 0.0, places=6)
        self.assertEqual(
            CanvasView._rotate_point_around_axis(
                (1.0, 2.0, 3.0),
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                0.75,
            ),
            (1.0, 2.0, 3.0),
        )

    def test_bond_match_lookup_order_sum_and_normal_helpers(self) -> None:
        bonds = [Bond(1, 2, 2), Bond(2, 1, 3), None, Bond(1, 3, 0)]
        cached_view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds, atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}),
            _atom_bond_ids={1: {0, 1, 3}, 2: {0, 1}, 3: {3}},
            _project_point_3d=lambda point: (point[0], point[1]),
        )
        fallback_view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds, atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}),
            _atom_bond_ids={},
            _project_point_3d=lambda point: (point[0], point[1]),
        )

        self.assertFalse(CanvasView._bond_matches_atoms(None, 1, 2))
        self.assertTrue(CanvasView._bond_matches_atoms(bonds[0], 1, 2))
        self.assertTrue(CanvasView._bond_matches_atoms(bonds[0], 2, 1))
        self.assertEqual(CanvasView._first_matching_bond_id(bonds, 1, 2), 0)
        self.assertEqual(CanvasView._first_matching_bond_id(bonds, 1, 2, skip_bond_id=0), 1)
        self.assertIsNone(CanvasView._bond_id_between(cached_view, 1, 1))
        self.assertEqual(CanvasView._bond_id_between(cached_view, 1, 2), 0)
        self.assertEqual(CanvasView._bond_id_between(cached_view, 1, 2, skip_bond_id=0), 1)
        self.assertEqual(CanvasView._bond_id_between(fallback_view, 1, 2, skip_bond_id=0), 1)
        self.assertIsNone(CanvasView._first_matching_bond_id([Bond(3, 4, 1), None], 1, 2))
        self.assertIsNone(
            CanvasView._bond_id_between(
                SimpleNamespace(
                    model=SimpleNamespace(bonds=[Bond(3, 4, 1), None]),
                    _atom_bond_ids={1: {0, 1}, 2: {0, 1}},
                ),
                1,
                2,
            )
        )
        self.assertTrue(CanvasView._bond_exists(cached_view, 1, 2))
        self.assertFalse(CanvasView._bond_exists(cached_view, 2, 3))
        self.assertEqual(CanvasView._atom_bond_order_sum(cached_view, 1), 6)

        nx, ny, length = CanvasView._line_normal_components(0.0, 0.0, 10.0, 0.0)
        self.assertEqual((nx, ny, length), (0.0, 1.0, 10.0))
        self.assertEqual(CanvasView._line_normal_components(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        self.assertEqual(CanvasView._orient_normal_toward_target(0.0, 1.0, 5.0, 0.0, 5.0, -3.0), (0.0, -1.0))
        self.assertEqual(CanvasView._line_normal(SimpleNamespace(), 0.0, 0.0, 10.0, 0.0), (0.0, 1.0))
        self.assertEqual(
            CanvasView._line_normal(SimpleNamespace(), 0.0, 0.0, 10.0, 0.0, QPointF(5.0, -2.0)),
            (0.0, -1.0),
        )

        self.assertEqual(CanvasView._bond_offset_unit_3d(cached_view, 99, 2), None)
        self.assertEqual(
            CanvasView._bond_offset_unit_3d(
                SimpleNamespace(
                    model=SimpleNamespace(
                        atoms={1: Atom("C", 1.0, 1.0), 2: Atom("C", 1.0, 1.0)},
                    ),
                    _project_point_3d=lambda point: (point[0], point[1]),
                ),
                1,
                2,
            ),
            None,
        )
        self.assertEqual(CanvasView._bond_offset_unit_3d(cached_view, 1, 2), (0.0, 1.0))
        self.assertEqual(CanvasView._bond_offset_unit_3d(cached_view, 1, 2, target=(5.0, -2.0, 0.0)), (0.0, -1.0))

    def test_bond_renderer_wrappers_and_color_fallbacks_delegate_cleanly(self) -> None:
        wedge_polygon = object()
        hash_segments = [(0.0, 0.0, 1.0, 1.0)]
        strip_polygon = object()
        ring_segments = ((1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0), (0.0, 1.0))
        ring_bond = object()
        one_sided_strip = object()
        parallel_bonds = [object(), object()]
        wedge_bond = object()
        hash_bond = object()
        dotted_bond = object()
        dotted_path = object()
        renderer = SimpleNamespace(
            parallel_bond_segments=mock.Mock(return_value=hash_segments),
            wedge_polygon=mock.Mock(return_value=wedge_polygon),
            hash_segments=mock.Mock(return_value=hash_segments),
            strip_polygon=mock.Mock(return_value=strip_polygon),
            ring_double_segments=mock.Mock(return_value=ring_segments),
            update_bond_geometry=mock.Mock(),
            add_bond_graphics=mock.Mock(),
            draw_ring_double_bond=mock.Mock(return_value=ring_bond),
            one_sided_bond_strip=mock.Mock(return_value=one_sided_strip),
            draw_parallel_bonds=mock.Mock(return_value=parallel_bonds),
            draw_wedge_bond=mock.Mock(return_value=wedge_bond),
            draw_hash_bond=mock.Mock(return_value=hash_bond),
            draw_dotted_bond=mock.Mock(return_value=dotted_bond),
            dotted_bond_path=mock.Mock(return_value=dotted_path),
        )
        view = SimpleNamespace(_bond_renderer=renderer)
        center = QPointF(5.0, 6.0)

        self.assertEqual(CanvasView._parallel_bond_segments(view, 1.0, 2.0, 3.0, 4.0, 2, 7, 8), hash_segments)
        self.assertIs(CanvasView._wedge_polygon(view, 1.0, 2.0, 3.0, 4.0, 7, 8), wedge_polygon)
        self.assertEqual(CanvasView._hash_segments(view, 1.0, 2.0, 3.0, 4.0, 3, 7, 8), hash_segments)
        self.assertIs(CanvasView._strip_polygon(view, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), strip_polygon)
        self.assertEqual(CanvasView._ring_double_segments(view, "a", "b", center, 7, 8, (0.0, 0.0, 1.0)), ring_segments)
        CanvasView.update_bond_geometry(view, 4)
        CanvasView._add_bond_graphics(view, 5)
        self.assertIs(CanvasView._draw_ring_double_bond(view, "a", "b", center, 7, 8, outer_style="bold", center_3d=(1.0, 2.0, 3.0)), ring_bond)
        self.assertIs(CanvasView._one_sided_bond_strip(view, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), one_sided_strip)
        self.assertEqual(CanvasView._draw_parallel_bonds(view, 1.0, 2.0, 3.0, 4.0, 2, 7, 8), parallel_bonds)
        self.assertIs(CanvasView._draw_wedge_bond(view, 1.0, 2.0, 3.0, 4.0, 7, 8), wedge_bond)
        self.assertIs(CanvasView._draw_hash_bond(view, 1.0, 2.0, 3.0, 4.0, 7, 8), hash_bond)
        self.assertIs(CanvasView._draw_dotted_bond(view, 1.0, 2.0, 3.0, 4.0, 7, 8), dotted_bond)
        self.assertIs(CanvasView._dotted_bond_path(view, 1.0, 2.0, 3.0, 4.0, 7, 8), dotted_path)

        renderer.parallel_bond_segments.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 7, 8)
        renderer.wedge_polygon.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.hash_segments.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 3, 7, 8)
        renderer.strip_polygon.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        renderer.ring_double_segments.assert_called_once_with("a", "b", center, 7, 8, (0.0, 0.0, 1.0))
        renderer.update_bond_geometry.assert_called_once_with(4)
        renderer.add_bond_graphics.assert_called_once_with(5)
        renderer.draw_ring_double_bond.assert_called_once_with(
            "a",
            "b",
            center,
            7,
            8,
            outer_style="bold",
            center_3d=(1.0, 2.0, 3.0),
        )
        renderer.one_sided_bond_strip.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        renderer.draw_parallel_bonds.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 7, 8)
        renderer.draw_wedge_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.draw_hash_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.draw_dotted_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.dotted_bond_path.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)

        redraw_view = SimpleNamespace(_atom_bond_ids={1: {2, 3}}, _redraw_bond=mock.Mock())
        CanvasView._redraw_connected_bonds(redraw_view, 1, skip_bond_id=3)
        redraw_view._redraw_bond.assert_called_once_with(2)

        color = object()
        pen_and_brush_item = _FakePenBrushItem(Qt.BrushStyle.SolidPattern)
        brush_only_item = _FakeBrushOnlyItem(Qt.BrushStyle.SolidPattern)
        no_brush_item = _FakeBrushOnlyItem(Qt.BrushStyle.NoBrush)

        CanvasView._apply_color_to_bond_item(view, pen_and_brush_item, color)
        CanvasView._apply_color_to_bond_item(view, brush_only_item, color)
        CanvasView._apply_color_to_bond_item(view, no_brush_item, color)

        self.assertIs(pen_and_brush_item._pen.color, color)
        self.assertEqual(pen_and_brush_item.pen_updates, [pen_and_brush_item._pen])
        self.assertEqual(pen_and_brush_item.brush_updates, [color])
        self.assertEqual(brush_only_item.brush_updates, [color])
        self.assertEqual(no_brush_item.brush_updates, [])


if __name__ == "__main__":
    unittest.main()
