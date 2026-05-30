from __future__ import annotations

from typing import TYPE_CHECKING

from core.model import Bond

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class CanvasBondMutationService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        existing_id = self.canvas._bond_id_between(a, b)
        if existing_id is not None:
            return existing_id
        bond_id = self.canvas.model.add_bond(a, b, order)
        self.canvas._add_bond_neighbors(a, b)
        self.canvas._add_bond_index(bond_id, a, b)
        self.canvas._mark_spatial_index_dirty()
        return bond_id

    def restore_bond_from_state(self, bond_id: int, bond_state: dict) -> None:
        if not bond_state:
            return
        self._clear_bond_graphics(bond_id)
        existing_bond = self.canvas.model.bonds[bond_id] if bond_id < len(self.canvas.model.bonds) else None
        bond = Bond(
            a=bond_state.get("a", 0),
            b=bond_state.get("b", 0),
            order=bond_state.get("order", 1),
            style=bond_state.get("style", "single"),
            color=bond_state.get("color", "#000000"),
        )
        if existing_bond is not None and (existing_bond.a != bond.a or existing_bond.b != bond.b):
            self.canvas._remove_bond_index(bond_id, existing_bond.a, existing_bond.b)
            self.canvas._remove_bond_neighbors(existing_bond.a, existing_bond.b, skip_bond_id=bond_id)
        if bond_id < len(self.canvas.model.bonds):
            self.canvas.model.bonds[bond_id] = bond
        else:
            self.canvas.model.bonds.extend([None] * (bond_id - len(self.canvas.model.bonds)))
            self.canvas.model.bonds.append(bond)
        if existing_bond is None or (existing_bond.a != bond.a or existing_bond.b != bond.b):
            self.canvas._add_bond_neighbors(bond.a, bond.b)
            self.canvas._add_bond_index(bond_id, bond.a, bond.b)
        self.canvas._add_bond_graphics(bond_id)
        self.canvas._mark_spatial_index_dirty()

    def remove_bond_by_id(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return
        bond = self.canvas.model.bonds[bond_id]
        self._clear_bond_graphics(bond_id)
        if bond is not None:
            self.canvas._remove_bond_index(bond_id, bond.a, bond.b)
            self.canvas._remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
        self.canvas.model.bonds[bond_id] = None
        self.canvas._mark_spatial_index_dirty()

    def trim_bonds_to_length(self, length: int) -> None:
        if length < 0 or length >= len(self.canvas.model.bonds):
            return
        for bond_id in range(length, len(self.canvas.model.bonds)):
            bond = self.canvas.model.bonds[bond_id]
            if bond is not None:
                self.canvas._remove_bond_index(bond_id, bond.a, bond.b)
                self.canvas._remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
            self._clear_bond_graphics(bond_id)
        del self.canvas.model.bonds[length:]
        self.canvas._mark_spatial_index_dirty()

    def _clear_bond_graphics(self, bond_id: int) -> None:
        for item in self.canvas.bond_items.get(bond_id, []):
            self.canvas.scene().removeItem(item)
        self.canvas.bond_items.pop(bond_id, None)


def canvas_bond_mutation_service_for(canvas) -> CanvasBondMutationService:
    return canvas._canvas_bond_mutation_service


__all__ = ["CanvasBondMutationService", "canvas_bond_mutation_service_for"]
