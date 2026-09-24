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

    def add_selected_note(self, note: Any) -> None:
        if note not in self.selected_notes:
            self.selected_notes.append(note)

    def remove_selected_note(self, note: Any) -> bool:
        if note not in self.selected_notes:
            return False
        self.selected_notes.remove(note)
        return True

    def clear_selected_notes(self) -> list[Any]:
        """Deselect every note; returns the notes that were selected."""
        notes = list(self.selected_notes)
        self.selected_notes = []
        return notes


def set_selection_outlines_for(canvas: Any, outlines: list[Any]) -> None:
    state = canvas.runtime_state.selection_state
    state.outlines = outlines


def append_selection_outline_for(canvas: Any, outline: Any) -> None:
    state = canvas.runtime_state.selection_state
    state.outlines.append(outline)


def clear_selection_outlines_for(canvas: Any) -> None:
    set_selection_outlines_for(canvas, [])
