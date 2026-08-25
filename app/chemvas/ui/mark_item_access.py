from __future__ import annotations

from chemvas.ui.canvas_service_ports import (
    mark_scene_service_for_access,
    scene_decoration_build_service_for_access,
)
from chemvas.ui.pick_radius_access import atom_pick_radius_for


def build_mark_item_for(canvas, kind: str):
    return scene_decoration_build_service_for_access(canvas).build_mark_item(kind)


def mark_center_for(canvas, item):
    return scene_decoration_build_service_for_access(canvas).mark_center(item)


def set_mark_center_for(canvas, item, center) -> None:
    scene_decoration_build_service_for_access(canvas).set_mark_center(item, center)


def remove_mark_item_for(canvas, item) -> None:
    mark_scene_service_for_access(canvas).remove_mark_item(item)


def remove_marks_for_atom_for(canvas, atom_id: int) -> None:
    mark_scene_service_for_access(canvas).remove_marks_for_atom(atom_id)


def mark_center_for_pointer_for(canvas, pos, atom_id: int | None, *, kind: str | None):
    return mark_scene_service_for_access(canvas).mark_center_for_pointer(
        pos, atom_id, kind=kind
    )


def mark_selection_radius_for(canvas) -> float:
    return atom_pick_radius_for(canvas)


def mark_kinds_by_atom_for(canvas) -> dict[int, list[str]]:
    from chemvas.ui.canvas_mark_registry import mark_registry_for

    registry = mark_registry_for(canvas)
    mark_kinds_by_atom: dict[int, list[str]] = {}
    for atom_id, marks in registry.items():
        kinds: list[str] = []
        for mark in marks:
            data = mark.data(1)
            if not isinstance(data, dict):
                continue
            kind = data.get("kind")
            if isinstance(kind, str):
                kinds.append(kind)
        if kinds:
            mark_kinds_by_atom[atom_id] = kinds
    return mark_kinds_by_atom


__all__ = [
    "build_mark_item_for",
    "mark_center_for",
    "mark_center_for_pointer_for",
    "mark_kinds_by_atom_for",
    "mark_selection_radius_for",
    "remove_mark_item_for",
    "remove_marks_for_atom_for",
    "set_mark_center_for",
]
