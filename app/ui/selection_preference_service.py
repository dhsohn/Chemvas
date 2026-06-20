from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_atom_graphics_state import visible_atom_item_for
from ui.canvas_model_access import atom_for_id
from ui.pick_radius_access import atom_pick_radius_for, bond_pick_radius_for
from ui.renderer_style_access import bond_length_px_for
from ui.selection_hit_logic import (
    AtomHitCandidate,
    BondHitCandidate,
    StructureHit,
    choose_preferred_structure_hit,
    nearest_ring_atom_id,
)

if TYPE_CHECKING:
    from ui.canvas_hit_testing_service import CanvasHitTestingService
    from ui.canvas_view import CanvasView
    from ui.selection_structure_service import SelectionStructureService


class SelectionPreferenceService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        hit_testing_service: CanvasHitTestingService,
        structure_service: SelectionStructureService,
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.structure_service = structure_service

    def item_at_scene_pos(self, pos: QPointF):
        return self.hit_testing_service.item_at_scene_pos(pos)

    def nearest_atom_hit(self, pos: QPointF) -> tuple[int, float] | None:
        return self.hit_testing_service.nearest_atom_hit(pos)

    def nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        return self.hit_testing_service.nearest_bond_hit(pos)

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF) -> StructureHit | None:
        item = self.item_at_scene_pos(pos)
        item_hit, _, _ = self.structure_service.structure_hit_from_item(item)
        if item_hit is not None and item_hit.kind == "atom":
            return item_hit
        atom_hit = self.nearest_atom_hit(pos)
        bond_hit = self.nearest_bond_hit(pos)
        preferred_hit = choose_preferred_structure_hit(
            AtomHitCandidate(
                atom_id=atom_hit[0],
                distance=atom_hit[1],
            )
            if atom_hit is not None
            else None,
            BondHitCandidate(bond_id=bond_hit[0], distance=bond_hit[1]) if bond_hit is not None else None,
            atom_pick_radius=atom_pick_radius_for(self.canvas),
            bond_pick_radius=bond_pick_radius_for(self.canvas),
        )
        if preferred_hit is not None:
            preferred_item = self.structure_service.structure_item_for_hit(preferred_hit)
            if preferred_item is not None:
                return preferred_hit
        if item is not None and item.data(0) == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                nearest_atom_id = nearest_ring_atom_id(
                    [
                        (atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y()))
                        for atom_id in ring_atom_ids
                        for atom in [atom_for_id(self.canvas, atom_id)]
                        if atom is not None
                    ],
                    max_distance=bond_length_px_for(self.canvas) * 0.4,
                )
                if nearest_atom_id is not None:
                    ring_atom_item = visible_atom_item_for(self.canvas, nearest_atom_id)
                    if ring_atom_item is not None:
                        return StructureHit(kind="atom", id=nearest_atom_id)
            return StructureHit(kind="ring")
        fallback_hit, _, _ = self.structure_service.structure_hit_from_item(item)
        return fallback_hit

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        hit = self.preferred_structure_hit_at_scene_pos(pos)
        if hit is None:
            return None
        if hit.kind in {"atom", "bond"}:
            return self.structure_service.structure_item_for_hit(hit)
        return self.item_at_scene_pos(pos)


__all__ = ["SelectionPreferenceService"]
