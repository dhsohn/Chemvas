import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_view import CanvasView


class _FakeLabelItem:
    def __init__(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewLabelGeometryHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_label_cut_radius_for_atom_uses_label_bounds_and_handles_missing_inputs(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 4.0, -2.0),
                }
            ),
            atom_items={1: _FakeLabelItem(QRectF(-1.0, -1.0, 2.0, 2.0))},
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0)),
        )

        radius = CanvasView._label_cut_radius_for_atom(view, 1)
        self.assertAlmostEqual(radius, (math.sqrt(2.0) + 0.03) * 0.6)

        self.assertIsNone(CanvasView._label_cut_radius_for_atom(view, 2))
        self.assertIsNone(CanvasView._label_cut_radius_for_atom(SimpleNamespace(model=view.model, atom_items={}, renderer=view.renderer), 1))

    def test_mark_target_distance_for_atom_uses_expanded_visible_label_rect(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 0.0, 0.0)}),
            _visible_label_rect_for_atom=mock.Mock(return_value=QRectF(-2.0, -1.0, 4.0, 2.0)),
            _mark_clearance_for_kind=mock.Mock(return_value=1.0),
        )
        view._ray_rect_exit_distance = lambda origin, direction, rect: CanvasView._ray_rect_exit_distance(
            view,
            origin,
            direction,
            rect,
        )

        distance = CanvasView._mark_target_distance_for_atom(view, 7, 1.0, 0.0, "plus")
        self.assertAlmostEqual(distance, 3.0)
        view._visible_label_rect_for_atom.assert_called_once_with(7)
        view._mark_clearance_for_kind.assert_called_once_with("plus")

        self.assertEqual(
            CanvasView._mark_target_distance_for_atom(
                SimpleNamespace(model=SimpleNamespace(atoms={}), _visible_label_rect_for_atom=mock.Mock(), _mark_clearance_for_kind=mock.Mock()),
                7,
                1.0,
                0.0,
                "minus",
            ),
            0.0,
        )

        self.assertEqual(
            CanvasView._mark_target_distance_for_atom(
                SimpleNamespace(
                    model=SimpleNamespace(atoms={7: Atom("C", 0.0, 0.0)}),
                    _visible_label_rect_for_atom=mock.Mock(return_value=None),
                    _mark_clearance_for_kind=mock.Mock(),
                ),
                7,
                1.0,
                0.0,
                "minus",
            ),
            0.0,
        )

    def test_line_rect_intersections_returns_all_hits_and_skips_disjoint_lines(self) -> None:
        view = SimpleNamespace()
        view._segment_intersection_t = lambda p1, p2, q1, q2: CanvasView._segment_intersection_t(view, p1, p2, q1, q2)

        hits = CanvasView._line_rect_intersections(
            view,
            QPointF(-1.0, 1.0),
            QPointF(3.0, 1.0),
            QRectF(0.0, 0.0, 2.0, 2.0),
        )
        self.assertCountEqual(hits, [0.25, 0.75])

        self.assertEqual(
            CanvasView._line_rect_intersections(
                view,
                QPointF(-1.0, 3.0),
                QPointF(3.0, 3.0),
                QRectF(0.0, 0.0, 2.0, 2.0),
            ),
            [],
        )

    def test_trim_line_for_labels_handles_zero_length_and_label_trimming(self) -> None:
        zero_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            _label_cut_radius_for_atom=mock.Mock(),
        )
        self.assertEqual(CanvasView._trim_line_for_labels(zero_view, 1, 2, 0.0, 0.0, 0.0, 0.0), (0.0, 1.0))
        zero_view._label_cut_radius_for_atom.assert_not_called()

        start_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            _label_cut_radius_for_atom=mock.Mock(side_effect=lambda atom_id: {1: 5.0}[atom_id]),
        )
        start_only = CanvasView._trim_line_for_labels(start_view, 1, None, 0.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(start_only[0], 0.051)
        self.assertEqual(start_only[1], 1.0)

        end_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            _label_cut_radius_for_atom=mock.Mock(side_effect=lambda atom_id: {2: 5.0}[atom_id]),
        )
        end_only = CanvasView._trim_line_for_labels(end_view, None, 2, 0.0, 0.0, 100.0, 0.0)
        self.assertEqual(end_only[0], 0.0)
        self.assertAlmostEqual(end_only[1], 0.949)

        tight_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            _label_cut_radius_for_atom=mock.Mock(side_effect=lambda atom_id: {1: 49.6, 2: 49.6}[atom_id]),
        )
        both = CanvasView._trim_line_for_labels(tight_view, 1, 2, 0.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(both[0], 0.49)
        self.assertAlmostEqual(both[1], 0.51)

    def test_ring_center_for_bond_averages_atoms_in_matching_ring(self) -> None:
        view = SimpleNamespace(
            ring_items=[
                _FakeRingItem("not-a-list"),
                _FakeRingItem([4, 5, 6]),
                _FakeRingItem([1, 2, 3]),
            ],
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 6.0, 0.0),
                    3: Atom("C", 0.0, 6.0),
                    4: Atom("C", 50.0, 50.0),
                    5: Atom("C", 60.0, 50.0),
                    6: Atom("C", 50.0, 60.0),
                }
            ),
        )

        center = CanvasView._ring_center_for_bond(view, Bond(1, 2, 1))
        self.assertIsNotNone(center)
        self.assertAlmostEqual(center.x(), 2.0)
        self.assertAlmostEqual(center.y(), 2.0)

        self.assertIsNone(CanvasView._ring_center_for_bond(view, Bond(1, 4, 1)))

    def test_ring_center_3d_for_bond_averages_coords_and_needs_three_points(self) -> None:
        coords_map = {
            1: (0.0, 0.0, 0.0),
            2: (6.0, 0.0, 0.0),
            3: (0.0, 6.0, 6.0),
        }
        view = SimpleNamespace(
            ring_items=[_FakeRingItem([1, 2, 3]), _FakeRingItem([4, 5, 6])],
            _current_atom_coords_3d=mock.Mock(side_effect=lambda atom_id: coords_map.get(atom_id)),
        )

        center = CanvasView._ring_center_3d_for_bond(view, Bond(1, 2, 1))
        self.assertEqual(center, (2.0, 2.0, 2.0))

        sparse_view = SimpleNamespace(
            ring_items=[_FakeRingItem([1, 2, 4])],
            _current_atom_coords_3d=mock.Mock(side_effect=lambda atom_id: coords_map.get(atom_id) if atom_id != 4 else None),
        )
        self.assertIsNone(CanvasView._ring_center_3d_for_bond(sparse_view, Bond(1, 2, 1)))

        self.assertIsNone(CanvasView._ring_center_3d_for_bond(view, Bond(1, 4, 1)))

    def test_geometry_wrappers_delegate_to_controller(self) -> None:
        view = SimpleNamespace()
        controller = mock.Mock()
        bond = Bond(1, 2, 1)
        label_item = mock.Mock()
        rect = QRectF(0.0, 0.0, 1.0, 1.0)
        point = QPointF(1.0, 2.0)

        with mock.patch("ui.canvas_view._geometry_controller_for", return_value=controller):
            CanvasView._ring_center_for_bond(view, bond)
            CanvasView._ring_center_3d_for_bond(view, bond)
            CanvasView._ring_for_bond(view, 3)
            CanvasView._label_rect_for_atom(view, 4)
            CanvasView._visible_text_rect(view, label_item)
            CanvasView._visible_label_rect_for_atom(view, 5)
            CanvasView._label_cut_radius_for_atom(view, 6)
            CanvasView._line_rect_clip_t(view, point, point, rect)
            CanvasView._segment_intersection_t(view, point, point, point, point)
            CanvasView._ray_rect_exit_distance(view, point, point, rect)
            CanvasView._mark_clearance_for_kind(view, "plus")
            CanvasView._mark_target_distance_for_atom(view, 7, 1.0, 0.0, "minus")
            CanvasView._line_rect_intersections(view, point, point, rect)
            CanvasView._trim_line_for_labels(view, 1, 2, 0.0, 0.0, 3.0, 4.0)

        controller.ring_center_for_bond.assert_called_once_with(bond)
        controller.ring_center_3d_for_bond.assert_called_once_with(bond)
        controller.ring_for_bond.assert_called_once_with(3)
        controller.label_rect_for_atom.assert_called_once_with(4)
        controller.visible_text_rect.assert_called_once_with(label_item)
        controller.visible_label_rect_for_atom.assert_called_once_with(5)
        controller.label_cut_radius_for_atom.assert_called_once_with(6)
        controller.line_rect_clip_t.assert_called_once_with(point, point, rect)
        controller.segment_intersection_t.assert_called_once_with(point, point, point, point)
        controller.ray_rect_exit_distance.assert_called_once_with(point, point, rect)
        controller.mark_clearance_for_kind.assert_called_once_with("plus")
        controller.mark_target_distance_for_atom.assert_called_once_with(7, 1.0, 0.0, "minus")
        controller.line_rect_intersections.assert_called_once_with(point, point, rect)
        controller.trim_line_for_labels.assert_called_once_with(1, 2, 0.0, 0.0, 3.0, 4.0)
