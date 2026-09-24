"""Selection runtime state and the single canvas-to-selection lookup.

Qt selection and explicit note selection retain distinct input semantics. This
state owns the latter together with selection painting; queries combine them.
The leaf lookup avoids importing the controller into its own Qt collaborators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtGui import QColor


@dataclass(slots=True)
class SelectionState:
    selected_notes: list[Any] = field(default_factory=list)
    color: QColor = field(default_factory=lambda: QColor("#0d9488"))
    suspend_outline: bool = False
    outlines: list[Any] = field(default_factory=list)


def add_selected_note_for(canvas: Any, note: Any) -> None:
    notes = canvas.runtime_state.selection_state.selected_notes
    if note not in notes:
        notes.append(note)


def remove_selected_note_for(canvas: Any, note: Any) -> bool:
    notes = canvas.runtime_state.selection_state.selected_notes
    if note not in notes:
        return False
    notes.remove(note)
    return True


def set_selection_outlines_for(canvas: Any, outlines: list[Any]) -> None:
    state = canvas.runtime_state.selection_state
    state.outlines = outlines


def append_selection_outline_for(canvas: Any, outline: Any) -> None:
    state = canvas.runtime_state.selection_state
    state.outlines.append(outline)


def clear_selection_outlines_for(canvas: Any) -> None:
    set_selection_outlines_for(canvas, [])
