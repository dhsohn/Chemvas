"""Differential checks for shared absolute atom geometry ownership."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import Atom, MoleculeModel
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    set_atom_dots_for,
    set_atom_items_for,
)
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas.spatial_index_state import CanvasSpatialIndexState
from chemvas.ui.molecule.atom_coords_access import (
    CanvasAtomCoords3DState,
    set_atom_coords_3d_for,
)
from chemvas.ui.selection.selection_rotation_access import (
    apply_projected_atom_positions_for,
)
from chemvas.ui.selection.selection_rotation_preview_transaction import (
    _RotationPreviewAuthority,
)


class _RecordingDot:
    def __init__(self) -> None:
        self.positions: list[tuple[float, float]] = []

    def setPos(self, x: float, y: float) -> None:
        self.positions.append((x, y))


class _RecordingMark:
    def __init__(self, payload: dict) -> None:
        self._payload = dict(payload)

    def data(self, key):
        if key == 1:
            return self._payload
        return None


def _accessory_snapshot(view) -> dict[str, object]:
    label_calls = view.services.atom_label_service.position_label.call_args_list
    mark_calls = (
        view.services.scene_decoration_build_service.set_mark_center.call_args_list
    )
    return {
        "atoms": {
            atom_id: (atom.x, atom.y) for atom_id, atom in view.model.atoms.items()
        },
        "coords_3d": dict(view.runtime_state.atom_coords_3d_state.atom_coords_3d),
        "labels": [(call.args[0], call.args[1], call.args[2]) for call in label_calls],
        "dots": {
            atom_id: list(dot.positions)
            for atom_id, dot in view.runtime_state.atom_graphics_state.atom_dots.items()
        },
        "marks": [
            (call.args[0], (call.args[1].x(), call.args[1].y())) for call in mark_calls
        ],
    }


class AtomGeometrySyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_view(self, *, atoms, marks=None, coords_3d=None):
        label_service = SimpleNamespace(position_label=mock.Mock())
        decoration = SimpleNamespace(set_mark_center=mock.Mock())
        spatial = CanvasSpatialIndexState(dirty=True)
        dirty_calls: list[str] = []

        def mark_spatial_index_dirty() -> None:
            spatial.dirty = True
            dirty_calls.append("dirty")

        hit = SimpleNamespace(
            mark_spatial_index_dirty=mock.Mock(side_effect=mark_spatial_index_dirty)
        )
        view = SimpleNamespace(
            model=MoleculeModel(atoms=atoms),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            services=canvas_runtime_services(
                atom_label_service=label_service,
                scene_decoration_build_service=decoration,
                hit_testing_service=hit,
                canvas_ring_fill_scene_service=SimpleNamespace(
                    update_ring_fills_for_atoms=mock.Mock()
                ),
                selection=SimpleNamespace(update_selection_outline=mock.Mock()),
            ),
            runtime_state=canvas_runtime_state(
                spatial_index_state=spatial,
                rotation_state=CanvasRotationState(),
                atom_coords_3d_state=CanvasAtomCoords3DState(),
                atom_graphics_state=CanvasAtomGraphicsState(),
                mark_registry=CanvasMarkRegistry(marks or {}),
            ),
        )
        view._spatial_dirty_calls = dirty_calls
        controller = CanvasMoveController(view, hit_testing_service=hit)
        view.services.move_controller = controller
        if coords_3d is not None:
            set_atom_coords_3d_for(view, dict(coords_3d))
        return view, controller

    def test_absolute_and_projected_paths_agree_on_accessories(self) -> None:
        """Same screen/3D targets via absolute owner vs projection adapter."""
        mark_offset = _RecordingMark({"dx": 2.0, "dy": -1.5})
        mark_plain = _RecordingMark({})
        label = object()
        dot = _RecordingDot()
        screen = {1: (11.0, -3.0), 2: (15.0, 2.0)}
        coords = {1: (1.0, 2.0, 3.0), 2: (5.0, 7.0, 11.0)}

        absolute_view, absolute = self._make_view(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 4.0, 5.0)},
            marks={1: [mark_offset, mark_plain]},
        )
        set_atom_items_for(absolute_view, {1: label})
        set_atom_dots_for(absolute_view, {1: dot})
        absolute.apply_atom_geometry(screen, coords_3d=coords)
        absolute_snapshot = _accessory_snapshot(absolute_view)

        projected_mark_offset = _RecordingMark({"dx": 2.0, "dy": -1.5})
        projected_mark_plain = _RecordingMark({})
        projected_label = object()
        projected_dot = _RecordingDot()
        projected_view, _projected = self._make_view(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 4.0, 5.0)},
            marks={1: [projected_mark_offset, projected_mark_plain]},
        )
        set_atom_items_for(projected_view, {1: projected_label})
        set_atom_dots_for(projected_view, {1: projected_dot})
        with mock.patch(
            "chemvas.ui.selection.selection_rotation_access.project_point_3d_for",
            side_effect=lambda canvas, point: screen[
                next(atom_id for atom_id, value in coords.items() if value == point)
            ],
        ):
            apply_projected_atom_positions_for(projected_view, {1, 2}, coords)
        projected_snapshot = _accessory_snapshot(projected_view)

        self.assertEqual(absolute_snapshot["atoms"], projected_snapshot["atoms"])
        self.assertEqual(
            absolute_snapshot["coords_3d"], projected_snapshot["coords_3d"]
        )
        self.assertEqual(
            [(1, 11.0, -3.0)],
            [
                (1, call.args[1], call.args[2])
                for call in absolute_view.services.atom_label_service.position_label.call_args_list
            ],
        )
        self.assertEqual(
            [
                (1, call.args[1], call.args[2])
                for call in absolute_view.services.atom_label_service.position_label.call_args_list
            ],
            [
                (1, call.args[1], call.args[2])
                for call in projected_view.services.atom_label_service.position_label.call_args_list
            ],
        )
        self.assertEqual(dot.positions, projected_dot.positions)
        absolute_marks = [
            (call.args[1].x(), call.args[1].y())
            for call in absolute_view.services.scene_decoration_build_service.set_mark_center.call_args_list
        ]
        projected_marks = [
            (call.args[1].x(), call.args[1].y())
            for call in projected_view.services.scene_decoration_build_service.set_mark_center.call_args_list
        ]
        self.assertEqual(absolute_marks, [(13.0, -4.5), (11.0, -3.0)])
        self.assertEqual(absolute_marks, projected_marks)

    def test_apply_atom_geometry_cache_cases_and_missing_atoms(self) -> None:
        view, controller = self._make_view(
            atoms={1: Atom("C", 1.0, 1.0), 2: Atom("O", 5.0, 5.0)},
            coords_3d={1: (1.0, 1.0, 4.0), 2: (5.0, 5.0, 2.0), 7: (9.0, 9.0, 9.0)},
        )
        label = object()
        set_atom_items_for(view, {1: label})

        affected = controller.apply_atom_geometry(
            {1: (3.0, 4.0), 99: (0.0, 0.0)},
            coords_3d={
                1: (10.0, 11.0, 12.0),
                2: None,
                7: (1.0, 2.0, 3.0),
                98: (4.0, 5.0, 6.0),
            },
        )

        self.assertEqual(affected, {1, 2, 7, 98})
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (3.0, 4.0))
        self.assertEqual((view.model.atoms[2].x, view.model.atoms[2].y), (5.0, 5.0))
        self.assertEqual(
            view.runtime_state.atom_coords_3d_state.atom_coords_3d,
            {1: (10.0, 11.0, 12.0), 7: (1.0, 2.0, 3.0), 98: (4.0, 5.0, 6.0)},
        )
        view.services.atom_label_service.position_label.assert_called_once_with(
            label, 3.0, 4.0
        )
        # Cache-only and missing-atom entries must not invent accessories.
        view.services.scene_decoration_build_service.set_mark_center.assert_not_called()

        filtered = controller.set_atom_positions
        before = dict(view.runtime_state.atom_coords_3d_state.atom_coords_3d)
        filtered(
            positions={99: (8.0, 8.0)},
            coords_3d={97: (7.0, 7.0, 7.0)},
            update_selection=False,
        )
        self.assertEqual(view.runtime_state.atom_coords_3d_state.atom_coords_3d, before)

    def test_set_atom_positions_preserves_depth_when_3d_entry_absent(self) -> None:
        view, controller = self._make_view(
            atoms={1: Atom("C", 0.0, 0.0)},
            coords_3d={1: (0.0, 0.0, 5.0)},
        )
        controller.set_atom_positions({1: (2.0, -3.0)}, update_selection=False)
        self.assertEqual(
            view.runtime_state.atom_coords_3d_state.atom_coords_3d[1],
            (2.0, -3.0, 5.0),
        )

    def test_partial_accessory_failure_restores_and_retries(self) -> None:
        mark_a = _RecordingMark({"dx": 1.0, "dy": 2.0})
        mark_b = _RecordingMark({"dx": -1.0, "dy": 0.0})
        view, controller = self._make_view(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 10.0, 0.0)},
            marks={1: [mark_a], 2: [mark_b]},
            coords_3d={1: (0.0, 0.0, 1.0), 2: (10.0, 0.0, 2.0)},
        )
        set_atom_items_for(view, {1: object(), 2: object()})
        set_atom_dots_for(view, {1: _RecordingDot(), 2: _RecordingDot()})

        saved_positions = {
            1: (view.model.atoms[1].x, view.model.atoms[1].y),
            2: (view.model.atoms[2].x, view.model.atoms[2].y),
        }
        saved_coords = dict(view.runtime_state.atom_coords_3d_state.atom_coords_3d)
        calls = {"count": 0}
        original = view.services.scene_decoration_build_service.set_mark_center

        def fail_after_first(mark, center) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("partial accessory sync failed")
            return original(mark, center)

        view.services.scene_decoration_build_service.set_mark_center = fail_after_first
        view.runtime_state.spatial_index_state.dirty = False
        view._spatial_dirty_calls.clear()
        with self.assertRaisesRegex(RuntimeError, "partial accessory sync failed"):
            controller.apply_atom_geometry(
                {1: (4.0, 5.0), 2: (14.0, 5.0)},
                coords_3d={1: (4.0, 5.0, 1.0), 2: (14.0, 5.0, 2.0)},
            )
        # Previously-clean index must be dirty even when accessory sync aborts.
        self.assertTrue(view.runtime_state.spatial_index_state.dirty)
        self.assertEqual(view._spatial_dirty_calls, ["dirty"])
        view.services.hit_testing_service.mark_spatial_index_dirty.assert_called()

        # Frame-style recovery uses saved screen values and exact cache tuples.
        view.services.scene_decoration_build_service.set_mark_center = original
        view.services.atom_label_service.position_label.reset_mock()
        authority = _RotationPreviewAuthority(
            controller=SimpleNamespace(
                canvas=view,
                refresh_atom_geometry=mock.Mock(),
                rotation=SimpleNamespace(),
            ),
            atom_ids=frozenset({1, 2}),
            affected_ring_items=(),
            scene_rect_snapshot=None,
        )
        authority._reapply_coords(
            {
                1: (saved_positions[1], saved_coords[1]),
                2: (saved_positions[2], saved_coords[2]),
            }
        )
        self.assertEqual(
            (view.model.atoms[1].x, view.model.atoms[1].y), saved_positions[1]
        )
        self.assertEqual(
            (view.model.atoms[2].x, view.model.atoms[2].y), saved_positions[2]
        )
        self.assertEqual(
            view.runtime_state.atom_coords_3d_state.atom_coords_3d, saved_coords
        )

        # Retry after restore succeeds.
        controller.apply_atom_geometry(
            {1: (4.0, 5.0), 2: (14.0, 5.0)},
            coords_3d={1: (4.0, 5.0, 1.0), 2: (14.0, 5.0, 2.0)},
        )
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (4.0, 5.0))
        self.assertEqual((view.model.atoms[2].x, view.model.atoms[2].y), (14.0, 5.0))

    def test_restore_mixed_cache_states_keeps_unrelated_screen_items_still(
        self,
    ) -> None:
        unrelated_label = object()
        view, controller = self._make_view(
            atoms={
                1: Atom("C", 1.0, 2.0),
                2: Atom("O", 3.0, 4.0),
                3: Atom("N", 8.0, 9.0),
            },
            coords_3d={
                1: (1.0, 2.0, 1.0),
                3: (8.0, 9.0, 3.0),
                4: (0.5, 0.5, 0.5),
            },
        )
        set_atom_items_for(view, {1: object(), 3: unrelated_label})
        # Mid-gesture drift for selected atoms and an unrelated cache-only atom.
        view.model.atoms[1].x, view.model.atoms[1].y = 20.0, 21.0
        view.model.atoms[2].x, view.model.atoms[2].y = 30.0, 31.0
        view.runtime_state.atom_coords_3d_state.atom_coords_3d[1] = (20.0, 21.0, 9.0)
        view.runtime_state.atom_coords_3d_state.atom_coords_3d[2] = (30.0, 31.0, 8.0)
        view.runtime_state.atom_coords_3d_state.atom_coords_3d[5] = (1.0, 1.0, 1.0)

        rotation = SimpleNamespace(
            start_positions={1: (1.0, 2.0), 2: (3.0, 4.0)},
            start_coords_3d={
                1: (1.0, 2.0, 1.0),
                3: (8.0, 9.0, 3.0),
                4: (0.5, 0.5, 0.5),
            },
            coord_atom_ids={1, 2, 3, 4, 5},
            atom_ids={1, 2},
            start_projection_center_3d=(0.0, 0.0, 0.0),
            start_projection_anchor_2d=(0.0, 0.0),
            projection_center_3d=(9.0, 9.0, 9.0),
            projection_anchor_2d=(8.0, 8.0),
        )
        authority = _RotationPreviewAuthority(
            controller=SimpleNamespace(
                canvas=view,
                refresh_atom_geometry=mock.Mock(),
                rotation=rotation,
            ),
            atom_ids=frozenset({1, 2}),
            affected_ring_items=(),
            scene_rect_snapshot=None,
        )
        authority.restore()

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (1.0, 2.0))
        self.assertEqual((view.model.atoms[2].x, view.model.atoms[2].y), (3.0, 4.0))
        # Unrelated atom 3 was cache-only: screen stays put.
        self.assertEqual((view.model.atoms[3].x, view.model.atoms[3].y), (8.0, 9.0))
        self.assertEqual(
            view.runtime_state.atom_coords_3d_state.atom_coords_3d,
            {1: (1.0, 2.0, 1.0), 3: (8.0, 9.0, 3.0), 4: (0.5, 0.5, 0.5)},
        )
        label_ids = [
            call.args[0]
            for call in view.services.atom_label_service.position_label.call_args_list
        ]
        self.assertNotIn(unrelated_label, label_ids)
        self.assertEqual(rotation.projection_center_3d, (0.0, 0.0, 0.0))
        self.assertEqual(rotation.projection_anchor_2d, (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
