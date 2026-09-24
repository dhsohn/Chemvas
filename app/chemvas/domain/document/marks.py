"""Charge and radical annotations owned by the document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.domain.document.annotation_collection import AnnotationCollection


@dataclass(frozen=True, slots=True)
class Mark:
    kind: str = "plus"
    text: str | None = None
    atom_id: int | None = None
    dx: float | None = None
    dy: float | None = None
    x: float = 0.0
    y: float = 0.0
    color: str | None = None


def mark_to_state(mark: Mark) -> dict[str, object]:
    return {
        "kind": "mark",
        "mark_kind": mark.kind,
        "text": mark.text,
        "atom_id": mark.atom_id,
        "dx": mark.dx,
        "dy": mark.dy,
        "x": mark.x,
        "y": mark.y,
        **({"color": mark.color} if mark.color is not None else {}),
    }


def mark_kinds_by_atom(document: AnnotationCollection[Mark]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for record_id in document.order:
        mark = document.records[record_id]
        if mark.atom_id is not None:
            result.setdefault(mark.atom_id, []).append(mark.kind)
    return result
