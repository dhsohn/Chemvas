from __future__ import annotations

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.ui.canvas_service_ports import scene_decoration_build_service_for_access


def build_arrow_item_for(canvas, start, end, kind: str):
    return scene_decoration_build_service_for_access(canvas).build_arrow_item(
        start, end, kind
    )


def ts_bracket_path_for(canvas, rect, bracket_kind: str = DEFAULT_BRACKET_KIND):
    return scene_decoration_build_service_for_access(canvas).ts_bracket_path(
        rect, bracket_kind
    )


def build_ts_bracket_item_for(canvas, rect, bracket_kind: str = DEFAULT_BRACKET_KIND):
    return scene_decoration_build_service_for_access(canvas).build_ts_bracket_item(
        rect, bracket_kind
    )


def build_shape_item_for(
    canvas, rect, shape_kind=None, stroke_style=None, *, fill=None
):
    return scene_decoration_build_service_for_access(canvas).build_shape_item(
        rect, shape_kind or "circle", stroke_style or "solid", fill=fill
    )


def build_orbital_items_for(canvas, center, kind: str):
    return scene_decoration_build_service_for_access(canvas).build_orbital_items(
        center, kind
    )


def add_arrow_head_for(canvas, path, start, end, double: bool) -> None:
    scene_decoration_build_service_for_access(canvas).add_arrow_head(
        path, start, end, double
    )


__all__ = [
    "add_arrow_head_for",
    "build_arrow_item_for",
    "build_orbital_items_for",
    "build_shape_item_for",
    "build_ts_bracket_item_for",
    "ts_bracket_path_for",
]
