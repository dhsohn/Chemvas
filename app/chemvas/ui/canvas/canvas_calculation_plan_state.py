"""Carry a document's existing calculation plan through load, Undo and save.

Chemvas no longer creates, edits or runs calculation plans. Documents that
already contain one keep it: the plan read from the file is held here
unchanged and written back as-is, and a save refuses to proceed rather than
drop it when drawing edits leave its atom or bond references behind. This
module exists only to preserve that existing document data.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CanvasCalculationPlanState:
    plan: dict[str, object] | None = None


def calculation_plan_for(canvas: Any) -> dict[str, object] | None:
    plan = canvas.runtime_state.calculation_plan_state.plan
    return deepcopy(plan) if plan is not None else None


def set_calculation_plan_for(
    canvas: Any,
    plan: dict[str, object] | None,
) -> None:
    canvas.runtime_state.calculation_plan_state.plan = (
        deepcopy(plan) if plan is not None else None
    )


__all__ = [
    "CanvasCalculationPlanState",
    "calculation_plan_for",
    "set_calculation_plan_for",
]
