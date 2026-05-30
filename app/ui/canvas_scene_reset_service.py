from __future__ import annotations

from core.model import MoleculeModel
from ui.insert_mode_logic import clear_insert_session


class CanvasSceneResetService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def clear_scene(self) -> None:
        self.canvas.scene().clear()
        self.canvas.hover_items = []
        self.canvas.hover_atom_id = None
        self.canvas.hover_bond_id = None
        self.canvas.model = MoleculeModel()
        self.canvas._mark_spatial_index_dirty()
        self.canvas.atom_coords_3d = {}
        self.canvas._projection_center_3d = None
        self.canvas._projection_anchor_2d = None
        self.canvas._rotation_start_projection_center_3d = None
        self.canvas._rotation_start_projection_anchor_2d = None
        self.canvas._rotation_axis_bond_id = None
        self.canvas._rotation_axis_atoms = None
        self.canvas._rotation_total_angle = 0.0
        self.canvas._rotation_mode = None
        self.canvas._rotation_free_angle_x = 0.0
        self.canvas._rotation_free_angle_y = 0.0
        self.canvas._rotation_start_positions = {}
        self.canvas._rotation_start_coords_3d = {}
        self.canvas._rotation_coord_atom_ids = set()
        self.canvas.atom_items = {}
        self.canvas.atom_dots = {}
        self.canvas._atom_neighbors = {}
        self.canvas._atom_bond_ids = {}
        self.canvas._graph_version = 0
        self.canvas._selection_component_cache_signature = None
        self.canvas._selection_component_cache = []
        self.canvas.bond_items = {}
        self.canvas.ring_items = []
        self.canvas.note_items = []
        self.canvas.mark_items = []
        self.canvas.arrow_items = []
        self.canvas.ts_bracket_items = []
        self.canvas.orbital_items = []
        self.canvas._marks_by_atom = {}
        self.canvas._smiles_preview_model = None
        self.canvas._clear_template_preview()
        self.canvas._clear_benzene_preview()
        self.canvas._clear_smiles_preview()
        self.canvas._apply_insert_session_state(clear_insert_session())


def canvas_scene_reset_service_for(canvas) -> CanvasSceneResetService:
    return canvas._canvas_scene_reset_service


__all__ = ["CanvasSceneResetService", "canvas_scene_reset_service_for"]
