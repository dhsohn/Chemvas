from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.features.selection import HANDLE_ACCENT_COLOR
from chemvas.ui.canvas_service_ports import (
    arrow_build_service_for_access,
    scene_decoration_build_service_for_access,
)
from chemvas.ui.endpoint_snap_access import (
    SNAP_MARK_SCREEN_PX,
    scene_length_for_screen_px,
    snapped_points_among_for,
)
from chemvas.ui.graphics_items import NoSelectEllipseItem
from chemvas.ui.scene_item_access import add_item_to_canvas_scene

SNAP_MARK_ROLE = "snap_mark"


def build_snap_mark_for(canvas, point):
    radius = scene_length_for_screen_px(canvas, SNAP_MARK_SCREEN_PX) / 2.0
    mark = NoSelectEllipseItem(
        point.x() - radius, point.y() - radius, radius * 2, radius * 2
    )
    pen = QPen(QColor(HANDLE_ACCENT_COLOR))
    pen.setWidthF(1.6)
    pen.setCosmetic(True)
    mark.setPen(pen)
    mark.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    mark.setData(0, SNAP_MARK_ROLE)
    return mark


def build_arrow_item_for(canvas, start, end, kind: str, mirrored: bool = False):
    return arrow_build_service_for_access(canvas).build_arrow_item(
        start, end, kind, mirrored
    )


def show_connect_mark_for(canvas, point):
    """Put a standalone snap ring on the scene and return it."""
    mark = build_snap_mark_for(canvas, point)
    return add_item_to_canvas_scene(canvas, mark)


def mark_snapped_points_for(canvas, item, points) -> None:
    for point in snapped_points_among_for(canvas, points):
        build_snap_mark_for(canvas, point).setParentItem(item)


def apply_arrow_labels_for(canvas, item, labels) -> None:
    arrow_build_service_for_access(canvas).apply_arrow_labels(item, labels)


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


def shape_pen_for(canvas, stroke_style: str):
    return scene_decoration_build_service_for_access(canvas).shape_pen(stroke_style)


def build_orbital_items_for(canvas, center, kind: str):
    return scene_decoration_build_service_for_access(canvas).build_orbital_items(
        center, kind
    )


def build_curved_arrow_path_for(canvas, start, end, control, double: bool):
    return arrow_build_service_for_access(canvas).build_curved_arrow_path(
        start, end, control, double
    )


__all__ = [
    "apply_arrow_labels_for",
    "build_arrow_item_for",
    "build_curved_arrow_path_for",
    "build_orbital_items_for",
    "build_shape_item_for",
    "build_ts_bracket_item_for",
    "mark_snapped_points_for",
    "show_connect_mark_for",
    "ts_bracket_path_for",
]
