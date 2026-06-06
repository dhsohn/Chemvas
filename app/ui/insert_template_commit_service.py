from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.insert_commit_rollback import rollback_insert_mutation
from ui.structure_insert_access import (
    add_atom_with_merge_for,
    add_insert_benzene_ring_for,
    add_insert_bond_for,
    add_insert_bond_graphics_for,
    add_insert_ring_from_points_for,
    has_insert_mutation_since_for,
    insert_atom_for_id,
    insert_bond_count_for,
    insert_bond_exists_for,
    insert_bond_for_id,
    insert_next_atom_id_for,
    new_insert_bond_ids_from,
    record_insert_additions_for,
)
from ui.template_insert_logic import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


def apply_template_commit_resolution(
    canvas: CanvasView,
    request: TemplateInsertRequest,
    plan: TemplateInsertPlan,
    resolution: TemplateInsertResolution | None,
    *,
    before_smiles_input: str | None,
    after_smiles_input: str | None = None,
    bond_exists: Callable[[int, int], bool] | None = None,
) -> bool:
    if plan.generator == "benzene":
        return _apply_benzene_template_commit(
            canvas,
            request,
            plan,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    if resolution is None or resolution.points is None:
        return False

    points = [QPointF(x, y) for x, y in resolution.points]
    before_next_atom_id = insert_next_atom_id_for(canvas)
    before_bond_count = insert_bond_count_for(canvas)

    try:
        if plan.generator in {"bond_regular_ring", "bond_template_shape"}:
            if plan.bond_id is None:
                return False
            merge = bond_merge_seed(canvas, plan.bond_id)
            if not merge:
                return False
            set_last_smiles_input_for(canvas, after_smiles_input)
            atom_ids: list[int] = []
            for point in points:
                atom_ids.append(add_atom_with_merge_for(canvas, point, "C", merge))
            bonds_start = insert_bond_count_for(canvas)
            for index in range(len(atom_ids)):
                a_id = atom_ids[index]
                b_id = atom_ids[(index + 1) % len(atom_ids)]
                if insert_bond_exists_for(canvas, a_id, b_id, bond_exists=bond_exists):
                    continue
                add_insert_bond_for(canvas, a_id, b_id)
            for new_bond_id in new_insert_bond_ids_from(canvas, bonds_start):
                add_insert_bond_graphics_for(canvas, new_bond_id)
        else:
            set_last_smiles_input_for(canvas, after_smiles_input)
            add_insert_ring_from_points_for(canvas, points)

        record_insert_additions_for(
            canvas,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
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


def _apply_benzene_template_commit(
    canvas: CanvasView,
    request: TemplateInsertRequest,
    plan: TemplateInsertPlan,
    *,
    before_smiles_input: str | None,
    after_smiles_input: str | None,
) -> bool:
    center = QPointF(*request.cursor_pos)
    before_next_atom_id = insert_next_atom_id_for(canvas)
    before_bond_count = insert_bond_count_for(canvas)
    try:
        set_last_smiles_input_for(canvas, after_smiles_input)
        add_insert_benzene_ring_for(
            canvas,
            center,
            attach_bond_id=plan.bond_id,
            before_smiles_input=before_smiles_input,
        )
        changed = has_insert_mutation_since_for(canvas, before_next_atom_id, before_bond_count)
        if not changed:
            rollback_insert_mutation(
                canvas,
                before_next_atom_id=before_next_atom_id,
                before_bond_count=before_bond_count,
                before_smiles_input=before_smiles_input,
            )
            return False
    except Exception:
        rollback_insert_mutation(
            canvas,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
        )
        raise
    return True


def bond_merge_seed(canvas: CanvasView, bond_id: int) -> list[tuple[int, float, float]]:
    bond = insert_bond_for_id(canvas, bond_id)
    if bond is None:
        return []
    atom_a = insert_atom_for_id(canvas, bond.a)
    atom_b = insert_atom_for_id(canvas, bond.b)
    if atom_a is None or atom_b is None:
        return []
    return [(bond.a, atom_a.x, atom_a.y), (bond.b, atom_b.x, atom_b.y)]


__all__ = ["apply_template_commit_resolution", "bond_merge_seed"]
