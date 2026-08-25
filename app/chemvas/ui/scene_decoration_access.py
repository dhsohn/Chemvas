from __future__ import annotations

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.ui.canvas_service_ports import (
    mark_scene_service_for_access,
    scene_decoration_build_service_for_access,
    scene_decoration_service_for_access,
)


def add_arrow_for(canvas, start, end, kind: str):
    return scene_decoration_service_for_access(canvas).add_arrow(start, end, kind)


def add_mark_for(
    canvas,
    pos,
    *,
    kind: str | None = None,
    atom_id: int | None = None,
    offset=None,
    record: bool = True,
):
    return scene_decoration_service_for_access(canvas).add_mark(
        pos, kind=kind, atom_id=atom_id, offset=offset, record=record
    )


def add_mark_for_atom_for(
    canvas,
    atom_id: int,
    click_pos,
    *,
    kind: str | None = None,
    record: bool = True,
):
    return mark_scene_service_for_access(canvas).add_mark_for_atom(
        atom_id, click_pos, kind=kind, record=record
    )


def preview_arrow_for(canvas, start, end, kind: str):
    return scene_decoration_build_service_for_access(canvas).preview_arrow(
        start, end, kind
    )


def add_ts_bracket_for(canvas, rect, bracket_kind: str = DEFAULT_BRACKET_KIND):
    return scene_decoration_service_for_access(canvas).add_ts_bracket(
        rect, bracket_kind=bracket_kind
    )


def add_ts_bracket_from_points_for(
    canvas, start, end, bracket_kind: str = DEFAULT_BRACKET_KIND
):
    rect = scene_decoration_build_service_for_access(
        canvas
    ).ts_bracket_rect_from_points(start, end)
    return add_ts_bracket_for(canvas, rect, bracket_kind=bracket_kind)


def preview_ts_bracket_for(
    canvas, start, end, bracket_kind: str = DEFAULT_BRACKET_KIND
):
    return scene_decoration_build_service_for_access(canvas).preview_ts_bracket(
        start, end, bracket_kind
    )


def add_shape_for(
    canvas, rect, *, shape_kind: str | None = None, stroke_style: str | None = None
):
    return scene_decoration_service_for_access(canvas).add_shape(
        rect, shape_kind=shape_kind, stroke_style=stroke_style
    )


def add_shape_from_points_for(
    canvas,
    start,
    end,
    *,
    shape_kind: str | None = None,
    stroke_style: str | None = None,
):
    rect = scene_decoration_build_service_for_access(canvas).shape_rect_from_points(
        start, end
    )
    return add_shape_for(
        canvas,
        rect,
        shape_kind=shape_kind,
        stroke_style=stroke_style,
    )


def preview_shape_for(
    canvas,
    start,
    end,
    *,
    shape_kind: str | None = None,
    stroke_style: str | None = None,
):
    return scene_decoration_build_service_for_access(canvas).preview_shape(
        start, end, shape_kind or "circle", stroke_style or "solid"
    )


def add_orbital_for(canvas, center):
    return scene_decoration_service_for_access(canvas).add_orbital(center)


__all__ = [
    "add_arrow_for",
    "add_mark_for",
    "add_mark_for_atom_for",
    "add_orbital_for",
    "add_shape_for",
    "add_shape_from_points_for",
    "add_ts_bracket_for",
    "add_ts_bracket_from_points_for",
    "preview_arrow_for",
    "preview_shape_for",
    "preview_ts_bracket_for",
]
