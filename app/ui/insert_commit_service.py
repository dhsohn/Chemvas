from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.insert_smiles_commit_service import apply_smiles_commit_plan
from ui.insert_template_commit_service import (
    apply_template_commit_resolution,
)
from ui.insert_template_commit_service import (
    bond_merge_seed as template_bond_merge_seed,
)
from ui.smiles_insert_logic import SmilesCommitPlan
from ui.template_insert_logic import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class InsertCommitService:
    canvas: CanvasView
    bond_exists: Callable[[int, int], bool] | None = None

    def apply_smiles_commit(
        self,
        plan: SmilesCommitPlan | None,
        *,
        before_smiles_input: str | None = None,
        after_smiles_input: str | None,
    ) -> bool:
        return apply_smiles_commit_plan(
            self.canvas,
            plan,
            before_smiles_input=last_smiles_input_for(self.canvas)
            if before_smiles_input is None
            else before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    def apply_smiles_commit_plan(
        self,
        plan: SmilesCommitPlan | None,
        *,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
    ) -> bool:
        return apply_smiles_commit_plan(
            self.canvas,
            plan,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    def apply_template_commit(
        self,
        pos: QPointF,
        *,
        request: TemplateInsertRequest,
        plan: TemplateInsertPlan,
        resolution: TemplateInsertResolution | None,
        before_smiles_input: str | None = None,
        after_smiles_input: str | None = None,
    ) -> bool:
        if request.cursor_pos != (pos.x(), pos.y()):
            request = TemplateInsertRequest(
                ring_size=request.ring_size,
                cursor_pos=(pos.x(), pos.y()),
                bond_id=request.bond_id,
                ring_style=request.ring_style,
            )
        return apply_template_commit_resolution(
            self.canvas,
            request,
            plan,
            resolution,
            before_smiles_input=last_smiles_input_for(self.canvas)
            if before_smiles_input is None
            else before_smiles_input,
            after_smiles_input=after_smiles_input,
            bond_exists=self.bond_exists,
        )

    def apply_template_commit_resolution(
        self,
        request: TemplateInsertRequest,
        plan: TemplateInsertPlan,
        resolution: TemplateInsertResolution | None,
        *,
        before_smiles_input: str | None,
        after_smiles_input: str | None = None,
    ) -> bool:
        return apply_template_commit_resolution(
            self.canvas,
            request,
            plan,
            resolution,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
            bond_exists=self.bond_exists,
        )

    def bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        if bond_id is None:
            return []
        return template_bond_merge_seed(self.canvas, bond_id)


__all__ = [
    "InsertCommitService",
    "apply_smiles_commit_plan",
    "apply_template_commit_resolution",
]
