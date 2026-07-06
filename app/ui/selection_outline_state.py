from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class SelectionOutlineState:
    outlines: list[Any] = field(default_factory=list)


def selection_outline_state_for(canvas: Any) -> SelectionOutlineState:
    return ensure_canvas_state(canvas, "selection_outline_state", SelectionOutlineState)


def selection_outlines_for(canvas: Any) -> list[Any]:
    return selection_outline_state_for(canvas).outlines


def set_selection_outlines_for(canvas: Any, outlines: list[Any]) -> None:
    state = selection_outline_state_for(canvas)
    state.outlines = outlines


def append_selection_outline_for(canvas: Any, outline: Any) -> None:
    state = selection_outline_state_for(canvas)
    state.outlines.append(outline)


def clear_selection_outlines_for(canvas: Any) -> None:
    set_selection_outlines_for(canvas, [])


__all__ = [
    "SelectionOutlineState",
    "append_selection_outline_for",
    "clear_selection_outlines_for",
    "selection_outline_state_for",
    "selection_outlines_for",
    "set_selection_outlines_for",
]
