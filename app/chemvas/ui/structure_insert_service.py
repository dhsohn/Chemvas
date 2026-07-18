from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
)
from chemvas.ui.input_view_access import viewport_center_scene_pos_for
from chemvas.ui.insert_commit_rollback import (
    capture_smiles_input_restore_authority,
    rollback_insert_mutation,
)
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_item_access import remove_scene_item
from chemvas.ui.structure_insert_access import (
    add_insert_atom_for,
    add_insert_bond_for,
    add_insert_bond_graphics_for,
    add_or_update_insert_atom_label_for,
    ensure_insert_carbon_dot_for,
    insert_atom_for_id,
    insert_bond_count_for,
    insert_bond_for_id,
    insert_next_atom_id_for,
    new_insert_bond_ids_from,
    record_insert_additions_for,
    restore_insert_selection_from_ids_for,
    set_inserted_atom_annotation_for,
    set_inserted_atom_metadata_for,
    set_inserted_bond_metadata_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


def _add_structure_insert_rollback_note(
    original_error: BaseException,
    message: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(message)
    except BaseException:
        return


class StructureInsertService:
    def __init__(self, canvas: CanvasView, *, note_controller=None) -> None:
        self.canvas = canvas
        self.note_controller = note_controller

    def _create_text_note(self, pos: QPointF, text: str):
        note_controller = self.note_controller
        if note_controller is not None:
            return note_controller.create_text_note(pos, text)
        return None

    def insert_structure_model(
        self,
        model: MoleculeModel,
        *,
        center: QPointF | None = None,
        title: str | None = None,
    ) -> tuple[set[int], set[int]]:
        if not model.atoms:
            return set(), set()
        before_smiles_input = last_smiles_input_for(self.canvas)
        smiles_authority = capture_smiles_input_restore_authority(self.canvas)
        before_next_atom_id = insert_next_atom_id_for(self.canvas)
        before_bond_count = insert_bond_count_for(self.canvas)
        try:
            history_service = canvas_services_for(self.canvas).history_service
        except AttributeError:
            history_service = None
        if center is None:
            center = viewport_center_scene_pos_for(self.canvas)
        left, top, right, bottom = model.bounds()
        model_center = QPointF((left + right) * 0.5, (top + bottom) * 0.5)
        dx = center.x() - model_center.x()
        dy = center.y() - model_center.y()

        atom_id_map: dict[int, int] = {}
        inserted_atom_ids: set[int] = set()
        inserted_bond_ids: set[int] = set()
        added_scene_items = []
        exact_transaction = capture_history_transaction_for_history(
            self.canvas,
            history_service=history_service,
        )
        try:
            source_atom_annotations = getattr(model, "atom_annotations", {})
            if not hasattr(source_atom_annotations, "get"):
                source_atom_annotations = {}
            for old_id in sorted(model.atoms):
                atom = model.atoms[old_id]
                new_id = add_insert_atom_for(
                    self.canvas, atom.element, atom.x + dx, atom.y + dy
                )
                set_inserted_atom_metadata_for(
                    self.canvas,
                    new_id,
                    color=atom.color,
                    explicit_label=atom.explicit_label,
                )
                set_inserted_atom_annotation_for(
                    self.canvas,
                    new_id,
                    source_atom_annotations.get(old_id),
                )
                atom_id_map[old_id] = new_id
                inserted_atom_ids.add(new_id)

            bonds_start = insert_bond_count_for(self.canvas)
            for bond in model.bonds:
                if bond is None:
                    continue
                a_id = atom_id_map.get(bond.a)
                b_id = atom_id_map.get(bond.b)
                if a_id is None or b_id is None:
                    continue
                new_bond_id = add_insert_bond_for(self.canvas, a_id, b_id, bond.order)
                set_inserted_bond_metadata_for(
                    self.canvas,
                    new_bond_id,
                    style=bond.style,
                    color=bond.color,
                )
            for bond_id in new_insert_bond_ids_from(self.canvas, bonds_start):
                bond = insert_bond_for_id(self.canvas, bond_id)
                if bond is None:
                    continue
                add_insert_bond_graphics_for(self.canvas, bond_id)
                inserted_bond_ids.add(bond_id)

            for new_id in inserted_atom_ids:
                atom = insert_atom_for_id(self.canvas, new_id)
                if atom is None:
                    continue
                if atom.element == "C" and not atom.explicit_label:
                    ensure_insert_carbon_dot_for(self.canvas, new_id)
                else:
                    add_or_update_insert_atom_label_for(
                        self.canvas,
                        new_id,
                        atom.element,
                        clear_smiles=False,
                        record=False,
                    )

            if title:
                inserted_atoms = [
                    atom
                    for atom_id in inserted_atom_ids
                    for atom in [insert_atom_for_id(self.canvas, atom_id)]
                    if atom is not None
                ]
                if inserted_atoms:
                    inserted_left = min(atom.x for atom in inserted_atoms)
                    inserted_top = min(atom.y for atom in inserted_atoms)
                    note_pos = QPointF(
                        inserted_left,
                        inserted_top - bond_length_px_for(self.canvas) * 1.4,
                    )
                    note_item = self._create_text_note(note_pos, title)
                    if note_item is not None:
                        added_scene_items.append(note_item)

            record_insert_additions_for(
                self.canvas,
                before_next_atom_id=before_next_atom_id,
                before_bond_count=before_bond_count,
                before_smiles_input=before_smiles_input,
                added_scene_items=added_scene_items,
            )
            restore_insert_selection_from_ids_for(
                self.canvas,
                inserted_atom_ids,
                inserted_bond_ids,
            )
            release_history_transaction_for_history(
                self.canvas,
                exact_transaction,
            )
        except BaseException as error:
            for item in reversed(added_scene_items):
                try:
                    remove_scene_item(self.canvas, item)
                except BaseException as cleanup_error:
                    _add_structure_insert_rollback_note(
                        error,
                        f"Structure insert scene cleanup also failed: {cleanup_error!r}",
                    )
            try:
                rollback_insert_mutation(
                    self.canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                    exact_transaction=exact_transaction,
                    smiles_authority=smiles_authority,
                    original_error=error,
                )
            except BaseException as cleanup_error:
                _add_structure_insert_rollback_note(
                    error,
                    f"Structure insert rollback also failed: {cleanup_error!r}",
                )
            raise
        return inserted_atom_ids, inserted_bond_ids


__all__ = ["StructureInsertService"]
