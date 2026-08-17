from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker

from chemvas.features.export import item_export_bounds
from chemvas.ui.canvas_scene_items_state import note_items_for, shape_items_for
from chemvas.ui.sheet_setup_access import sheet_rect_for

WARNING_CODES = (
    "outside-sheet",
    "text-shape-border-overlap",
    "text-text-overlap",
)
_GEOMETRY_EPSILON = 0.01
_SHEET_EPSILON = 0.01


def check_canvas_layout(canvas: Any) -> dict[str, object]:
    notes = [
        (index, item)
        for index, item in enumerate(note_items_for(canvas))
        if item.isVisible() and _has_visible_note_glyphs(item)
    ]
    shapes = [
        (index, item)
        for index, item in enumerate(shape_items_for(canvas))
        if item.isVisible()
    ]
    warnings: list[dict[str, object]] = []

    note_paths = [(index, _scene_shape(item)) for index, item in notes]
    for left_position, (left_index, left_path) in enumerate(note_paths):
        for right_index, right_path in note_paths[left_position + 1 :]:
            overlap = left_path.intersected(right_path)
            if not _positive_path(overlap):
                continue
            warnings.append(
                _warning(
                    "text-text-overlap",
                    [
                        {"kind": "note", "index": left_index},
                        {"kind": "note", "index": right_index},
                    ],
                    overlap.boundingRect(),
                    "Notes overlap.",
                )
            )

    for note_index, note_path in note_paths:
        for shape_index, shape in shapes:
            border = _shape_border_scene_path(shape)
            if border is None:
                continue
            overlap = note_path.intersected(border)
            if not _positive_path(overlap):
                continue
            warnings.append(
                _warning(
                    "text-shape-border-overlap",
                    [
                        {"kind": "note", "index": note_index},
                        {"kind": "shape", "index": shape_index},
                    ],
                    overlap.boundingRect(),
                    "Note text crosses a shape border.",
                )
            )

    sheet = sheet_rect_for(canvas).adjusted(
        -_SHEET_EPSILON,
        -_SHEET_EPSILON,
        _SHEET_EPSILON,
        _SHEET_EPSILON,
    )
    for kind, records in (("note", notes), ("shape", shapes)):
        for index, item in records:
            bounds = item_export_bounds(item)
            if sheet.contains(bounds):
                continue
            warnings.append(
                _warning(
                    "outside-sheet",
                    [{"kind": kind, "index": index}],
                    bounds,
                    f"{kind.capitalize()} extends outside the sheet.",
                )
            )

    warnings.sort(key=_warning_sort_key)
    counts = {code: 0 for code in WARNING_CODES}
    for warning in warnings:
        counts[str(warning["code"])] += 1
    return {
        "ok": not warnings,
        "warning_count": len(warnings),
        "counts": counts,
        "warnings": warnings,
    }


def _has_visible_note_glyphs(item: Any) -> bool:
    return bool(item.toPlainText().strip())


def _scene_shape(item: Any) -> QPainterPath:
    return item.mapToScene(item.shape())


def _shape_border_scene_path(item: Any) -> QPainterPath | None:
    pen = item.pen()
    if pen.style() == Qt.PenStyle.NoPen or pen.color().alpha() == 0:
        return None
    stroker = QPainterPathStroker()
    stroker.setWidth(max(float(pen.widthF()), _GEOMETRY_EPSILON))
    stroker.setCapStyle(pen.capStyle())
    stroker.setJoinStyle(pen.joinStyle())
    return item.mapToScene(stroker.createStroke(item.path()))


def _positive_path(path: QPainterPath) -> bool:
    bounds = path.boundingRect()
    return bounds.width() > _GEOMETRY_EPSILON and bounds.height() > _GEOMETRY_EPSILON


def _warning(
    code: str,
    items: list[dict[str, object]],
    bounds: QRectF,
    message: str,
) -> dict[str, object]:
    return {
        "code": code,
        "severity": "warning",
        "items": items,
        "bounds": [
            round(bounds.x(), 6),
            round(bounds.y(), 6),
            round(bounds.width(), 6),
            round(bounds.height(), 6),
        ],
        "message": message,
    }


def _warning_sort_key(warning: dict[str, object]) -> tuple[str, str]:
    return str(warning["code"]), repr(warning["items"])


__all__ = ["WARNING_CODES", "check_canvas_layout"]
