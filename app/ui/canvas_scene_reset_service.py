from __future__ import annotations

from core.model import MoleculeModel

from ui.atom_coords_access import clear_atom_coords_3d_for
from ui.benzene_preview_access import clear_benzene_preview_for
from ui.canvas_atom_graphics_state import clear_atom_graphics_for
from ui.canvas_bond_graphics_state import clear_bond_graphics_for
from ui.canvas_graph_state import graph_state_for
from ui.canvas_group_state import clear_groups_for
from ui.canvas_hover_state import (
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)
from ui.canvas_insert_state import insert_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import set_model_for
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_scene_items_state import clear_scene_item_collections_for
from ui.insert_mode_logic import clear_insert_session
from ui.insert_session_access import (
    apply_insert_session_state_for,
    clear_smiles_preview_for,
    clear_template_preview_for,
)
from ui.scene_item_access import clear_canvas_scene


class CanvasSceneResetService:
    def __init__(self, canvas, *, hit_testing_service) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.graph = graph_state_for(canvas)
        self.rotation = rotation_state_for(canvas)
        self.insert_state = insert_state_for(canvas)
        self.marks = mark_registry_for(canvas)

    def clear_scene(self) -> None:
        clear_canvas_scene(self.canvas)
        set_hover_items_for(self.canvas, [])
        set_hover_atom_id_for(self.canvas, None)
        set_hover_bond_id_for(self.canvas, None)
        set_model_for(self.canvas, MoleculeModel())
        self.hit_testing_service.mark_spatial_index_dirty()
        clear_atom_coords_3d_for(self.canvas)
        self.rotation.reset_all()
        clear_atom_graphics_for(self.canvas)
        self.graph.reset()
        clear_bond_graphics_for(self.canvas)
        clear_scene_item_collections_for(self.canvas)
        clear_groups_for(self.canvas)
        self.marks.clear()
        self.insert_state.smiles_preview_model = None
        clear_template_preview_for(self.canvas)
        clear_benzene_preview_for(self.canvas)
        clear_smiles_preview_for(self.canvas)
        apply_insert_session_state_for(self.canvas, clear_insert_session())


__all__ = ["CanvasSceneResetService"]
