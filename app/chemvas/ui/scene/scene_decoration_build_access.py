from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.features.selection import HANDLE_ACCENT_COLOR
from chemvas.ui.canvas.graphics_items import NoSelectEllipseItem
from chemvas.ui.scene.scene_item_access import add_item_to_canvas_scene
from chemvas.ui.tools.endpoint_snap_access import (
    SNAP_MARK_SCREEN_PX,
    scene_length_for_screen_px,
    snapped_points_among_for,
)

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
    return canvas.services.arrow_build_service.build_arrow_item(
        start, end, kind, mirrored
    )


def show_connect_mark_for(canvas, point):
    """Put a standalone snap ring on the scene and return it."""
    mark = build_snap_mark_for(canvas, point)
    return add_item_to_canvas_scene(canvas, mark)


def mark_snapped_points_for(canvas, item, points) -> None:
    for point in snapped_points_among_for(canvas, points):
        build_snap_mark_for(canvas, point).setParentItem(item)


def ts_bracket_path_for(canvas, rect, bracket_kind: str = DEFAULT_BRACKET_KIND):
    return canvas.services.scene_decoration_build_service.ts_bracket_path(
        rect, bracket_kind
    )


def build_ts_bracket_item_for(canvas, rect, bracket_kind: str = DEFAULT_BRACKET_KIND):
    return canvas.services.scene_decoration_build_service.build_ts_bracket_item(
        rect, bracket_kind
    )


def build_shape_item_for(
    canvas, rect, shape_kind=None, stroke_style=None, *, fill=None
):
    return canvas.services.scene_decoration_build_service.build_shape_item(
        rect, shape_kind or "circle", stroke_style or "solid", fill=fill
    )


__all__ = [
    "build_arrow_item_for",
    "build_shape_item_for",
    "build_ts_bracket_item_for",
    "mark_snapped_points_for",
    "show_connect_mark_for",
    "ts_bracket_path_for",
]
