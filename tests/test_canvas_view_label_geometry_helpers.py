import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.atom_coords_access import CanvasAtomCoords3DState
    from chemvas.ui.bond_graphics_access import (
        ring_center_3d_for_bond_for,
        ring_center_for_bond_for,
    )
    from chemvas.ui.bond_label_geometry_access import (
        label_rect_for_atom_for,
        trim_line_for_labels_for,
    )
    from chemvas.ui.canvas_atom_graphics_state import set_atom_items_for
    from chemvas.ui.canvas_geometry_access import (
        label_cut_radius_for_atom_for,
        mark_clearance_for_kind_for,
        mark_target_distance_for_atom_for,
        visible_label_rect_for_atom_for,
    )
    from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
    from chemvas.ui.canvas_scene_items_state import set_scene_item_collection_for


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


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewLabelGeometryHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _bind_geometry_controller(self, view, controller=None):
        controller = (
            CanvasGeometryController(view) if controller is None else controller
        )
        services = getattr(view, "services", None)
        if services is None:
            services = canvas_runtime_services()
            view.services = services
        services.geometry_controller = controller
        return controller

    def test_label_cut_radius_for_atom_uses_label_bounds_and_handles_missing_inputs(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 4.0, -2.0),
                }
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0)),
        )
        set_atom_items_for(view, {1: _FakeLabelItem(QRectF(-1.0, -1.0, 2.0, 2.0))})
        self._bind_geometry_controller(view)

        radius = label_cut_radius_for_atom_for(view, 1)
        self.assertAlmostEqual(radius, (math.sqrt(2.0) + 0.03) * 0.6)

        self.assertIsNone(label_cut_radius_for_atom_for(view, 2))
        empty_view = SimpleNamespace(model=view.model, renderer=view.renderer)
        set_atom_items_for(empty_view, {})
        self._bind_geometry_controller(empty_view)
        self.assertIsNone(label_cut_radius_for_atom_for(empty_view, 1))

    def test_mark_target_distance_for_atom_uses_expanded_visible_label_rect(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 0.0, 0.0)}),
        )
        controller = CanvasGeometryController(view)
        controller.visible_label_rect_for_atom = mock.Mock(
            return_value=QRectF(-2.0, -1.0, 4.0, 2.0)
        )
        controller.mark_clearance_for_kind = mock.Mock(return_value=1.0)
        self._bind_geometry_controller(view, controller)

        distance = mark_target_distance_for_atom_for(view, 7, 1.0, 0.0, "plus")
        self.assertAlmostEqual(distance, 3.0)
        controller.visible_label_rect_for_atom.assert_called_once_with(7)
        controller.mark_clearance_for_kind.assert_called_once_with("plus")

        missing_atom_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}),
        )
        self._bind_geometry_controller(missing_atom_view)
        self.assertEqual(
            mark_target_distance_for_atom_for(missing_atom_view, 7, 1.0, 0.0, "minus"),
            0.0,
        )

        missing_label_view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 0.0, 0.0)}),
        )
        missing_label_controller = CanvasGeometryController(missing_label_view)
        missing_label_controller.visible_label_rect_for_atom = mock.Mock(
            return_value=None
        )
        self._bind_geometry_controller(missing_label_view, missing_label_controller)
        self.assertEqual(
            mark_target_distance_for_atom_for(missing_label_view, 7, 1.0, 0.0, "minus"),
            0.0,
        )

    def test_line_rect_intersections_returns_all_hits_and_skips_disjoint_lines(
        self,
    ) -> None:
        controller = CanvasGeometryController(SimpleNamespace())

        hits = controller.line_rect_intersections(
            QPointF(-1.0, 1.0),
            QPointF(3.0, 1.0),
            QRectF(0.0, 0.0, 2.0, 2.0),
        )
        self.assertCountEqual(hits, [0.25, 0.75])

        self.assertEqual(
            controller.line_rect_intersections(
                QPointF(-1.0, 3.0),
                QPointF(3.0, 3.0),
                QRectF(0.0, 0.0, 2.0, 2.0),
            ),
            [],
        )

    def test_trim_line_for_labels_handles_zero_length_and_label_trimming(self) -> None:
        zero_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
        )
        zero_label_cut_radius = mock.Mock()
        zero_controller = CanvasGeometryController(zero_view)
        zero_controller.label_cut_radius_for_atom = zero_label_cut_radius
        self._bind_geometry_controller(zero_view, zero_controller)
        self.assertEqual(
            trim_line_for_labels_for(zero_view, 1, 2, 0.0, 0.0, 0.0, 0.0), (0.0, 1.0)
        )
        zero_label_cut_radius.assert_not_called()

        start_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
        )
        start_controller = CanvasGeometryController(start_view)
        start_controller.label_cut_radius_for_atom = lambda atom_id: {1: 5.0}[atom_id]
        self._bind_geometry_controller(start_view, start_controller)
        start_only = trim_line_for_labels_for(start_view, 1, None, 0.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(start_only[0], 0.051)
        self.assertEqual(start_only[1], 1.0)

        end_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
        )
        end_controller = CanvasGeometryController(end_view)
        end_controller.label_cut_radius_for_atom = lambda atom_id: {2: 5.0}[atom_id]
        self._bind_geometry_controller(end_view, end_controller)
        end_only = trim_line_for_labels_for(end_view, None, 2, 0.0, 0.0, 100.0, 0.0)
        self.assertEqual(end_only[0], 0.0)
        self.assertAlmostEqual(end_only[1], 0.949)

        tight_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
        )
        tight_controller = CanvasGeometryController(tight_view)
        tight_controller.label_cut_radius_for_atom = lambda atom_id: {1: 49.6, 2: 49.6}[
            atom_id
        ]
        self._bind_geometry_controller(tight_view, tight_controller)
        both = trim_line_for_labels_for(tight_view, 1, 2, 0.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(both[0], 0.49)
        self.assertAlmostEqual(both[1], 0.51)

    def test_ring_center_for_bond_averages_atoms_in_matching_ring(self) -> None:
        view = SimpleNamespace(
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
        set_scene_item_collection_for(
            view,
            "ring_items",
            [
                _FakeRingItem("not-a-list"),
                _FakeRingItem([4, 5, 6]),
                _FakeRingItem([1, 2, 3]),
            ],
        )
        self._bind_geometry_controller(view)

        center = ring_center_for_bond_for(view, Bond(1, 2, 1))
        self.assertIsNotNone(center)
        self.assertAlmostEqual(center.x(), 2.0)
        self.assertAlmostEqual(center.y(), 2.0)

        self.assertIsNone(ring_center_for_bond_for(view, Bond(1, 4, 1)))

    def test_ring_center_3d_for_bond_averages_coords_and_needs_three_points(
        self,
    ) -> None:
        coords_map = {
            1: (0.0, 0.0, 0.0),
            2: (6.0, 0.0, 0.0),
            3: (0.0, 6.0, 6.0),
        }
        renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 6.0, 0.0),
                    3: Atom("C", 0.0, 6.0),
                }
            ),
            atom_coords_3d_state=CanvasAtomCoords3DState(atom_coords_3d=coords_map),
            renderer=renderer,
        )
        set_scene_item_collection_for(
            view, "ring_items", [_FakeRingItem([1, 2, 3]), _FakeRingItem([4, 5, 6])]
        )
        self._bind_geometry_controller(view)

        center = ring_center_3d_for_bond_for(view, Bond(1, 2, 1))
        self.assertEqual(center, (2.0, 2.0, 2.0))

        sparse_view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 6.0, 0.0),
                }
            ),
            atom_coords_3d_state=CanvasAtomCoords3DState(atom_coords_3d=coords_map),
            renderer=renderer,
        )
        set_scene_item_collection_for(
            sparse_view, "ring_items", [_FakeRingItem([1, 2, 4])]
        )
        self._bind_geometry_controller(sparse_view)
        self.assertIsNone(ring_center_3d_for_bond_for(sparse_view, Bond(1, 2, 1)))

        self.assertIsNone(ring_center_3d_for_bond_for(view, Bond(1, 4, 1)))

    def test_geometry_access_helpers_delegate_to_controller(self) -> None:
        controller = mock.Mock()
        view = SimpleNamespace(
            services=canvas_runtime_services(geometry_controller=controller)
        )
        bond = Bond(1, 2, 1)

        ring_center_for_bond_for(view, bond)
        ring_center_3d_for_bond_for(view, bond)
        label_rect_for_atom_for(view, 4)
        trim_line_for_labels_for(view, 1, 2, 0.0, 0.0, 3.0, 4.0)
        visible_label_rect_for_atom_for(view, 5)
        label_cut_radius_for_atom_for(view, 6)
        mark_clearance_for_kind_for(view, "plus")
        mark_target_distance_for_atom_for(view, 7, 1.0, 0.0, "minus")

        controller.ring_center_for_bond.assert_called_once_with(bond)
        controller.ring_center_3d_for_bond.assert_called_once_with(bond)
        controller.label_rect_for_atom.assert_called_once_with(4)
        controller.visible_label_rect_for_atom.assert_called_once_with(5)
        controller.label_cut_radius_for_atom.assert_called_once_with(6)
        controller.mark_clearance_for_kind.assert_called_once_with("plus")
        controller.mark_target_distance_for_atom.assert_called_once_with(
            7, 1.0, 0.0, "minus"
        )
        controller.trim_line_for_labels.assert_called_once_with(
            1, 2, 0.0, 0.0, 3.0, 4.0
        )
