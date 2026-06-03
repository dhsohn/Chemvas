from __future__ import annotations

from core.model import MoleculeModel

from ui.canvas_graph_state import graph_state_for
from ui.canvas_insert_state import insert_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_rotation_state import rotation_state_for
from ui.insert_mode_logic import clear_insert_session


class CanvasSceneResetService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.graph = graph_state_for(canvas)
        self.rotation = rotation_state_for(canvas)
        self.insert_state = insert_state_for(canvas)
        self.marks = mark_registry_for(canvas)

    def clear_scene(self) -> None:
        self.canvas.scene().clear()
        self.canvas.hover_items = []
        self.canvas.hover_atom_id = None
        self.canvas.hover_bond_id = None
        self.canvas.model = MoleculeModel()
        self.canvas._mark_spatial_index_dirty()
        self.canvas.atom_coords_3d = {}
        self.rotation.reset_all()
        self.canvas.atom_items = {}
        self.canvas.atom_dots = {}
        self.graph.reset()
        self.canvas.bond_items = {}
        self.canvas.ring_items = []
        self.canvas.note_items = []
        self.canvas.mark_items = []
        self.canvas.arrow_items = []
        self.canvas.ts_bracket_items = []
        self.canvas.orbital_items = []
        self.marks.clear()
        self.insert_state.smiles_preview_model = None
        self.canvas._clear_template_preview()
        self.canvas._clear_benzene_preview()
        self.canvas._clear_smiles_preview()
        self.canvas._apply_insert_session_state(clear_insert_session())


def canvas_scene_reset_service_for(canvas) -> CanvasSceneResetService:
    return canvas._canvas_scene_reset_service


__all__ = ["CanvasSceneResetService", "canvas_scene_reset_service_for"]
