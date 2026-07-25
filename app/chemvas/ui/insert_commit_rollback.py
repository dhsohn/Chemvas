from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.domain.transactions import RestoreOutcome, restore_snapshot
from chemvas.ui.canvas_smiles_input_state import (
    CanvasSmilesInputState,
    smiles_input_state_for,
)
from chemvas.ui.history_canvas_access import restore_history_transaction_for_history
from chemvas.ui.structure_insert_access import rollback_insert_mutation_for
from chemvas.ui.transactions.document import DocumentSavepoint

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(frozen=True, slots=True)
class SmilesInputRestoreAuthority:
    state: CanvasSmilesInputState

    @classmethod
    def capture(cls, canvas: object) -> SmilesInputRestoreAuthority:
        return cls(state=smiles_input_state_for(canvas))

    def restore(self, target: str | None) -> RestoreOutcome:
        try:
            self.state.last_smiles_input = target
            if self.state.last_smiles_input != target:
                raise RuntimeError("SMILES rollback did not restore the target value")
        except Exception as error:
            return RestoreOutcome(
                authoritative=False,
                fallback_to_inverse=False,
                errors=(error,),
            )
        return RestoreOutcome(authoritative=True)


def capture_smiles_input_restore_authority(
    canvas: object,
) -> SmilesInputRestoreAuthority:
    return SmilesInputRestoreAuthority.capture(canvas)


def _add_insert_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"Insert rollback also failed: {rollback_error!r}")
    except Exception:
        return


def rollback_insert_mutation(
    canvas: CanvasView,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: str | None,
    exact_transaction: DocumentSavepoint | None = None,
    smiles_authority: SmilesInputRestoreAuthority | None = None,
    original_error: BaseException | None = None,
) -> RestoreOutcome:
    if smiles_authority is None:
        smiles_authority = capture_smiles_input_restore_authority(canvas)
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
            lambda: restore_history_transaction_for_history(
                canvas,
                exact_transaction,
            ),
            description="insert transaction",
        )
        if original_error is not None or not restore_result.authoritative:
            rollback_errors.extend(restore_result.errors)
        authoritative = authoritative and restore_result.authoritative
    smiles_result = smiles_authority.restore(before_smiles_input)
    rollback_errors.extend(smiles_result.errors)
    authoritative = authoritative and smiles_result.authoritative

    if not rollback_errors:
        return RestoreOutcome(authoritative=authoritative)
    if original_error is not None:
        for rollback_error in rollback_errors:
            _add_insert_rollback_note(original_error, rollback_error)
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
    "SmilesInputRestoreAuthority",
    "capture_smiles_input_restore_authority",
    "rollback_insert_mutation",
]
