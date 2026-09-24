import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.ring_support import seed_ring_items
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import Atom, Bond
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    set_atom_items_for,
)
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas.canvas_scene_items_state import (
    CanvasSceneItemsState,
)
from chemvas.ui.molecule.atom_coords_access import CanvasAtomCoords3DState
from chemvas.ui.molecule.bond_graphics_access import (
    ring_center_3d_for_bond_for,
    ring_center_for_bond_for,
)
from tests.scene_render_context import (
    attach_scene_render_context,
    scene_geometry_for_test_canvas,
)


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


class CanvasViewLabelGeometryHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _bind_geometry_controller(self, view, controller=None):
        context = attach_scene_render_context(view)
        if controller is not None:
            context.geometry = controller
        return context.geometry

    def test_label_cut_radius_for_atom_uses_label_bounds_and_handles_missing_inputs(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[],
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 4.0, -2.0),
                },
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0)),
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )
        set_atom_items_for(view, {1: _FakeLabelItem(QRectF(-1.0, -1.0, 2.0, 2.0))})
        self._bind_geometry_controller(view)

        radius = view.render_context.geometry.label_cut_radius_for_atom(1)
        self.assertAlmostEqual(radius, (math.sqrt(2.0) + 0.03) * 0.6)

        self.assertIsNone(view.render_context.geometry.label_cut_radius_for_atom(2))
        empty_view = SimpleNamespace(
            model=view.model,
            renderer=view.renderer,
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )
        set_atom_items_for(empty_view, {})
        self._bind_geometry_controller(empty_view)
        self.assertIsNone(
            empty_view.render_context.geometry.label_cut_radius_for_atom(1)
        )

    def test_mark_target_distance_for_atom_uses_expanded_visible_label_rect(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 0.0, 0.0)}),
        )
        controller = scene_geometry_for_test_canvas(view)
        controller.visible_label_rect_for_atom = mock.Mock(
            return_value=QRectF(-2.0, -1.0, 4.0, 2.0)
        )
        controller.mark_clearance_for_kind = mock.Mock(return_value=1.0)
        self._bind_geometry_controller(view, controller)

        distance = view.render_context.geometry.mark_target_distance_for_atom(
            7, 1.0, 0.0, "plus"
        )
        self.assertAlmostEqual(distance, 3.0)
        controller.visible_label_rect_for_atom.assert_called_once_with(7)
        controller.mark_clearance_for_kind.assert_called_once_with("plus")

        missing_atom_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}),
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )
        self._bind_geometry_controller(missing_atom_view)
        self.assertEqual(
            missing_atom_view.render_context.geometry.mark_target_distance_for_atom(
                7, 1.0, 0.0, "minus"
            ),
            0.0,
        )

        missing_label_view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 0.0, 0.0)}),
        )
        missing_label_controller = scene_geometry_for_test_canvas(missing_label_view)
        missing_label_controller.visible_label_rect_for_atom = mock.Mock(
            return_value=None
        )
        self._bind_geometry_controller(missing_label_view, missing_label_controller)
        self.assertEqual(
            missing_label_view.render_context.geometry.mark_target_distance_for_atom(
                7, 1.0, 0.0, "minus"
            ),
            0.0,
        )

    def test_line_rect_intersections_returns_all_hits_and_skips_disjoint_lines(
        self,
    ) -> None:
        controller = scene_geometry_for_test_canvas(SimpleNamespace())

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
        zero_controller = scene_geometry_for_test_canvas(zero_view)
        zero_controller.label_cut_radius_for_atom = zero_label_cut_radius
        self._bind_geometry_controller(zero_view, zero_controller)
        self.assertEqual(
            zero_view.render_context.geometry.trim_line_for_labels(
                1, 2, 0.0, 0.0, 0.0, 0.0
            ),
            (0.0, 1.0),
        )
        zero_label_cut_radius.assert_not_called()

        start_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )
        start_controller = scene_geometry_for_test_canvas(start_view)
        start_controller.label_cut_radius_for_atom = lambda atom_id: {1: 5.0}[atom_id]
        self._bind_geometry_controller(start_view, start_controller)
        start_only = start_view.render_context.geometry.trim_line_for_labels(
            1, None, 0.0, 0.0, 100.0, 0.0
        )
        self.assertAlmostEqual(start_only[0], 0.051)
        self.assertEqual(start_only[1], 1.0)

        end_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )
        end_controller = scene_geometry_for_test_canvas(end_view)
        end_controller.label_cut_radius_for_atom = lambda atom_id: {2: 5.0}[atom_id]
        self._bind_geometry_controller(end_view, end_controller)
        end_only = end_view.render_context.geometry.trim_line_for_labels(
            None, 2, 0.0, 0.0, 100.0, 0.0
        )
        self.assertEqual(end_only[0], 0.0)
        self.assertAlmostEqual(end_only[1], 0.949)

        tight_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState()
            ),
        )
        tight_controller = scene_geometry_for_test_canvas(tight_view)
        tight_controller.label_cut_radius_for_atom = lambda atom_id: {1: 49.6, 2: 49.6}[
            atom_id
        ]
        self._bind_geometry_controller(tight_view, tight_controller)
        both = tight_view.render_context.geometry.trim_line_for_labels(
            1, 2, 0.0, 0.0, 100.0, 0.0
        )
        self.assertAlmostEqual(both[0], 0.49)
        self.assertAlmostEqual(both[1], 0.51)

    def test_ring_center_for_bond_averages_atoms_in_matching_ring(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[],
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 6.0, 0.0),
                    3: Atom("C", 0.0, 6.0),
                    4: Atom("C", 50.0, 50.0),
                    5: Atom("C", 60.0, 50.0),
                    6: Atom("C", 50.0, 60.0),
                },
            ),
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState()
            ),
        )
        seed_ring_items(
            view,
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
                bonds=[],
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 6.0, 0.0),
                    3: Atom("C", 0.0, 6.0),
                },
            ),
            renderer=renderer,
            runtime_state=canvas_runtime_state(
                atom_coords_3d_state=CanvasAtomCoords3DState(atom_coords_3d=coords_map),
                rotation_state=CanvasRotationState(),
                scene_items_state=CanvasSceneItemsState(),
            ),
        )
        seed_ring_items(view, [_FakeRingItem([1, 2, 3]), _FakeRingItem([4, 5, 6])])
        self._bind_geometry_controller(view)

        center = ring_center_3d_for_bond_for(view, Bond(1, 2, 1))
        self.assertEqual(center, (2.0, 2.0, 2.0))

        sparse_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[],
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 6.0, 0.0),
                },
            ),
            renderer=renderer,
            runtime_state=canvas_runtime_state(
                atom_coords_3d_state=CanvasAtomCoords3DState(atom_coords_3d=coords_map),
                rotation_state=CanvasRotationState(),
                scene_items_state=CanvasSceneItemsState(),
            ),
        )
        seed_ring_items(sparse_view, [_FakeRingItem([1, 2, 4])])
        self._bind_geometry_controller(sparse_view)
        self.assertIsNone(ring_center_3d_for_bond_for(sparse_view, Bond(1, 2, 1)))

        self.assertIsNone(ring_center_3d_for_bond_for(view, Bond(1, 4, 1)))

    def test_geometry_access_helpers_delegate_to_render_context(self) -> None:
        controller = mock.Mock()
        view = SimpleNamespace(render_context=SimpleNamespace(geometry=controller))
        bond = Bond(1, 2, 1)

        ring_center_for_bond_for(view, bond)
        ring_center_3d_for_bond_for(view, bond)
        view.render_context.geometry.label_rect_for_atom(4)
        view.render_context.geometry.trim_line_for_labels(1, 2, 0.0, 0.0, 3.0, 4.0)
        view.render_context.geometry.mark_target_distance_for_atom(7, 1.0, 0.0, "minus")

        controller.ring_center_for_bond.assert_called_once_with(bond)
        controller.ring_center_3d_for_bond.assert_called_once_with(bond)
        controller.label_rect_for_atom.assert_called_once_with(4)
        controller.mark_target_distance_for_atom.assert_called_once_with(
            7, 1.0, 0.0, "minus"
        )
        controller.trim_line_for_labels.assert_called_once_with(
            1, 2, 0.0, 0.0, 3.0, 4.0
        )
        controller.trim_line_for_labels.reset_mock()
        offsets = ((0.0, 0.0), (1.0, 2.0))
        view.render_context.geometry.trim_line_for_labels(
            1, 2, 0.0, 0.0, 3.0, 4.0, offsets
        )
        controller.trim_line_for_labels.assert_called_once_with(
            1, 2, 0.0, 0.0, 3.0, 4.0, offsets
        )
