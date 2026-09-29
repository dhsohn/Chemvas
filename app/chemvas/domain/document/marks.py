"""Charge and radical annotations owned by the document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

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


def mark_center_coordinates(
    state: Mapping[str, object], model_atoms: Mapping[int, Any]
) -> tuple[float, float] | None:
    center = None
    atom_id = state.get("atom_id")
    dx = state.get("dx")
    dy = state.get("dy")
    if isinstance(atom_id, int) and atom_id in model_atoms:
        atom = model_atoms[atom_id]
        if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
            center = (atom.x + dx, atom.y + dy)
    if center is None:
        x = state.get("x")
        y = state.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            center = (float(x), float(y))
    return center
