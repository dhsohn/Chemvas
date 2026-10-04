from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SelectionPressAction = Literal[
    "ignore", "drag_current_selection", "reselect_preferred_and_drag"
]


@dataclass(frozen=True)
class SelectionPressContext:
    has_selection_target: bool
    hits_current_selection: bool
    has_preferred_structure: bool


@dataclass(frozen=True)
class SelectionPressDecision:
    action: SelectionPressAction


# Scene objects a press selects directly (with arrows); Control toggles one
# that is not selected yet instead of starting a drag.
DIRECT_SELECT_OBJECT_KINDS = frozenset(
    ("note", "shape", "image", "mark", "orbital", "ts_bracket")
)


def plan_selection_press(context: SelectionPressContext) -> SelectionPressDecision:
    if context.hits_current_selection and context.has_selection_target:
        return SelectionPressDecision(action="drag_current_selection")
    if context.has_preferred_structure:
        return SelectionPressDecision(action="reselect_preferred_and_drag")
    return SelectionPressDecision(action="ignore")


__all__ = [
    "DIRECT_SELECT_OBJECT_KINDS",
    "SelectionPressContext",
    "SelectionPressDecision",
    "plan_selection_press",
]
