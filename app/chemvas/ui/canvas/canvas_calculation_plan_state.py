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
