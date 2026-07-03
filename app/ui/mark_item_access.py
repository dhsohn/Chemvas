from __future__ import annotations

from ui.canvas_service_ports import (
    mark_scene_service_for_access,
    scene_decoration_build_service_for_access,
)
from ui.pick_radius_access import atom_pick_radius_for


def _decoration_build_service(canvas):
    try:
        return scene_decoration_build_service_for_access(canvas)
    except AttributeError:
        return None


def _mark_scene_service(canvas):
    try:
        return mark_scene_service_for_access(canvas)
    except AttributeError:
        return None


def build_mark_item_for(canvas, kind: str):
    service = _decoration_build_service(canvas)
    build_mark_item = getattr(service, "build_mark_item", None)
    if callable(build_mark_item):
        return build_mark_item(kind)
    return None


def mark_center_for(canvas, item):
    service = _decoration_build_service(canvas)
    mark_center = getattr(service, "mark_center", None)
    if callable(mark_center):
        return mark_center(item)
    return item.pos()


def set_mark_center_for(canvas, item, center) -> None:
    service = _decoration_build_service(canvas)
    set_mark_center = getattr(service, "set_mark_center", None)
    if callable(set_mark_center):
        set_mark_center(item, center)
        return


def remove_mark_item_for(canvas, item) -> None:
    service = _mark_scene_service(canvas)
    remove_mark_item = getattr(service, "remove_mark_item", None)
    if callable(remove_mark_item):
        remove_mark_item(item)
        return


def remove_marks_for_atom_for(canvas, atom_id: int) -> None:
    service = _mark_scene_service(canvas)
    remove_marks_for_atom = getattr(service, "remove_marks_for_atom", None)
    if callable(remove_marks_for_atom):
        remove_marks_for_atom(atom_id)
        return


def mark_offset_from_click_for(canvas, atom_id: int, click_pos, *, kind: str | None = None):
    service = _mark_scene_service(canvas)
    mark_offset_from_click = getattr(service, "mark_offset_from_click", None)
    if callable(mark_offset_from_click):
        return mark_offset_from_click(atom_id, click_pos, kind=kind)
    return click_pos


def mark_center_for_pointer_for(canvas, pos, atom_id: int | None, *, kind: str | None):
    service = _mark_scene_service(canvas)
    mark_center_for_pointer = getattr(service, "mark_center_for_pointer", None)
    if callable(mark_center_for_pointer):
        return mark_center_for_pointer(pos, atom_id, kind=kind)
    return pos


def mark_selection_radius_for(canvas) -> float:
    return atom_pick_radius_for(canvas)


def mark_kinds_by_atom_for(canvas) -> dict[int, list[str]]:
    from ui.canvas_mark_registry import mark_registry_for

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
    "mark_offset_from_click_for",
    "mark_selection_radius_for",
    "remove_mark_item_for",
    "remove_marks_for_atom_for",
    "set_mark_center_for",
]
