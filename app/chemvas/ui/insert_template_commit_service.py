from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.features.insertion import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
)
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
)
from chemvas.ui.insert_commit_rollback import (
    capture_smiles_input_restore_authority,
    rollback_insert_mutation,
)
from chemvas.ui.structure_build_committer import StructureBuildCommitter
from chemvas.ui.structure_insert_access import (
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
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


def _add_template_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"Template rollback also failed: {rollback_error!r}")
    except BaseException:
        return


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

    if (
        resolution is None
        or resolution.points is None
        or len(resolution.points) != plan.ring_size
    ):
        return False

    points = [QPointF(x, y) for x, y in resolution.points]
    committer = StructureBuildCommitter(canvas)
    snapshot = committer.begin_recorded_change(before_smiles_input=before_smiles_input)

    try:
        if plan.generator in {
            "atom_regular_ring",
            "bond_regular_ring",
            "bond_template_shape",
        }:
            if plan.generator == "atom_regular_ring":
                if plan.atom_id is None:
                    committer.abort_recorded_change(snapshot)
                    return False
                merge = atom_merge_seed(canvas, plan.atom_id)
            elif plan.bond_id is not None:
                merge = bond_merge_seed(canvas, plan.bond_id)
            else:
                committer.abort_recorded_change(snapshot)
                return False
            if not merge:
                committer.abort_recorded_change(snapshot)
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
            committer.add_ring_fill(points, atom_ids)
        else:
            set_last_smiles_input_for(canvas, after_smiles_input)
            add_insert_ring_from_points_for(canvas, points)

        committer.record_additions(snapshot)
    except BaseException as error:
        try:
            committer.abort_recorded_change(snapshot, original_error=error)
        except BaseException as rollback_error:
            _add_template_rollback_note(error, rollback_error)
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
    smiles_authority = capture_smiles_input_restore_authority(canvas)
    services = getattr(canvas, "services", None)
    exact_transaction = None
    try:
        # Exact capture is itself fallible extension code.  If a live capture
        # port mutates the SMILES input and then raises, the same rollback path
        # must restore the authority even though no ring atom exists yet.
        exact_transaction = capture_history_transaction_for_history(
            canvas,
            history_service=getattr(services, "history_service", None),
        )
        set_last_smiles_input_for(canvas, after_smiles_input)
        add_insert_benzene_ring_for(
            canvas,
            center,
            attach_atom_id=plan.atom_id,
            attach_bond_id=plan.bond_id,
            before_smiles_input=before_smiles_input,
        )
        changed = has_insert_mutation_since_for(
            canvas, before_next_atom_id, before_bond_count
        )
        if not changed:
            rollback_insert_mutation(
                canvas,
                before_next_atom_id=before_next_atom_id,
                before_bond_count=before_bond_count,
                before_smiles_input=before_smiles_input,
                exact_transaction=exact_transaction,
                smiles_authority=smiles_authority,
            )
            return False
        release_history_transaction_for_history(canvas, exact_transaction)
    except BaseException as error:
        try:
            rollback_insert_mutation(
                canvas,
                before_next_atom_id=before_next_atom_id,
                before_bond_count=before_bond_count,
                before_smiles_input=before_smiles_input,
                exact_transaction=exact_transaction,
                smiles_authority=smiles_authority,
                original_error=error,
            )
        except BaseException as rollback_error:
            _add_template_rollback_note(error, rollback_error)
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


def atom_merge_seed(canvas: CanvasView, atom_id: int) -> list[tuple[int, float, float]]:
    atom = insert_atom_for_id(canvas, atom_id)
    if atom is None:
        return []
    return [(atom_id, atom.x, atom.y)]


__all__ = ["apply_template_commit_resolution", "atom_merge_seed", "bond_merge_seed"]
