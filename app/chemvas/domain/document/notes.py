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
    # Detached native captions retain their baseline offset, justification and
    # source rotation independently of a document's retained CDXML bindings.
    native_caption: tuple[float, float, str, float] | None = None


def note_to_document_state(note: Note) -> dict[str, object]:
    return {
        "text": note.text,
        "x": note.x,
        "y": note.y,
        **({"rotation": note.rotation} if note.rotation else {}),
        "html": note.html,
        **(
            {"native_caption": list(note.native_caption)} if note.native_caption else {}
        ),
    }


def note_to_state(note: Note) -> dict[str, object]:
    return {"kind": "note", **note_to_document_state(note)}
