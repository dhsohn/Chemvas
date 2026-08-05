from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from chemvas.ui.canvas_state_lookup import ensure_canvas_state


@dataclass
class CanvasCalculationPlanState:
    plan: dict[str, object] | None = None


def calculation_plan_state_for(canvas: Any) -> CanvasCalculationPlanState:
    return ensure_canvas_state(
        canvas,
        "calculation_plan_state",
        CanvasCalculationPlanState,
    )


def calculation_plan_for(canvas: Any) -> dict[str, object] | None:
    plan = calculation_plan_state_for(canvas).plan
    return deepcopy(plan) if plan is not None else None


def set_calculation_plan_for(
    canvas: Any,
    plan: dict[str, object] | None,
) -> None:
    calculation_plan_state_for(canvas).plan = (
        deepcopy(plan) if plan is not None else None
    )


__all__ = [
    "CanvasCalculationPlanState",
    "calculation_plan_for",
    "calculation_plan_state_for",
    "set_calculation_plan_for",
]
