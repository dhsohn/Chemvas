from __future__ import annotations

from typing import Any, cast


class CanvasMarkRegistry:
    def __init__(self, by_atom: dict[int, list[Any]] | None = None) -> None:
        self.by_atom: dict[int, list[Any]] = by_atom if by_atom is not None else {}

    def get_for_atom(self, atom_id: int) -> list[Any] | None:
        return self.by_atom.get(atom_id)

    def add_for_atom(self, atom_id: int, item: Any) -> None:
        marks = self.by_atom.setdefault(atom_id, [])
        if item not in marks:
            marks.append(item)

    def discard(self, atom_id: int, item: Any) -> None:
        marks = self.by_atom.get(atom_id)
        if marks is None:
            return
        if item in marks:
            marks.remove(item)
        if not marks:
            self.by_atom.pop(atom_id, None)

    def replace_for_atom(self, atom_id: int, items: list[Any]) -> None:
        deduped: list[Any] = []
        for item in items:
            if item not in deduped:
                deduped.append(item)
        if deduped:
            self.by_atom[atom_id] = deduped
        else:
            self.by_atom.pop(atom_id, None)

    def reorder_for_atom(self, atom_id: int, placements: list[tuple[int, Any]]) -> None:
        marks = self.by_atom.get(atom_id)
        if marks is None:
            raise RuntimeError("Restored marks require an owner registry")
        if not placements:
            return
        for _, item in placements:
            marks.remove(item)
        for index, item in placements:
            marks.insert(index, item)

    def pop_for_atom(self, atom_id: int) -> list[Any]:
        return self.by_atom.pop(atom_id, [])

    def clear(self) -> None:
        self.by_atom = {}

    def items(self):
        return self.by_atom.items()


def mark_registry_for(canvas: Any) -> CanvasMarkRegistry:
    return cast("CanvasMarkRegistry", canvas.runtime_state.mark_registry)


__all__ = ["CanvasMarkRegistry", "mark_registry_for"]
