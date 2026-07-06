from __future__ import annotations

from typing import TYPE_CHECKING

from core.model import Bond

from ui.bond_graphics_access import add_bond_graphics_for
from ui.canvas_bond_graphics_state import bond_items_for_id, pop_bond_items_for
from ui.canvas_model_access import (
    add_bond_to_model_for,
    bond_count_for,
    bond_for_id,
    bond_ids_from,
    clear_bond_for_id,
    has_bond_slot_for,
    set_bond_for_id,
    trim_bonds_direct_for,
)
from ui.scene_item_access import remove_items_from_canvas_scene

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class CanvasBondMutationService:
    def __init__(self, canvas: CanvasView, *, hit_testing_service, graph_service) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.graph_service = graph_service

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        graph_service = self.graph_service
        # This is the one write site where a stale index entry would let a
        # duplicate bond into the model and poison every later save, so use
        # the graph service's self-repairing lookup instead of the fast path.
        existing_id = graph_service.bond_id_between_with_repair(a, b)
        if existing_id is not None:
            return existing_id
        bond_id = add_bond_to_model_for(self.canvas, a, b, order)
        graph_service.add_bond_neighbors(a, b)
        graph_service.add_bond_index(bond_id, a, b)
        self.hit_testing_service.mark_spatial_index_dirty()
        return bond_id

    def restore_bond_from_state(self, bond_id: int, bond_state: dict) -> None:
        if not bond_state:
            return
        self._clear_bond_graphics(bond_id)
        graph_service = self.graph_service
        existing_bond = bond_for_id(self.canvas, bond_id)
        bond = Bond(
            a=bond_state.get("a", 0),
            b=bond_state.get("b", 0),
            order=bond_state.get("order", 1),
            style=bond_state.get("style", "single"),
            color=bond_state.get("color", "#000000"),
        )
        if existing_bond is not None and (existing_bond.a != bond.a or existing_bond.b != bond.b):
            graph_service.remove_bond_index(bond_id, existing_bond.a, existing_bond.b)
            graph_service.remove_bond_neighbors(existing_bond.a, existing_bond.b, skip_bond_id=bond_id)
        set_bond_for_id(self.canvas, bond_id, bond)
        if existing_bond is None or (existing_bond.a != bond.a or existing_bond.b != bond.b):
            graph_service.add_bond_neighbors(bond.a, bond.b)
            graph_service.add_bond_index(bond_id, bond.a, bond.b)
        add_bond_graphics_for(self.canvas, bond_id)
        self.hit_testing_service.mark_spatial_index_dirty()

    def remove_bond_by_id(self, bond_id: int) -> None:
        if not has_bond_slot_for(self.canvas, bond_id):
            return
        bond = bond_for_id(self.canvas, bond_id)
        self._clear_bond_graphics(bond_id)
        if bond is not None:
            graph_service = self.graph_service
            graph_service.remove_bond_index(bond_id, bond.a, bond.b)
            graph_service.remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
        clear_bond_for_id(self.canvas, bond_id)
        self.hit_testing_service.mark_spatial_index_dirty()

    def trim_bonds_to_length(self, length: int) -> None:
        if length < 0 or length >= bond_count_for(self.canvas):
            return
        graph_service = self.graph_service
        trimmed_bonds = [
            (bond_id, bond_for_id(self.canvas, bond_id))
            for bond_id in bond_ids_from(self.canvas, length)
        ]
        trim_bonds_direct_for(self.canvas, length)
        for bond_id, bond in trimmed_bonds:
            if bond is not None:
                graph_service.remove_bond_index(bond_id, bond.a, bond.b)
                graph_service.remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
            self._clear_bond_graphics(bond_id)
        self.hit_testing_service.mark_spatial_index_dirty()

    def _clear_bond_graphics(self, bond_id: int) -> None:
        remove_items_from_canvas_scene(self.canvas, bond_items_for_id(self.canvas, bond_id))
        pop_bond_items_for(self.canvas, bond_id)


__all__ = ["CanvasBondMutationService"]
