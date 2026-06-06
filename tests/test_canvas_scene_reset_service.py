import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from core.model import MoleculeModel
from ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_bond_graphics_state import bond_items_for
from ui.canvas_graph_state import CanvasGraphState
from ui.canvas_hover_state import (
    hover_state_for,
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)
from ui.canvas_insert_state import CanvasInsertState
from ui.canvas_mark_registry import CanvasMarkRegistry
from ui.canvas_rotation_state import CanvasRotationState
from ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    ts_bracket_items_for,
)
from ui.canvas_scene_reset_service import CanvasSceneResetService
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
        clear_benzene_preview = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(dummy=True),
            services=SimpleNamespace(
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
                benzene_preview_service=SimpleNamespace(clear_preview=clear_benzene_preview),
                insert_controller=SimpleNamespace(
                    clear_template_preview=mock.Mock(),
                    clear_smiles_preview=mock.Mock(),
                    apply_insert_session_state=apply_insert_session_state,
                ),
            ),
            rotation_state=CanvasRotationState(
                projection_center_3d=(1.0, 1.0, 1.0),
                projection_anchor_2d=(2.0, 2.0),
                start_projection_center_3d=(3.0, 3.0, 3.0),
                start_projection_anchor_2d=(4.0, 4.0),
                axis_bond_id=7,
                axis_atoms=(1, 2),
                total_angle=1.2,
                mode="bond",
                free_angle_x=2.3,
                free_angle_y=4.5,
                start_positions={1: (0.0, 0.0)},
                start_coords_3d={1: (0.0, 0.0, 0.0)},
                coord_atom_ids={1},
            ),
            atom_items={1: object()},
            atom_dots={1: object()},
            graph_state=CanvasGraphState(
                atom_neighbors={1: {2}},
                atom_bond_ids={1: {0}},
                graph_version=9,
                selection_component_cache_signature="sig",
                selection_component_cache=[{1}],
            ),
            bond_items={0: [object()]},
            ring_items=[object()],
            note_items=[object()],
            mark_items=[object()],
            arrow_items=[object()],
            ts_bracket_items=[object()],
            orbital_items=[object()],
            mark_registry=CanvasMarkRegistry({1: [object()]}),
            insert_state=CanvasInsertState(smiles_preview_model=object()),
        )
        set_atom_coords_3d_for(canvas, {1: (1.0, 2.0, 3.0)})
        set_hover_items_for(canvas, [object()])
        set_hover_atom_id_for(canvas, 3)
        set_hover_bond_id_for(canvas, 4)

        CanvasSceneResetService(
            canvas,
            hit_testing_service=canvas.services.hit_testing_service,
        ).clear_scene()

        self.assertEqual(scene.clear_calls, 1)
        self.assertEqual(hover_state_for(canvas).items, [])
        self.assertIsNone(hover_state_for(canvas).atom_id)
        self.assertIsNone(hover_state_for(canvas).bond_id)
        self.assertIsInstance(canvas.model, MoleculeModel)
        canvas.services.hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()
        self.assertEqual(atom_coords_3d_for(canvas), {})
        self.assertIsNone(canvas.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.rotation_state.projection_anchor_2d)
        self.assertIsNone(canvas.rotation_state.start_projection_center_3d)
        self.assertIsNone(canvas.rotation_state.start_projection_anchor_2d)
        self.assertIsNone(canvas.rotation_state.axis_bond_id)
        self.assertIsNone(canvas.rotation_state.axis_atoms)
        self.assertEqual(canvas.rotation_state.total_angle, 0.0)
        self.assertIsNone(canvas.rotation_state.mode)
        self.assertEqual(canvas.rotation_state.free_angle_x, 0.0)
        self.assertEqual(canvas.rotation_state.free_angle_y, 0.0)
        self.assertEqual(canvas.rotation_state.start_positions, {})
        self.assertEqual(canvas.rotation_state.start_coords_3d, {})
        self.assertEqual(canvas.rotation_state.coord_atom_ids, set())
        self.assertEqual(atom_items_for(canvas), {})
        self.assertEqual(atom_dots_for(canvas), {})
        self.assertEqual(canvas.graph_state.atom_neighbors, {})
        self.assertEqual(canvas.graph_state.atom_bond_ids, {})
        self.assertEqual(canvas.graph_state.graph_version, 0)
        self.assertIsNone(canvas.graph_state.selection_component_cache_signature)
        self.assertEqual(canvas.graph_state.selection_component_cache, [])
        self.assertEqual(bond_items_for(canvas), {})
        self.assertEqual(ring_items_for(canvas), [])
        self.assertEqual(note_items_for(canvas), [])
        self.assertEqual(mark_items_for(canvas), [])
        self.assertEqual(arrow_items_for(canvas), [])
        self.assertEqual(ts_bracket_items_for(canvas), [])
        self.assertEqual(orbital_items_for(canvas), [])
        self.assertEqual(canvas.mark_registry.by_atom, {})
        self.assertIsNone(canvas.insert_state.smiles_preview_model)
        canvas.services.insert_controller.clear_template_preview.assert_called_once_with()
        clear_benzene_preview.assert_called_once_with()
        canvas.services.insert_controller.clear_smiles_preview.assert_called_once_with()
        apply_insert_session_state.assert_called_once_with(clear_insert_session())
