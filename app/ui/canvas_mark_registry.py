from __future__ import annotations

from typing import Any

from ui.canvas_state_lookup import canvas_state_object


class CanvasMarkRegistry:
    def __init__(self, by_atom: dict[int, list[Any]] | None = None) -> None:
        self.by_atom: dict[int, list[Any]] = by_atom if by_atom is not None else {}

    def get_for_atom(self, atom_id: int) -> list[Any] | None:
        return self.by_atom.get(atom_id)

    def set_for_atom(self, atom_id: int, marks: list[Any]) -> None:
        self.by_atom[atom_id] = marks

    def add_for_atom(self, atom_id: int, item: Any) -> None:
        marks = self.by_atom.setdefault(atom_id, [])
        if item not in marks:
            marks.append(item)

    def remove_item(self, item: Any) -> int | None:
        data = item.data(1) or {}
        atom_id = data.get("atom_id") if isinstance(data, dict) else None
        if not isinstance(atom_id, int):
            return None
        marks = self.by_atom.get(atom_id)
        if marks is not None and item in marks:
            marks.remove(item)
        if marks is not None and not marks:
            self.by_atom.pop(atom_id, None)
        return atom_id

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
