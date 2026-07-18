from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor

from chemvas.domain.document import Atom
from chemvas.ui.atom_coords_access import pop_atom_coords_3d_for
from chemvas.ui.atom_label_access import (
    add_or_update_atom_label,
    atom_label_service,
    implicit_carbon_dot_brush_for,
)
from chemvas.ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    pop_atom_dot_for,
    pop_atom_item_for,
)
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_model_access import (
    add_atom_to_model_for,
    atom_for_id,
    bond_for_id,
    ensure_next_atom_id_after_for,
    remove_atom_direct_for,
    set_atom_annotation_for,
    set_atom_for_id,
)
from chemvas.ui.mark_item_access import remove_marks_for_atom_for
from chemvas.ui.scene_item_access import remove_item_from_canvas_scene

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class CanvasAtomMutationService:
    def __init__(
        self, canvas: CanvasView, *, hit_testing_service, graph_service
    ) -> None:
        self.canvas = canvas
        self.graph = graph_state_for(canvas)
        self.graph_service = graph_service
        self.hit_testing_service = hit_testing_service

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = add_atom_to_model_for(self.canvas, element, x, y)
        self.graph_service.ensure_atom_neighbors(atom_id)
        self.graph_service.ensure_atom_bond_ids(atom_id)
        if element.upper() == "C":
            atom_label_service(self.canvas).ensure_carbon_dot(atom_id)
        else:
            add_or_update_atom_label(
                self.canvas,
                atom_id,
                element,
                include_default_kwargs=False,
                clear_smiles=False,
                record=False,
            )
        self.hit_testing_service.mark_spatial_index_dirty()
        return atom_id

    def remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        self._clear_atom_graphics(atom_id)
        if remove_marks:
            remove_marks_for_atom_for(self.canvas, atom_id)
        remove_atom_direct_for(self.canvas, atom_id)
        pop_atom_coords_3d_for(self.canvas, atom_id)
        neighbors = self.graph.atom_neighbors.pop(atom_id, None)
        if neighbors:
            for neighbor in neighbors:
                neighbor_set = self.graph.atom_neighbors.get(neighbor)
                if neighbor_set is not None and atom_id in neighbor_set:
                    neighbor_set.remove(atom_id)
            self.graph.bump_version()
        bond_ids = self.graph.atom_bond_ids.pop(atom_id, None)
        if bond_ids:
            for bond_id in list(bond_ids):
                bond = bond_for_id(self.canvas, bond_id)
                if bond is None:
                    continue
                other_id = bond.b if bond.a == atom_id else bond.a
                other_set = self.graph.atom_bond_ids.get(other_id)
                if other_set is not None and bond_id in other_set:
                    other_set.remove(bond_id)
        self.hit_testing_service.mark_spatial_index_dirty()

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
        set_atom_for_id(self.canvas, atom_id, atom)
        set_atom_annotation_for(self.canvas, atom_id, state.get("annotation"))
        self.graph_service.ensure_atom_neighbors(atom_id)
        self.graph_service.ensure_atom_bond_ids(atom_id)
        ensure_next_atom_id_after_for(self.canvas, atom_id)
        self._clear_atom_graphics(atom_id)
        if atom.element.upper() == "C":
            if atom.explicit_label:
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    include_default_kwargs=False,
                    clear_smiles=False,
                    record=False,
                    allow_merge=False,
                    show_carbon=True,
                )
            else:
                atom_label_service(self.canvas).ensure_carbon_dot(atom_id)
        else:
            add_or_update_atom_label(
                self.canvas,
                atom_id,
                atom.element,
                include_default_kwargs=False,
                clear_smiles=False,
                record=False,
                allow_merge=False,
            )
        self.apply_atom_color(atom_id, atom.color)
        self.hit_testing_service.mark_spatial_index_dirty()

    def apply_atom_color(self, atom_id: int, color: str | QColor) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        color_value = color if isinstance(color, QColor) else QColor(color)
        if not color_value.isValid():
            return
        atom.color = color_value.name()
        label_item = atom_items_for(self.canvas).get(atom_id)
        if label_item is not None:
            label_item.setDefaultTextColor(color_value)
        dot_item = atom_dots_for(self.canvas).get(atom_id)
        if dot_item is not None:
            dot_item.setBrush(implicit_carbon_dot_brush_for(self.canvas))

    def _clear_atom_graphics(self, atom_id: int) -> None:
        label = pop_atom_item_for(self.canvas, atom_id)
        if label is not None:
            remove_item_from_canvas_scene(self.canvas, label)
        dot = pop_atom_dot_for(self.canvas, atom_id)
        if dot is not None:
            remove_item_from_canvas_scene(self.canvas, dot)


__all__ = ["CanvasAtomMutationService"]
