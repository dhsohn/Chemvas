from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker, QTransform

from chemvas.features.export import item_export_bounds
from chemvas.ui.canvas_scene_items_state import note_items_for, shape_items_for
from chemvas.ui.sheet_setup_access import sheet_rect_for

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsTextItem

WARNING_CODES = (
    "outside-sheet",
    "text-shape-border-overlap",
    "text-text-overlap",
)
_GEOMETRY_EPSILON = 0.01
_SHEET_EPSILON = 0.01


def check_canvas_layout(canvas: Any) -> dict[str, object]:
    notes = []
    note_paths = []
    for index, item in enumerate(note_items_for(canvas)):
        if not item.isVisible() or item.effectiveOpacity() <= 0.0:
            continue
        path = _note_glyph_scene_path(item)
        if path.isEmpty():
            continue
        notes.append((index, item))
        note_paths.append((index, path))
    shapes = [
        (index, item)
        for index, item in enumerate(shape_items_for(canvas))
        if item.isVisible() and _has_visible_shape_paint(item)
    ]
    warnings: list[dict[str, object]] = []

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


def _has_visible_shape_paint(item: Any) -> bool:
    if item.opacity() <= 0.0:
        return False
    pen = item.pen()
    if pen.style() != Qt.PenStyle.NoPen and pen.color().alpha() > 0:
        return True
    brush = item.brush()
    return brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0


def _note_glyph_scene_path(item: QGraphicsTextItem) -> QPainterPath:
    """Use the shaped text that Qt paints, not its rectangular hit target."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    document = item.document()
    if document is None:
        return path
    # Force layout before reading block/run positions, including fresh notes.
    item.boundingRect()
    block = document.begin()
    while block.isValid():
        layout = block.layout()
        if layout is not None:
            fragment_iterator = block.begin()
            while not fragment_iterator.atEnd():
                fragment = fragment_iterator.fragment()
                brush = fragment.charFormat().foreground()
                color = (
                    item.defaultTextColor()
                    if brush.style() == Qt.BrushStyle.NoBrush
                    else brush.color()
                )
                if color.alpha() > 0:
                    runs = layout.glyphRuns(
                        fragment.position() - block.position(), fragment.length()
                    )
                    for run in runs:
                        font = run.rawFont()
                        for glyph, position in zip(
                            run.glyphIndexes(), run.positions(), strict=True
                        ):
                            offset = layout.position() + position
                            transform = QTransform.fromTranslate(offset.x(), offset.y())
                            path.addPath(transform.map(font.pathForGlyph(glyph)))
                fragment_iterator += 1
        block = block.next()
    return item.mapToScene(path)


def _shape_border_scene_path(item: Any) -> QPainterPath | None:
    pen = item.pen()
    if pen.style() == Qt.PenStyle.NoPen or pen.color().alpha() == 0:
        return None
    stroker = QPainterPathStroker()
    stroker.setWidth(max(float(pen.widthF()), _GEOMETRY_EPSILON))
    stroker.setCapStyle(pen.capStyle())
    stroker.setJoinStyle(pen.joinStyle())
    dash_pattern = pen.dashPattern()
    if dash_pattern:
        stroker.setDashPattern(dash_pattern)
        stroker.setDashOffset(pen.dashOffset())
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
