from __future__ import annotations

from chemvas.ui.canvas_service_access import optional_canvas_service_method
from chemvas.ui.canvas_service_ports import (
    mark_scene_service_for_access,
    scene_decoration_build_service_for_access,
)
from chemvas.ui.pick_radius_access import atom_pick_radius_for


def _decoration_build_method(canvas, name: str):
    return optional_canvas_service_method(
        canvas, scene_decoration_build_service_for_access, name
    )


def _mark_scene_method(canvas, name: str):
    return optional_canvas_service_method(canvas, mark_scene_service_for_access, name)


def build_mark_item_for(canvas, kind: str):
    build_mark_item = _decoration_build_method(canvas, "build_mark_item")
    if build_mark_item is not None:
        return build_mark_item(kind)
    return None


def mark_center_for(canvas, item):
    mark_center = _decoration_build_method(canvas, "mark_center")
    if mark_center is not None:
        return mark_center(item)
    return item.pos()


def set_mark_center_for(canvas, item, center) -> None:
    set_mark_center = _decoration_build_method(canvas, "set_mark_center")
    if set_mark_center is not None:
        set_mark_center(item, center)
        return


def remove_mark_item_for(canvas, item) -> None:
    remove_mark_item = _mark_scene_method(canvas, "remove_mark_item")
    if remove_mark_item is not None:
        remove_mark_item(item)
        return


def remove_marks_for_atom_for(canvas, atom_id: int) -> None:
    remove_marks_for_atom = _mark_scene_method(canvas, "remove_marks_for_atom")
    if remove_marks_for_atom is not None:
        remove_marks_for_atom(atom_id)
        return


def mark_offset_from_click_for(
    canvas, atom_id: int, click_pos, *, kind: str | None = None
):
    mark_offset_from_click = _mark_scene_method(canvas, "mark_offset_from_click")
    if mark_offset_from_click is not None:
        return mark_offset_from_click(atom_id, click_pos, kind=kind)
    return click_pos


def mark_center_for_pointer_for(canvas, pos, atom_id: int | None, *, kind: str | None):
    mark_center_for_pointer = _mark_scene_method(canvas, "mark_center_for_pointer")
    if mark_center_for_pointer is not None:
        return mark_center_for_pointer(pos, atom_id, kind=kind)
    return pos


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
    "mark_offset_from_click_for",
    "mark_selection_radius_for",
    "remove_mark_item_for",
    "remove_marks_for_atom_for",
    "set_mark_center_for",
]
