from __future__ import annotations

from typing import TYPE_CHECKING

from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.structure_insert_access import rollback_insert_mutation_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


def rollback_insert_mutation(
    canvas: CanvasView,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: str | None,
) -> None:
    rollback_insert_mutation_for(
        canvas,
        before_next_atom_id=before_next_atom_id,
        before_bond_count=before_bond_count,
    )
    set_last_smiles_input_for(canvas, before_smiles_input)


__all__ = ["rollback_insert_mutation"]
