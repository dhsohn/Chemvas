from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor

from core.model import Atom

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class CanvasAtomMutationService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.canvas.model.add_atom(element, x, y)
        self.canvas._ensure_atom_neighbors(atom_id)
        self.canvas._ensure_atom_bond_ids(atom_id)
        if element.upper() == "C":
            self.canvas._ensure_carbon_dot(atom_id)
        else:
            self.canvas._atom_label_service.add_or_update_atom_label(
                atom_id,
                element,
                clear_smiles=False,
                record=False,
            )
        self.canvas._mark_spatial_index_dirty()
        return atom_id

    def remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        self._clear_atom_graphics(atom_id)
        if remove_marks:
            self.canvas._remove_marks_for_atom(atom_id)
        self.canvas.model.atoms.pop(atom_id, None)
        self.canvas.atom_coords_3d.pop(atom_id, None)
        neighbors = self.canvas._atom_neighbors.pop(atom_id, None)
        if neighbors:
            for neighbor in neighbors:
                neighbor_set = self.canvas._atom_neighbors.get(neighbor)
                if neighbor_set is not None and atom_id in neighbor_set:
                    neighbor_set.remove(atom_id)
            self.canvas._graph_version += 1
            self.canvas._selection_component_cache_signature = None
        bond_ids = self.canvas._atom_bond_ids.pop(atom_id, None)
        if bond_ids:
            for bond_id in list(bond_ids):
                bond = self.canvas.model.bonds[bond_id] if 0 <= bond_id < len(self.canvas.model.bonds) else None
                if bond is None:
                    continue
                other_id = bond.b if bond.a == atom_id else bond.a
                other_set = self.canvas._atom_bond_ids.get(other_id)
                if other_set is not None and bond_id in other_set:
                    other_set.remove(bond_id)
        self.canvas._mark_spatial_index_dirty()

    def restore_atom_from_state(self, atom_id: int, state: dict) -> None:
        if not state:
            return
        atom = Atom(
            element=state.get("element", "C"),
            x=state.get("x", 0.0),
            y=state.get("y", 0.0),
            color=state.get("color", "#000000"),
            explicit_label=bool(state.get("explicit_label", False)),
        )
        self.canvas.model.atoms[atom_id] = atom
        self.canvas._ensure_atom_neighbors(atom_id)
        self.canvas._ensure_atom_bond_ids(atom_id)
        if atom_id >= self.canvas.model.next_atom_id:
            self.canvas.model.next_atom_id = atom_id + 1
        self._clear_atom_graphics(atom_id)
        if atom.element.upper() == "C":
            if atom.explicit_label:
                self.canvas._atom_label_service.add_or_update_atom_label(
                    atom_id,
                    atom.element,
                    clear_smiles=False,
                    record=False,
                    allow_merge=False,
                    show_carbon=True,
                )
            else:
                self.canvas._ensure_carbon_dot(atom_id)
        else:
            self.canvas._atom_label_service.add_or_update_atom_label(
                atom_id,
                atom.element,
                clear_smiles=False,
                record=False,
                allow_merge=False,
            )
        self.apply_atom_color(atom_id, atom.color)
        self.canvas._mark_spatial_index_dirty()

    def apply_atom_color(self, atom_id: int, color: str | QColor) -> None:
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return
        color_value = color if isinstance(color, QColor) else QColor(color)
        if not color_value.isValid():
            return
        atom.color = color_value.name()
        label_item = self.canvas.atom_items.get(atom_id)
        if label_item is not None:
            label_item.setDefaultTextColor(color_value)
        dot_item = self.canvas.atom_dots.get(atom_id)
        if dot_item is not None:
            dot_item.setBrush(self.canvas._implicit_carbon_dot_brush())

    def _clear_atom_graphics(self, atom_id: int) -> None:
        label = self.canvas.atom_items.pop(atom_id, None)
        if label is not None:
            self.canvas.scene().removeItem(label)
        dot = self.canvas.atom_dots.pop(atom_id, None)
        if dot is not None:
            self.canvas.scene().removeItem(dot)


def canvas_atom_mutation_service_for(canvas) -> CanvasAtomMutationService:
    service = getattr(canvas, "_canvas_atom_mutation_service", None)
    if isinstance(service, CanvasAtomMutationService) and service.canvas is canvas:
        return service
    if service is not None and all(
        hasattr(service, name)
        for name in (
            "add_atom",
            "remove_atom_only",
            "restore_atom_from_state",
            "apply_atom_color",
        )
    ):
        return service
    return CanvasAtomMutationService(canvas)


__all__ = ["CanvasAtomMutationService", "canvas_atom_mutation_service_for"]
