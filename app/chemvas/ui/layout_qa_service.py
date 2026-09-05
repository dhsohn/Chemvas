from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QPainterPath,
    QPainterPathStroker,
    QTextCharFormat,
    QTextCursor,
    QTransform,
)

from chemvas.features.export import item_export_bounds
from chemvas.ui.canvas_scene_items_state import note_items_for, shape_items_for
from chemvas.ui.sheet_setup_access import sheet_rect_for

if TYPE_CHECKING:
    from PyQt6.QtGui import QRawFont, QTextBlock, QTextFragment
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
        path = _note_paint_scene_path(item)
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


def _note_paint_scene_path(item: QGraphicsTextItem) -> QPainterPath:
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
            background = block.blockFormat().background()
            if (
                background.style() != Qt.BrushStyle.NoBrush
                and background.color().alpha()
            ):
                document_layout = document.documentLayout()
                assert document_layout is not None
                bounds = document_layout.blockBoundingRect(block)
                frame = document.rootFrame()
                if (
                    frame is not None
                    and QTextCursor(block).currentFrame() == frame
                    and document.pageSize().width() <= 0
                ):
                    bounds.setRight(
                        document_layout.frameBoundingRect(frame).right()
                        - frame.frameFormat().rightMargin()
                    )
                path.addRect(bounds)
            fragment_iterator = block.begin()
            while not fragment_iterator.atEnd():
                fragment = fragment_iterator.fragment()
                brush = fragment.charFormat().foreground()
                color = (
                    item.defaultTextColor()
                    if brush.style() == Qt.BrushStyle.NoBrush
                    else brush.color()
                )
                path.addPath(
                    _fragment_decoration_path(block, fragment, color.alpha() > 0)
                )
                if color.alpha() > 0:
                    runs = layout.glyphRuns(
                        fragment.position() - block.position(), fragment.length()
                    )
                    for run in runs:
                        font = run.rawFont()
                        baseline_shift = _fragment_baseline_shift(
                            fragment.charFormat(), font
                        )
                        for glyph, position in zip(
                            run.glyphIndexes(), run.positions(), strict=True
                        ):
                            offset = layout.position() + position
                            transform = QTransform.fromTranslate(
                                offset.x(), offset.y() + baseline_shift
                            )
                            path.addPath(transform.map(font.pathForGlyph(glyph)))
                fragment_iterator += 1
        block = block.next()
    return item.mapToScene(path)


def _fragment_baseline_shift(format_: QTextCharFormat, font: QRawFont) -> float:
    height = font.ascent() + font.descent()
    if (
        format_.verticalAlignment()
        == QTextCharFormat.VerticalAlignment.AlignSuperScript
    ):
        return -height * format_.superScriptBaseline() / 100
    if format_.verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSubScript:
        return height * format_.subScriptBaseline() / 100
    return 0.0


def _fragment_decoration_path(
    block: QTextBlock, fragment: QTextFragment, visible_text: bool
) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    format_ = fragment.charFormat()
    background = format_.background()
    visible_background = (
        background.style() != Qt.BrushStyle.NoBrush and background.color().alpha() > 0
    )
    if not visible_background and not visible_text:
        return path
    layout = block.layout()
    assert layout is not None
    start = fragment.position() - block.position()
    end = start + fragment.length()
    for index in range(layout.lineCount()):
        line = layout.lineAt(index)
        first = max(start, line.textStart())
        last = min(end, line.textStart() + line.textLength())
        if first >= last:
            continue
        top = layout.position().y() + line.y()
        # Visual runs preserve bidi gaps and omit trailing wrap whitespace.
        for run in line.glyphRuns(first, last - first):
            bounds = run.boundingRect()
            left = layout.position().x() + bounds.left()
            right = layout.position().x() + bounds.right()
            if visible_background:
                path.addRect(QRectF(left, top, right - left, line.height()))
            if not visible_text:
                continue
            font = run.rawFont()
            thickness = font.lineThickness()
            offsets = []
            if run.underline():
                offset = math.ceil(font.underlinePosition()) + thickness / 2
                if font.underlinePosition() <= font.descent():
                    offset = min(offset, font.descent() - thickness / 2)
                offsets.append(offset)
            if run.overline():
                offsets.append(-font.ascent())
            if run.strikeOut():
                offsets.append(-font.ascent() / 3)
            baseline = top + line.ascent() + _fragment_baseline_shift(format_, font)
            for offset in offsets:
                path.addRect(
                    QRectF(
                        math.floor(left),
                        baseline + offset - thickness / 2,
                        math.floor(right) - math.floor(left),
                        thickness,
                    )
                )
    return path


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
