from __future__ import annotations

from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for


def mark_center_for_pointer_for(canvas, pos, atom_id: int | None, *, kind: str | None):
    return canvas.services.canvas_mark_scene_service.mark_center_for_pointer(
        pos, atom_id, kind=kind
    )


def find_atom_for_mark_for(canvas, pos, *, kind: str | None = None):
    return canvas.services.canvas_mark_scene_service.find_atom_for_mark(pos, kind=kind)


def mark_selection_radius_for(canvas) -> float:
    return atom_pick_radius_for(canvas)


def mark_kinds_by_atom_for(canvas) -> dict[int, list[str]]:
    from chemvas.domain.document.marks import mark_kinds_by_atom

    return mark_kinds_by_atom(canvas.runtime_state.mark_state)


__all__ = [
    "find_atom_for_mark_for",
    "mark_center_for_pointer_for",
    "mark_kinds_by_atom_for",
    "mark_selection_radius_for",
]
