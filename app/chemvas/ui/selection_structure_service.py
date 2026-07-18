from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsItem

from chemvas.features.selection import StructureHit
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id, bonds_for
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.selection_scene_access import clear_scene_selection_for
from chemvas.ui.selection_service_access import clear_note_selection_for
from chemvas.ui.selection_structure_targets import (
    STRUCTURE_OVERLAY_KINDS,
    structure_selection_targets_for_item,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(frozen=True, slots=True)
class StructureSelectionResult:
    selected: bool
    update_outline: bool = False


class SelectionStructureService:
    def __init__(self, canvas: CanvasView, *, graph_service) -> None:
        self.canvas = canvas
        self.graph_service = graph_service

    def atom_item_for_id(self, atom_id: int):
        return visible_atom_item_for(self.canvas, atom_id)

    def structure_hit_from_item(
        self, item
    ) -> tuple[StructureHit | None, tuple[int, int] | None, list[int] | None]:
        if item is None:
            return None, None, None
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                return StructureHit(kind="atom", id=atom_id), None, None
            return None, None, None
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                bond = bond_for_id(self.canvas, bond_id)
                if bond is not None:
                    return StructureHit(kind="bond", id=bond_id), (bond.a, bond.b), None
            return None, None, None
        if kind == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                return StructureHit(kind="ring"), None, ring_atom_ids
            return StructureHit(kind="ring"), None, None
        return StructureHit(kind="other"), None, None

    def structure_item_for_hit(self, hit: StructureHit):
        if hit.kind == "atom" and isinstance(hit.id, int):
            return self.atom_item_for_id(hit.id)
        if hit.kind == "bond" and isinstance(hit.id, int):
            bond_items = bond_items_for_id(self.canvas, hit.id)
            if bond_items:
                return bond_items[0]
        return None

    def selection_targets_for_item(self, item) -> list[QGraphicsItem]:
        return structure_selection_targets_for_item(
            self.canvas,
            item,
            atom_item_for_id=self.atom_item_for_id,
        )

    def _connected_atom_ids_for_item(self, item) -> set[int]:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if (
                isinstance(atom_id, int)
                and atom_for_id(self.canvas, atom_id) is not None
            ):
                return self.graph_service.expand_connected_atoms({atom_id})
            return set()
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                bond = bond_for_id(self.canvas, bond_id)
                if bond is not None:
                    return self.graph_service.expand_connected_atoms({bond.a, bond.b})
            return set()
        if kind == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                return self.graph_service.expand_connected_atoms(
                    {
                        atom_id
                        for atom_id in ring_atom_ids
                        if atom_for_id(self.canvas, atom_id) is not None
                    }
                )
        return set()

    def select_structure_for_item(self, item) -> StructureSelectionResult:
        if item is None:
            return StructureSelectionResult(False)
        kind = item.data(0)
        if kind in STRUCTURE_OVERLAY_KINDS:
            clear_scene_selection_for(self.canvas)
            clear_note_selection_for(self.canvas)
            item.setSelected(True)
            return StructureSelectionResult(True)
        atom_ids = self._connected_atom_ids_for_item(item)
        if not atom_ids:
            return StructureSelectionResult(False)
        clear_scene_selection_for(self.canvas)
        clear_note_selection_for(self.canvas)
        for atom_id in atom_ids:
            atom_item = self.atom_item_for_id(atom_id)
            if atom_item is not None:
                atom_item.setSelected(True)
        for bond_id, bond in enumerate(bonds_for(self.canvas)):
            if bond is None:
                continue
            if bond.a not in atom_ids or bond.b not in atom_ids:
                continue
            for bond_item in bond_items_for_id(self.canvas, bond_id):
                bond_item.setSelected(True)
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list) and all(
                atom_id in atom_ids for atom_id in ring_atom_ids
            ):
                ring_item.setSelected(True)
        return StructureSelectionResult(True, update_outline=True)


__all__ = [
    "STRUCTURE_OVERLAY_KINDS",
    "SelectionStructureService",
    "StructureSelectionResult",
]
