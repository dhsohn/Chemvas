import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
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


if __name__ == "__main__":
    unittest.main()
