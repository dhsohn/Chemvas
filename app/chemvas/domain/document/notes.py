"""Rich-text note values, independent of a text editor or graphics scene."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Note:
    text: str = ""
    html: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


def note_to_document_state(note: Note) -> dict[str, object]:
    return {
        "text": note.text,
        "x": note.x,
        "y": note.y,
        **({"rotation": note.rotation} if note.rotation else {}),
        "html": note.html,
    }


def note_to_state(note: Note) -> dict[str, object]:
    return {"kind": "note", **note_to_document_state(note)}
