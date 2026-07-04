from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.insert_commit_rollback import rollback_insert_mutation
from ui.scene_decoration_access import add_mark_for_atom_for
from ui.smiles_insert_logic import SmilesCommitPlan
from ui.structure_insert_access import (
    add_insert_atom_for,
    add_insert_bond_for,
    add_insert_bond_graphics_for,
    add_or_update_insert_atom_label_for,
    ensure_insert_carbon_dot_for,
    insert_atom_for_id,
    insert_bond_count_for,
    insert_next_atom_id_for,
    new_insert_bond_ids_from,
    record_insert_additions_for,
    set_inserted_atom_annotation_for,
    set_inserted_atom_metadata_for,
    set_inserted_bond_metadata_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


def apply_smiles_commit_plan(
    canvas: CanvasView,
    plan: SmilesCommitPlan | None,
    *,
    before_smiles_input: str | None,
    after_smiles_input: str | None,
) -> bool:
    if plan is None or not plan.atoms:
        return False
    source_atom_ids = {atom.source_atom_id for atom in plan.atoms}
    if len(source_atom_ids) != len(plan.atoms):
        return False
    for bond_plan in plan.bonds:
        if bond_plan.source_a not in source_atom_ids or bond_plan.source_b not in source_atom_ids:
            return False

    before_next_atom_id = insert_next_atom_id_for(canvas)
    before_bond_count = insert_bond_count_for(canvas)

    id_map: dict[int, int] = {}
    try:
        for atom_plan in plan.atoms:
            new_id = add_insert_atom_for(canvas, atom_plan.element, atom_plan.x, atom_plan.y)
            if not set_inserted_atom_metadata_for(
                canvas,
                new_id,
                color=atom_plan.color,
                explicit_label=atom_plan.explicit_label,
            ):
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                )
                return False
            id_map[atom_plan.source_atom_id] = new_id

        bonds_start = insert_bond_count_for(canvas)
        for bond_plan in plan.bonds:
            a_id = id_map.get(bond_plan.source_a)
            b_id = id_map.get(bond_plan.source_b)
            if a_id is None or b_id is None:
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                )
                return False
            bond_id = add_insert_bond_for(canvas, a_id, b_id, bond_plan.order)
            if not set_inserted_bond_metadata_for(
                canvas,
                bond_id,
                style=bond_plan.style,
                color=bond_plan.color,
            ):
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                )
                return False

        for new_bond_id in new_insert_bond_ids_from(canvas, bonds_start):
            add_insert_bond_graphics_for(canvas, new_bond_id)

        for new_id in id_map.values():
            atom = insert_atom_for_id(canvas, new_id)
            if atom is None:
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                )
                return False
            if atom.element == "C" and not atom.explicit_label:
                ensure_insert_carbon_dot_for(canvas, new_id)
            else:
                add_or_update_insert_atom_label_for(
                    canvas,
                    new_id,
                    atom.element,
                    clear_smiles=False,
                    record=False,
                )

        for source_atom_id, annotation in plan.annotations.items():
            annotated_atom_id = id_map.get(source_atom_id)
            if annotated_atom_id is None:
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                )
                return False
            if not set_inserted_atom_annotation_for(canvas, annotated_atom_id, annotation):
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                    before_smiles_input=before_smiles_input,
                )
                return False

        added_scene_items = []
        for mark_plan in plan.marks:
            mark_atom_id = id_map.get(mark_plan.source_atom_id)
            if mark_atom_id is None:
                continue
            item = add_mark_for_atom_for(
                canvas,
                mark_atom_id,
                QPointF(mark_plan.x, mark_plan.y),
                kind=mark_plan.kind,
                record=False,
            )
            if item is not None:
                added_scene_items.append(item)

        set_last_smiles_input_for(canvas, after_smiles_input)
        record_insert_additions_for(
            canvas,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
            added_scene_items=added_scene_items or None,
        )
    except Exception:
        rollback_insert_mutation(
            canvas,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
        )
        raise
    return True


__all__ = ["apply_smiles_commit_plan"]
