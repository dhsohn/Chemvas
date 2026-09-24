"""Selection runtime state and the single canvas-to-selection lookup.

Qt selection and explicit note selection retain distinct input semantics. This
state owns the latter together with selection painting; queries combine them.
The leaf lookup avoids importing the controller into its own Qt collaborators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtGui import QColor

if TYPE_CHECKING:
    from chemvas.ui.selection.selection_controller import SelectionController


@dataclass(slots=True)
class SelectionState:
    selected_notes: list[Any] = field(default_factory=list)
    color: QColor = field(default_factory=lambda: QColor("#0d9488"))
    suspend_outline: bool = False
    outlines: list[Any] = field(default_factory=list)


def selection_state_for(canvas: Any) -> SelectionState:
    return cast("SelectionState", canvas.runtime_state.selection_state)


def selection_for(canvas: Any) -> SelectionController:
    return cast("SelectionController", canvas.services.selection)


def selected_notes_for(canvas: Any) -> list[Any]:
    return selection_state_for(canvas).selected_notes


def set_selected_notes_for(canvas: Any, notes: list[Any]) -> None:
    selection_state_for(canvas).selected_notes = notes


def add_selected_note_for(canvas: Any, note: Any) -> None:
    notes = selected_notes_for(canvas)
    if note not in notes:
        notes.append(note)


def remove_selected_note_for(canvas: Any, note: Any) -> bool:
    notes = selected_notes_for(canvas)
    if note not in notes:
        return False
    notes.remove(note)
    return True


def clear_selected_notes_for(canvas: Any) -> None:
    set_selected_notes_for(canvas, [])


def selection_outlines_for(canvas: Any) -> list[Any]:
    return selection_state_for(canvas).outlines


def set_selection_outlines_for(canvas: Any, outlines: list[Any]) -> None:
    state = selection_state_for(canvas)
    state.outlines = outlines


def append_selection_outline_for(canvas: Any, outline: Any) -> None:
    state = selection_state_for(canvas)
    state.outlines.append(outline)


def clear_selection_outlines_for(canvas: Any) -> None:
    set_selection_outlines_for(canvas, [])
