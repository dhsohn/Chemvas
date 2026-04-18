import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import MoleculeModel
from ui.canvas_scene_reset_service import CanvasSceneResetService, canvas_scene_reset_service_for
from ui.insert_mode_logic import clear_insert_session


class _FakeScene:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear(self) -> None:
        self.clear_calls += 1


class CanvasSceneResetServiceTest(unittest.TestCase):
    def test_clear_scene_resets_canvas_state_and_clears_previews(self) -> None:
        scene = _FakeScene()
        apply_insert_session_state = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            hover_items=[object()],
            hover_atom_id=3,
            hover_bond_id=4,
            model=SimpleNamespace(dummy=True),
            _mark_spatial_index_dirty=mock.Mock(),
            atom_coords_3d={1: (1.0, 2.0, 3.0)},
            _projection_center_3d=(1.0, 1.0, 1.0),
            _projection_anchor_2d=(2.0, 2.0),
            _rotation_start_projection_center_3d=(3.0, 3.0, 3.0),
            _rotation_start_projection_anchor_2d=(4.0, 4.0),
            _rotation_axis_bond_id=7,
            _rotation_axis_atoms=(1, 2),
            _rotation_total_angle=1.2,
            _rotation_mode="bond",
            _rotation_free_angle_x=2.3,
            _rotation_free_angle_y=4.5,
            _rotation_start_positions={1: (0.0, 0.0)},
            _rotation_start_coords_3d={1: (0.0, 0.0, 0.0)},
            _rotation_coord_atom_ids={1},
            atom_items={1: object()},
            atom_dots={1: object()},
            _atom_neighbors={1: {2}},
            _atom_bond_ids={1: {0}},
            _graph_version=9,
            _selection_component_cache_signature="sig",
            _selection_component_cache=[{1}],
            bond_items={0: [object()]},
            ring_items=[object()],
            note_items=[object()],
            mark_items=[object()],
            arrow_items=[object()],
            ts_bracket_items=[object()],
            orbital_items=[object()],
            _marks_by_atom={1: [object()]},
            _smiles_preview_model=object(),
            _clear_template_preview=mock.Mock(),
            _clear_benzene_preview=mock.Mock(),
            _clear_smiles_preview=mock.Mock(),
            _apply_insert_session_state=apply_insert_session_state,
        )

        CanvasSceneResetService(canvas).clear_scene()

        self.assertEqual(scene.clear_calls, 1)
        self.assertEqual(canvas.hover_items, [])
        self.assertIsNone(canvas.hover_atom_id)
        self.assertIsNone(canvas.hover_bond_id)
        self.assertIsInstance(canvas.model, MoleculeModel)
        canvas._mark_spatial_index_dirty.assert_called_once_with()
        self.assertEqual(canvas.atom_coords_3d, {})
        self.assertIsNone(canvas._projection_center_3d)
        self.assertIsNone(canvas._projection_anchor_2d)
        self.assertIsNone(canvas._rotation_start_projection_center_3d)
        self.assertIsNone(canvas._rotation_start_projection_anchor_2d)
        self.assertIsNone(canvas._rotation_axis_bond_id)
        self.assertIsNone(canvas._rotation_axis_atoms)
        self.assertEqual(canvas._rotation_total_angle, 0.0)
        self.assertIsNone(canvas._rotation_mode)
        self.assertEqual(canvas._rotation_free_angle_x, 0.0)
        self.assertEqual(canvas._rotation_free_angle_y, 0.0)
        self.assertEqual(canvas._rotation_start_positions, {})
        self.assertEqual(canvas._rotation_start_coords_3d, {})
        self.assertEqual(canvas._rotation_coord_atom_ids, set())
        self.assertEqual(canvas.atom_items, {})
        self.assertEqual(canvas.atom_dots, {})
        self.assertEqual(canvas._atom_neighbors, {})
        self.assertEqual(canvas._atom_bond_ids, {})
        self.assertEqual(canvas._graph_version, 0)
        self.assertIsNone(canvas._selection_component_cache_signature)
        self.assertEqual(canvas._selection_component_cache, [])
        self.assertEqual(canvas.bond_items, {})
        self.assertEqual(canvas.ring_items, [])
        self.assertEqual(canvas.note_items, [])
        self.assertEqual(canvas.mark_items, [])
        self.assertEqual(canvas.arrow_items, [])
        self.assertEqual(canvas.ts_bracket_items, [])
        self.assertEqual(canvas.orbital_items, [])
        self.assertEqual(canvas._marks_by_atom, {})
        self.assertIsNone(canvas._smiles_preview_model)
        canvas._clear_template_preview.assert_called_once_with()
        canvas._clear_benzene_preview.assert_called_once_with()
        canvas._clear_smiles_preview.assert_called_once_with()
        apply_insert_session_state.assert_called_once_with(clear_insert_session())

    def test_canvas_scene_reset_service_for_reuses_real_duck_typed_and_fallback_services(self) -> None:
        canvas = SimpleNamespace()
        real_service = CanvasSceneResetService(canvas)
        canvas._canvas_scene_reset_service = real_service

        self.assertIs(canvas_scene_reset_service_for(canvas), real_service)

        duck_service = SimpleNamespace(clear_scene=mock.Mock())
        canvas._canvas_scene_reset_service = duck_service

        self.assertIs(canvas_scene_reset_service_for(canvas), duck_service)

        canvas._canvas_scene_reset_service = object()

        self.assertIsInstance(canvas_scene_reset_service_for(canvas), CanvasSceneResetService)
