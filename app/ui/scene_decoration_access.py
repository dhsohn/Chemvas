from __future__ import annotations

from ui.scene_decoration_ports import (
    mark_scene_service_for_access,
    scene_decoration_build_service_for_access,
    scene_decoration_service_for_access,
)


def _decoration_service_method(canvas, name: str):
    try:
        service = scene_decoration_service_for_access(canvas)
    except AttributeError:
        return None
    method = getattr(service, name, None)
    return method if callable(method) else None


def _build_service_method(canvas, name: str):
    try:
        service = scene_decoration_build_service_for_access(canvas)
    except AttributeError:
        return None
    method = getattr(service, name, None)
    return method if callable(method) else None


def add_arrow_for(canvas, start, end, kind: str):
    method = _decoration_service_method(canvas, "add_arrow")
    if method is not None:
        return method(start, end, kind)
    return None


def add_mark_for(
    canvas,
    pos,
    *,
    kind: str | None = None,
    atom_id: int | None = None,
    offset=None,
    record: bool = True,
):
    method = _decoration_service_method(canvas, "add_mark")
    if method is not None:
        return method(pos, kind=kind, atom_id=atom_id, offset=offset, record=record)
    return None


def add_mark_for_atom_for(
    canvas,
    atom_id: int,
    click_pos,
    *,
    kind: str | None = None,
    record: bool = True,
):
    try:
        service = mark_scene_service_for_access(canvas)
    except AttributeError:
        service = None
    method = getattr(service, "add_mark_for_atom", None) if service is not None else None
    if callable(method):
        return method(atom_id, click_pos, kind=kind, record=record)
    return None


def preview_arrow_for(canvas, start, end, kind: str):
    method = _build_service_method(canvas, "preview_arrow")
    if method is not None:
        return method(start, end, kind)
    return None


def add_ts_bracket_for(canvas, rect):
    method = _decoration_service_method(canvas, "add_ts_bracket")
    if method is not None:
        return method(rect)
    return None


def add_ts_bracket_from_points_for(canvas, start, end):
    rect_from_points = _build_service_method(canvas, "ts_bracket_rect_from_points")
    if rect_from_points is not None:
        return add_ts_bracket_for(canvas, rect_from_points(start, end))
    return None


def preview_ts_bracket_for(canvas, start, end):
    method = _build_service_method(canvas, "preview_ts_bracket")
    if method is not None:
        return method(start, end)
    return None


def add_orbital_for(canvas, center):
    method = _decoration_service_method(canvas, "add_orbital")
    if method is not None:
        return method(center)
    return None


__all__ = [
    "add_arrow_for",
    "add_mark_for",
    "add_mark_for_atom_for",
    "add_orbital_for",
    "add_ts_bracket_for",
    "add_ts_bracket_from_points_for",
    "preview_arrow_for",
    "preview_ts_bracket_for",
]
