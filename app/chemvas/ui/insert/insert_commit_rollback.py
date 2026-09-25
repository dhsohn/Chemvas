from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.domain.transactions import (
    RestoreOutcome,
    add_recovery_error_note,
    restore_snapshot,
)
from chemvas.ui.molecule.structure_insert_access import rollback_insert_mutation_for

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView
    from chemvas.ui.transactions.document import DocumentSavepoint


def rollback_insert_mutation(
    canvas: CanvasView,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    exact_transaction: DocumentSavepoint | None = None,
    original_error: BaseException | None = None,
) -> RestoreOutcome:
    rollback_errors: list[BaseException] = []
    authoritative = True
    try:
        rollback_insert_mutation_for(
            canvas,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
        )
    except Exception as caught_model_error:
        rollback_errors.append(caught_model_error)
        authoritative = False
    if exact_transaction is not None:
        restore_result = restore_snapshot(
            lambda: exact_transaction.restore(),
            description="insert transaction",
        )
        if original_error is not None or not restore_result.authoritative:
            rollback_errors.extend(restore_result.errors)
        authoritative = authoritative and restore_result.authoritative

    if not rollback_errors:
        return RestoreOutcome(authoritative=authoritative)
    if original_error is not None:
        for rollback_error in rollback_errors:
            add_recovery_error_note(
                original_error,
                rollback_error,
                phase="rolling back the insert mutation",
            )
        return RestoreOutcome(
            authoritative=authoritative,
            fallback_to_inverse=False,
            errors=tuple(rollback_errors),
        )
    if authoritative:
        return RestoreOutcome(
            authoritative=True,
            fallback_to_inverse=False,
            errors=tuple(rollback_errors),
        )
    if len(rollback_errors) == 1:
        raise rollback_errors[0]
    raise BaseExceptionGroup("Insert rollback failed", rollback_errors)


__all__ = [
    "rollback_insert_mutation",
]
