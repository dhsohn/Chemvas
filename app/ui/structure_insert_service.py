from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from core.model import MoleculeModel

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class StructureInsertService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def insert_structure_model(
        self,
        model: MoleculeModel,
        *,
        center: QPointF | None = None,
        title: str | None = None,
    ) -> tuple[set[int], set[int]]:
        if not model.atoms:
            return set(), set()
        before_smiles_input = self.canvas.last_smiles_input
        before_next_atom_id = self.canvas.model.next_atom_id
        before_bond_count = len(self.canvas.model.bonds)

        if center is None:
            center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        left, top, right, bottom = model.bounds()
        model_center = QPointF((left + right) * 0.5, (top + bottom) * 0.5)
        dx = center.x() - model_center.x()
        dy = center.y() - model_center.y()

        atom_id_map: dict[int, int] = {}
        inserted_atom_ids: set[int] = set()
        inserted_bond_ids: set[int] = set()
        for old_id in sorted(model.atoms):
            atom = model.atoms[old_id]
            new_id = self.canvas.add_atom(atom.element, atom.x + dx, atom.y + dy)
            self.canvas.model.atoms[new_id].color = atom.color
            self.canvas.model.atoms[new_id].explicit_label = atom.explicit_label
            atom_id_map[old_id] = new_id
            inserted_atom_ids.add(new_id)

        bonds_start = len(self.canvas.model.bonds)
        for bond in model.bonds:
            if bond is None:
                continue
            a_id = atom_id_map.get(bond.a)
            b_id = atom_id_map.get(bond.b)
            if a_id is None or b_id is None:
                continue
            new_bond_id = self.canvas.add_bond(a_id, b_id, bond.order)
            created_bond = self.canvas.model.bonds[new_bond_id]
            created_bond.style = bond.style
            created_bond.color = bond.color
        for bond_id in range(bonds_start, len(self.canvas.model.bonds)):
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            self.canvas._add_bond_graphics(bond_id)
            inserted_bond_ids.add(bond_id)

        for new_id in inserted_atom_ids:
            atom = self.canvas.model.atoms[new_id]
            if atom.element == "C" and not atom.explicit_label:
                self.canvas._ensure_carbon_dot(new_id)
            else:
                self.canvas.add_or_update_atom_label(new_id, atom.element, clear_smiles=False, record=False)

        added_scene_items = []
        if title:
            inserted_left = min(self.canvas.model.atoms[atom_id].x for atom_id in inserted_atom_ids)
            inserted_top = min(self.canvas.model.atoms[atom_id].y for atom_id in inserted_atom_ids)
            note_pos = QPointF(
                inserted_left,
                inserted_top - self.canvas.renderer.style.bond_length_px * 1.4,
            )
            added_scene_items.append(self.canvas.add_text_note(note_pos, title))

        self.canvas._record_additions(
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
            added_scene_items=added_scene_items,
        )
        self.canvas._restore_selection_from_ids(inserted_atom_ids, inserted_bond_ids)
        return inserted_atom_ids, inserted_bond_ids


__all__ = ["StructureInsertService"]
