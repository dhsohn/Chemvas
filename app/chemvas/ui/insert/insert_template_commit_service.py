from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.ui.insert.template_commit_logic import commit_template_ring
from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter
from chemvas.ui.molecule.structure_insert_access import (
    add_insert_ring_from_points_for,
    build_insert_benzene_ring_for,
    has_insert_mutation_since_for,
    insert_bond_exists_for,
)
from chemvas.ui.scene.scene_group_operations import group_connection_allowed_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.features.insertion import (
        TemplateInsertPlan,
        TemplateInsertRequest,
        TemplateInsertResolution,
    )
    from chemvas.ui.canvas.canvas_view import CanvasView


def apply_template_commit_resolution(
    canvas: CanvasView,
    request: TemplateInsertRequest,
    plan: TemplateInsertPlan,
    resolution: TemplateInsertResolution | None,
    *,
    bond_exists: Callable[[int, int], bool] | None = None,
) -> bool:
    anchors = {plan.atom_id} if plan.atom_id is not None else set()
    bond = canvas.model.bond_for_id(plan.bond_id)
    if bond is not None:
        anchors.update((bond.a, bond.b))
    if anchors and not group_connection_allowed_for(canvas, anchors):
        return False
    if plan.generator == "benzene":
        return _apply_benzene_template_commit(
            canvas,
            request,
            plan,
        )

    if (
        resolution is None
        or resolution.points is None
        or len(resolution.points) != plan.ring_size
    ):
        return False

    points = [QPointF(x, y) for x, y in resolution.points]
    committer = StructureBuildCommitter(canvas)
    snapshot = committer.begin_recorded_change()
    builder = canvas.services.structure_build_service
    try:
        if not commit_template_ring(
            canvas,
            plan,
            points,
            add_atom_with_merge=builder.add_atom_with_merge,
            add_ring_from_points=lambda ring: add_insert_ring_from_points_for(
                canvas, ring
            ),
            add_ring_fill=committer.add_ring_fill,
            bond_exists=lambda a_id, b_id: insert_bond_exists_for(
                canvas, a_id, b_id, bond_exists=bond_exists
            ),
        ):
            committer.abort_recorded_change(snapshot)
            return False
        committer.record_additions(snapshot)
    except Exception as error:
        committer.abort_recorded_change(snapshot, original_error=error)
        raise
    return True


def _apply_benzene_template_commit(
    canvas: CanvasView, request: TemplateInsertRequest, plan: TemplateInsertPlan
) -> bool:
    center = QPointF(*request.cursor_pos)
    committer = StructureBuildCommitter(canvas)
    snapshot = committer.begin_recorded_change()
    try:
        build_insert_benzene_ring_for(
            canvas,
            center,
            attach_atom_id=plan.atom_id,
            attach_bond_id=plan.bond_id,
        )
        changed = has_insert_mutation_since_for(
            canvas, snapshot.before_next_atom_id, snapshot.before_bond_count
        )
        if changed:
            committer.record_additions(snapshot)
    except Exception as error:
        committer.abort_recorded_change(snapshot, original_error=error)
        raise
    if not changed:
        committer.abort_recorded_change(snapshot)
        return False
    return True


__all__ = ["apply_template_commit_resolution"]
