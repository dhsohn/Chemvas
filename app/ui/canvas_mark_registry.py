from __future__ import annotations

from typing import Any

from ui.canvas_state_lookup import canvas_state_object


class CanvasMarkRegistry:
    def __init__(self, by_atom: dict[int, list[Any]] | None = None) -> None:
        self.by_atom: dict[int, list[Any]] = by_atom if by_atom is not None else {}

    def get_for_atom(self, atom_id: int) -> list[Any] | None:
        return self.by_atom.get(atom_id)

    def add_for_atom(self, atom_id: int, item: Any) -> None:
        marks = self.by_atom.setdefault(atom_id, [])
        if item not in marks:
            marks.append(item)

    def pop_for_atom(self, atom_id: int) -> list[Any]:
        return self.by_atom.pop(atom_id, [])

    def clear(self) -> None:
        self.by_atom = {}

    def items(self):
        return self.by_atom.items()


def mark_registry_for(canvas: Any) -> CanvasMarkRegistry:
    registry = canvas_state_object(canvas, "mark_registry")
    if registry is not None:
        return registry
    registry = CanvasMarkRegistry()
    canvas.mark_registry = registry
    return registry


__all__ = ["CanvasMarkRegistry", "mark_registry_for"]
