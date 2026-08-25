from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.insertion import SmilesCommitPlan
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_model_access import atom_for_id, bond_count_for, bond_ids_from
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.structure_build_committer import StructureBuildCommitter
from chemvas.ui.structure_insert_access import (
    add_or_update_insert_atom_label_for,
    ensure_insert_carbon_dot_for,
    set_inserted_atom_annotation_for,
    set_inserted_atom_metadata_for,
    set_inserted_bond_metadata_for,
)
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


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
        if (
            bond_plan.source_a not in source_atom_ids
            or bond_plan.source_b not in source_atom_ids
        ):
            return False

    committer = StructureBuildCommitter(canvas)
    snapshot = committer.begin_recorded_change(
        before_smiles_input=before_smiles_input,
    )
    id_map: dict[int, int] = {}
    added_scene_items: list[object] = []
    aborted = False

    def abort(*, original_error: BaseException | None = None) -> None:
        nonlocal aborted
        aborted = True
        committer.abort_recorded_change(
            snapshot,
            added_scene_items=added_scene_items,
            original_error=original_error,
        )

    try:
        for atom_plan in plan.atoms:
            new_id = add_atom_for(canvas, atom_plan.element, atom_plan.x, atom_plan.y)
            if not set_inserted_atom_metadata_for(
                canvas,
                new_id,
                color=atom_plan.color,
                explicit_label=atom_plan.explicit_label,
            ):
                abort()
                return False
            id_map[atom_plan.source_atom_id] = new_id

        bonds_start = bond_count_for(canvas)
        for bond_plan in plan.bonds:
            a_id = id_map.get(bond_plan.source_a)
            b_id = id_map.get(bond_plan.source_b)
            if a_id is None or b_id is None:
                abort()
                return False
            bond_id = add_bond_for(canvas, a_id, b_id, bond_plan.order)
            if not set_inserted_bond_metadata_for(
                canvas,
                bond_id,
                style=bond_plan.style,
                color=bond_plan.color,
            ):
                abort()
                return False

        for new_bond_id in bond_ids_from(canvas, bonds_start):
            add_bond_graphics_for(canvas, new_bond_id)

        for new_id in id_map.values():
            atom = atom_for_id(canvas, new_id)
            if atom is None:
                abort()
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
                abort()
                return False
            if not set_inserted_atom_annotation_for(
                canvas, annotated_atom_id, annotation
            ):
                abort()
                return False

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
        committer.record_additions(
            snapshot,
            added_scene_items=added_scene_items or None,
        )
    except Exception as error:
        if not aborted:
            abort(original_error=error)
        raise
    return True


__all__ = ["apply_smiles_commit_plan"]
