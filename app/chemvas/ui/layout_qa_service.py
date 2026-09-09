from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, override

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPicture,
    QTextCharFormat,
    QTextCursor,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
)

from chemvas.features.export import EXPORT_EXCLUDED_KINDS, item_export_bounds
from chemvas.ui.canvas_arrow_build_service import ARROW_LABEL_ROLE
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_model_access import bond_for_id
from chemvas.ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    shape_items_for,
    ts_bracket_items_for,
)
from chemvas.ui.sheet_setup_access import sheet_rect_for

if TYPE_CHECKING:
    from PyQt6.QtGui import QRawFont, QTextBlock, QTextFragment

WARNING_CODES = (
    "arrow-structure-overlap",
    "atom-bond-overlap",
    "charge-bond-overlap",
    "outside-sheet",
    "text-arrow-overlap",
    "text-bond-overlap",
    "text-shape-border-overlap",
    "text-text-overlap",
)
_GEOMETRY_EPSILON = 0.01
_SHEET_EPSILON = 0.01


def check_canvas_layout(canvas: Any, *, sheet_only: bool = False) -> dict[str, object]:
    warnings = _sheet_boundary_warnings(canvas)
    if sheet_only:
        return _layout_report(warnings, sheet_only=True)
    notes = []
    note_paths = []
    for index, item in enumerate(note_items_for(canvas)):
        if not item.isVisible() or item.effectiveOpacity() <= 0.0:
            continue
        path = note_paint_scene_path(item)
        if path.isEmpty():
            continue
        notes.append((index, item))
        note_paths.append((index, path))
    shapes = [
        (index, item)
        for index, item in enumerate(shape_items_for(canvas))
        if item.isVisible() and _has_visible_shape_paint(item)
    ]
    atom_paths = []
    for atom_id, item in sorted(atom_items_for(canvas).items()):
        if not item.isVisible() or item.effectiveOpacity() <= 0.0:
            continue
        path = _atom_label_scene_path(item)
        if not path.isEmpty():
            atom_paths.append((atom_id, path))
    for left_position, (left_id, left_path) in enumerate(atom_paths):
        for right_id, right_path in atom_paths[left_position + 1 :]:
            overlap = left_path.intersected(right_path)
            if _positive_path(overlap):
                warnings.append(
                    _warning(
                        "text-text-overlap",
                        [
                            {"kind": "atom", "id": left_id},
                            {"kind": "atom", "id": right_id},
                        ],
                        overlap.boundingRect(),
                        "Atom labels overlap.",
                    )
                )

    for atom_id, atom_path in atom_paths:
        for note_index, note_path in note_paths:
            overlap = atom_path.intersected(note_path)
            if _positive_path(overlap):
                warnings.append(
                    _warning(
                        "text-text-overlap",
                        [
                            {"kind": "atom", "id": atom_id},
                            {"kind": "note", "index": note_index},
                        ],
                        overlap.boundingRect(),
                        "Atom label and note overlap.",
                    )
                )

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

    bond_paths = (
        _molecular_bond_paths(canvas)
        if atom_paths or arrow_items_for(canvas) or mark_items_for(canvas)
        else []
    )
    warnings.extend(_molecular_text_bond_warnings(canvas, atom_paths, bond_paths))
    warnings.extend(_arrow_structure_warnings(canvas, atom_paths, bond_paths))

    warnings.extend(
        _arrow_label_warnings(canvas, atom_paths, note_paths, bond_paths, shapes)
    )
    return _layout_report(warnings, sheet_only=False)


def _layout_report(
    warnings: list[dict[str, object]], *, sheet_only: bool
) -> dict[str, object]:
    containment = (
        "Visible atoms, bonds, notes, marks, arrows and attached labels, "
        "shapes, TS brackets, orbitals and ring fills outside the sheet."
    )
    unchecked = [
        "Aesthetic quality, semantic label ownership, chemical correctness or stereochemical meaning.",
        "Final print-size readability; use the export readability guard separately.",
    ]
    if sheet_only:
        coverage = {
            "ok_meaning": "No visible content outside the sheet; collisions were not checked.",
            "checked": [containment],
            "not_checked": [*unchecked, "All collision checks (--sheet-only)."],
        }
    else:
        coverage = {
            "ok_meaning": "No warnings in the checked collision and sheet-boundary classes.",
            "checked": [
                "Visible atom, note and attached arrow-label ink pairs.",
                "Atom labels against nonincident molecular bonds; attached charges against all molecular bonds.",
                "Arrow strokes against atom labels and molecular bonds.",
                "Attached arrow-label ink against molecular bonds and own or other arrow strokes.",
                "Notes and attached arrow-label ink against shape borders.",
                containment,
            ],
            "not_checked": [
                *unchecked,
                "Other collision pairs, including note-bond, note-arrow, bond-bond, arrow-arrow and charge-text pairs.",
                "Collisions involving TS brackets, orbitals, ring fills and other standalone marks.",
                "Automatic list markers outside the collected text glyph runs in collision checks.",
            ],
        }

    warnings.sort(key=_warning_sort_key)
    counts = {code: 0 for code in (("outside-sheet",) if sheet_only else WARNING_CODES)}
    for warning in warnings:
        counts[str(warning["code"])] += 1
    return {
        "ok": not warnings,
        "warning_count": len(warnings),
        "counts": counts,
        "warnings": warnings,
        "coverage": coverage,
    }


def _sheet_boundary_warnings(canvas: Any) -> list[dict[str, object]]:
    """Containment has no pairwise work and is shared by both check modes."""
    sheet = sheet_rect_for(canvas).adjusted(
        -_SHEET_EPSILON, -_SHEET_EPSILON, _SHEET_EPSILON, _SHEET_EPSILON
    )
    warnings: list[dict[str, object]] = []

    def check(ref: dict[str, object], bounds: QRectF | None) -> None:
        if bounds is None or bounds.isNull():
            return
        if not all(math.isfinite(v) for v in bounds.getRect()):
            raise ValueError("Cannot measure non-finite native content bounds.")
        if not sheet.contains(bounds):
            warnings.append(
                _warning(
                    "outside-sheet",
                    [ref],
                    bounds,
                    "Visible content extends outside the sheet.",
                )
            )

    for atom_id, item in sorted(atom_items_for(canvas).items()):
        check(
            {"kind": "atom", "id": atom_id}, _sheet_item_bounds(item, atom_label=True)
        )
    for atom_id, item in sorted(atom_dots_for(canvas).items()):
        check({"kind": "atom", "id": atom_id}, _sheet_item_bounds(item))
    for atom_ids, path in _molecular_bond_paths(canvas):
        check({"kind": "bond", "atom_ids": atom_ids}, path.boundingRect())
    for kind, items in (
        ("note", note_items_for(canvas)),
        ("mark", mark_items_for(canvas)),
        ("arrow", arrow_items_for(canvas)),
        ("shape", shape_items_for(canvas)),
        ("ts_bracket", ts_bracket_items_for(canvas)),
        ("orbital", orbital_items_for(canvas)),
        ("ring", ring_items_for(canvas)),
    ):
        for index, item in enumerate(items):
            ref: dict[str, object] = {"kind": kind, "index": index}
            check(ref, _sheet_item_bounds(item))
            if kind == "arrow":
                for child in item.childItems():
                    if child.data(0) != ARROW_LABEL_ROLE:
                        continue
                    side = child.data(1)
                    if side not in {"above", "below"}:
                        raise ValueError(
                            "Arrow label has no valid above/below side metadata."
                        )
                    check(
                        {"kind": "arrow-label", "index": index, "side": side},
                        _sheet_item_bounds(child),
                    )
    return warnings


def _sheet_item_bounds(item: Any, *, atom_label: bool = False) -> QRectF | None:
    if not item.isVisible() or item.effectiveOpacity() <= 0.0:
        return None
    if isinstance(item, QGraphicsTextItem):
        path = (
            _atom_label_scene_path(item) if atom_label else note_paint_scene_path(item)
        )
        # Keep native text/export bounds, excluding the atom-label hit halo.
        # Notes retain their editable text box, including native list indentation.
        if path.isEmpty() and not _has_visible_list_marker(item):
            return None
        bounds = item_export_bounds(item)
        # Italic bearings and scripts can paint beyond Qt's text box.
        return bounds if path.isEmpty() else bounds.united(path.boundingRect())
    bounds = QRectF()
    if not isinstance(item, QGraphicsItemGroup):
        bounds = _graphics_paint_scene_path(item).boundingRect()
    for child in item.childItems():
        if child.data(0) in EXPORT_EXCLUDED_KINDS or child.data(0) == ARROW_LABEL_ROLE:
            continue
        child_bounds = _sheet_item_bounds(child)
        if child_bounds is not None:
            bounds = child_bounds if bounds.isNull() else bounds.united(child_bounds)
    return None if bounds.isNull() else bounds


def _has_visible_list_marker(item: QGraphicsTextItem) -> bool:
    # Qt paints list markers outside glyphRuns(), including empty list items.
    # Use its block formatting; do not reconstruct marker glyphs or positions.
    document = item.document()
    assert document is not None
    block = document.begin()
    while block.isValid():
        text_list = block.textList()
        if text_list is not None:
            brush = block.charFormat().foreground()
            color = (
                item.defaultTextColor()
                if brush.style() == Qt.BrushStyle.NoBrush
                else brush.color()
            )
            if color.alpha() > 0:
                return True
        block = block.next()
    return False


def _arrow_label_warnings(
    canvas: Any,
    atom_paths: list[tuple[int, QPainterPath]],
    note_paths: list[tuple[int, QPainterPath]],
    bond_paths: list[tuple[list[int], QPainterPath]],
    shapes: list[tuple[int, Any]],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    text_paths: list[tuple[dict[str, object], QPainterPath]] = [
        ({"kind": "atom", "id": atom_id}, path) for atom_id, path in atom_paths
    ] + [({"kind": "note", "index": index}, path) for index, path in note_paths]
    targets: list[tuple[str, dict[str, object], QPainterPath]] = [
        ("text-bond-overlap", {"kind": "bond", "atom_ids": ids}, path)
        for ids, path in bond_paths
    ]
    targets.extend(
        (
            "text-arrow-overlap",
            {"kind": "arrow", "index": index},
            _graphics_paint_scene_path(arrow),
        )
        for index, arrow in enumerate(arrow_items_for(canvas))
    )
    targets.extend(
        ("text-shape-border-overlap", {"kind": "shape", "index": index}, path)
        for index, shape in shapes
        if (path := _shape_border_scene_path(shape)) is not None
    )
    for index, arrow in enumerate(arrow_items_for(canvas)):
        for item in arrow.childItems():
            if (
                item.data(0) != ARROW_LABEL_ROLE
                or not isinstance(item, QGraphicsTextItem)
                or not item.isVisible()
                or item.effectiveOpacity() <= 0.0
            ):
                continue
            side = item.data(1)
            if side not in {"above", "below"}:
                raise ValueError("Arrow label has no valid above/below side metadata.")
            label_path = note_paint_scene_path(item)
            if label_path.isEmpty():
                continue
            ref = {"kind": "arrow-label", "index": index, "side": side}
            # Previously visited labels join the text list, so every pair is
            # checked once without comparing all scene items indiscriminately.
            for other_ref, path in text_paths:
                overlap = label_path.intersected(path)
                if _positive_path(overlap):
                    warnings.append(
                        _warning(
                            "text-text-overlap",
                            [other_ref, ref],
                            overlap.boundingRect(),
                            "Attached arrow label overlaps other text.",
                        )
                    )
            for code, other_ref, path in targets:
                overlap = label_path.intersected(path)
                if _positive_path(overlap):
                    warnings.append(
                        _warning(
                            code,
                            [ref, other_ref],
                            overlap.boundingRect(),
                            "Attached arrow label crosses painted geometry.",
                        )
                    )
            text_paths.append((ref, label_path))
    return warnings


def _molecular_bond_paths(canvas: Any) -> list[tuple[list[int], QPainterPath]]:
    # A bond may have several painted pieces (parallel strokes, hashes, dots).
    # Report it once using stable document atom IDs, not its runtime slot.
    bond_paths = []
    for bond_id, items in sorted(bond_items_for(canvas).items()):
        path = QPainterPath()
        for item in items:
            path = path.united(_graphics_paint_scene_path(item))
        bond = bond_for_id(canvas, bond_id)
        if bond is not None and not path.isEmpty():
            bond_paths.append((sorted((bond.a, bond.b)), path))
    return bond_paths


def _molecular_text_bond_warnings(
    canvas: Any,
    atom_paths: list[tuple[int, QPainterPath]],
    bond_paths: list[tuple[list[int], QPainterPath]],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for atom_id, atom_path in atom_paths:
        for atom_ids, bond_path in bond_paths:
            if atom_id in atom_ids:
                continue
            overlap = atom_path.intersected(bond_path)
            if _positive_path(overlap):
                warnings.append(
                    _warning(
                        "atom-bond-overlap",
                        [
                            {"kind": "atom", "id": atom_id},
                            {"kind": "bond", "atom_ids": atom_ids},
                        ],
                        overlap.boundingRect(),
                        "Atom label crosses a nonincident molecular bond.",
                    )
                )
    for index, item in enumerate(mark_items_for(canvas)):
        metadata = item.data(1)
        if (
            not isinstance(item, QGraphicsTextItem)
            or not isinstance(metadata, dict)
            or metadata.get("kind") not in {"plus", "minus"}
            or type(metadata.get("atom_id")) is not int
            or not item.isVisible()
            or item.effectiveOpacity() <= 0.0
        ):
            continue
        charge_path = note_paint_scene_path(item)
        for atom_ids, bond_path in bond_paths:
            overlap = charge_path.intersected(bond_path)
            if _positive_path(overlap):
                warnings.append(
                    _warning(
                        "charge-bond-overlap",
                        [
                            {
                                "kind": "mark",
                                "index": index,
                                "atom_id": metadata["atom_id"],
                            },
                            {"kind": "bond", "atom_ids": atom_ids},
                        ],
                        overlap.boundingRect(),
                        "Attached charge glyph crosses a molecular bond.",
                    )
                )
    return warnings


def _arrow_structure_warnings(
    canvas: Any,
    atom_paths: list[tuple[int, QPainterPath]],
    bond_paths: list[tuple[list[int], QPainterPath]],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for arrow_index, arrow in enumerate(arrow_items_for(canvas)):
        arrow_path = _graphics_paint_scene_path(arrow)
        for atom_id, atom_path in atom_paths:
            overlap = arrow_path.intersected(atom_path)
            if _positive_path(overlap):
                warnings.append(
                    _warning(
                        "arrow-structure-overlap",
                        [
                            {"kind": "arrow", "index": arrow_index},
                            {"kind": "atom", "id": atom_id},
                        ],
                        overlap.boundingRect(),
                        "Arrow crosses an atom label.",
                    )
                )
        for atom_ids, bond_path in bond_paths:
            overlap = arrow_path.intersected(bond_path)
            if _positive_path(overlap):
                warnings.append(
                    _warning(
                        "arrow-structure-overlap",
                        [
                            {"kind": "arrow", "index": arrow_index},
                            {"kind": "bond", "atom_ids": atom_ids},
                        ],
                        overlap.boundingRect(),
                        "Arrow crosses a molecular bond.",
                    )
                )

    return warnings


class _AtomLabelPainter(QPainter):
    """Collect custom label paint runs without duplicating their layout rules."""

    def __init__(self, picture: QPicture) -> None:
        super().__init__(picture)
        self.text_path: QPainterPath | None = None

    @override
    def drawText(self, *args: Any) -> Any:
        point, text = args
        if self.text_path is None:
            self.text_path = QPainterPath()
            self.text_path.setFillRule(Qt.FillRule.WindingFill)
        if self.pen().color().alpha() > 0:
            self.text_path.addText(point, self.font(), text)

    @override
    def drawPath(self, path: QPainterPath) -> None:
        self.text_path = QPainterPath()
        if self.brush().color().alpha() > 0:
            self.text_path.addPath(path)


def _atom_label_scene_path(item: QGraphicsTextItem) -> QPainterPath:
    # The public paint entrypoint supplies positioned subscript/stacked runs.
    # Plain labels paint through Qt's C++ text engine instead; use its shaped
    # document glyphs just as for notes. Neither path includes the hit target.
    picture = QPicture()
    painter = _AtomLabelPainter(picture)
    try:
        item.paint(painter, QStyleOptionGraphicsItem(), None)
    finally:
        painter.end()
    if painter.text_path is not None:
        return item.mapToScene(painter.text_path)
    return note_paint_scene_path(item)


def _has_visible_shape_paint(item: Any) -> bool:
    if item.opacity() <= 0.0:
        return False
    pen = item.pen()
    if pen.style() != Qt.PenStyle.NoPen and pen.color().alpha() > 0:
        return True
    brush = item.brush()
    return brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0


def note_paint_scene_path(item: QGraphicsTextItem) -> QPainterPath:
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
    layout = block.layout()
    assert layout is not None
    format_font = format_.font().resolve(layout.font())
    if not visible_background and (
        not visible_text
        or not (
            format_font.underline() or format_font.overline() or format_font.strikeOut()
        )
    ):
        return path
    start = fragment.position() - block.position()
    end = start + fragment.length()
    first_line = layout.lineForTextPosition(start).lineNumber()
    last_line = layout.lineForTextPosition(end - 1).lineNumber()
    for index in range(first_line, last_line + 1):
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


def _graphics_paint_scene_path(item: Any) -> QPainterPath:
    if not item.isVisible() or item.effectiveOpacity() <= 0.0:
        return QPainterPath()
    if isinstance(item, QGraphicsLineItem):
        path = QPainterPath(item.line().p1())
        path.lineTo(item.line().p2())
    elif isinstance(item, QGraphicsPolygonItem):
        path = QPainterPath()
        path.setFillRule(item.fillRule())
        path.addPolygon(item.polygon())
        path.closeSubpath()
    elif isinstance(item, QGraphicsEllipseItem):
        path = QPainterPath()
        path.addEllipse(item.rect())
    elif isinstance(item, QGraphicsRectItem):
        path = QPainterPath()
        path.addRect(item.rect())
    else:
        path = item.path()
    painted = _stroke_path(path, item.pen())
    if not isinstance(item, QGraphicsLineItem):
        brush = item.brush()
        if brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0:
            painted = painted.united(path)
    return item.mapToScene(painted)


def _shape_border_scene_path(item: Any) -> QPainterPath | None:
    pen = item.pen()
    if pen.style() == Qt.PenStyle.NoPen or pen.color().alpha() == 0:
        return None
    return item.mapToScene(_stroke_path(item.path(), pen))


def _stroke_path(path: QPainterPath, pen: Any) -> QPainterPath:
    if pen.style() == Qt.PenStyle.NoPen or pen.color().alpha() == 0:
        return QPainterPath()
    stroker = QPainterPathStroker()
    stroker.setWidth(max(float(pen.widthF()), _GEOMETRY_EPSILON))
    stroker.setCapStyle(pen.capStyle())
    stroker.setJoinStyle(pen.joinStyle())
    dash_pattern = pen.dashPattern()
    if dash_pattern:
        stroker.setDashPattern(dash_pattern)
        stroker.setDashOffset(pen.dashOffset())
    return stroker.createStroke(path)


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


__all__ = ["WARNING_CODES", "check_canvas_layout", "note_paint_scene_path"]
