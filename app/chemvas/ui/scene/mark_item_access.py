from __future__ import annotations

from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for


def build_mark_item_for(canvas, kind: str):
    return canvas.services.scene_decoration_build_service.build_mark_item(kind)


def apply_mark_color_for(canvas, item, color: str | None) -> None:
    canvas.services.scene_decoration_build_service.apply_mark_color(item, color)


def refresh_mark_item_geometry_for(canvas, item, kind: str) -> None:
    canvas.services.scene_decoration_build_service.refresh_mark_item_geometry(
        item, kind
    )


def mark_center_for(canvas, item):
    return canvas.services.scene_decoration_build_service.mark_center(item)


def set_mark_center_for(canvas, item, center) -> None:
    canvas.services.scene_decoration_build_service.set_mark_center(item, center)


def remove_mark_item_for(canvas, item) -> None:
    canvas.services.canvas_mark_scene_service.remove_mark_item(item)


def remove_marks_for_atom_for(canvas, atom_id: int) -> None:
    canvas.services.canvas_mark_scene_service.remove_marks_for_atom(atom_id)


def sync_marks_for_atom_for(canvas, atom_id: int) -> None:
    canvas.services.canvas_mark_scene_service.sync_marks_for_atom(atom_id)


def reveal_unmarked_isolated_carbons_for(canvas, atom_ids: set[int]):
    return canvas.services.canvas_mark_scene_service.reveal_unmarked_isolated_carbons(
        atom_ids
    )


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
    "apply_mark_color_for",
    "build_mark_item_for",
    "find_atom_for_mark_for",
    "mark_center_for",
    "mark_center_for_pointer_for",
    "mark_kinds_by_atom_for",
    "mark_selection_radius_for",
    "refresh_mark_item_geometry_for",
    "remove_mark_item_for",
    "remove_marks_for_atom_for",
    "reveal_unmarked_isolated_carbons_for",
    "set_mark_center_for",
    "sync_marks_for_atom_for",
]
