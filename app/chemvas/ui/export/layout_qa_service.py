from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast, override

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPicture,
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

from chemvas.ui.annotations.arrows import ARROW_LABEL_ROLE
from chemvas.ui.canvas.graphics_items import note_paint_scene_path
from chemvas.ui.export.export_scope import EXPORT_EXCLUDED_KINDS, item_export_bounds
from chemvas.ui.export.layout_spatial import (
    MAX_INTERSECTION_COMPLEXITY,
    MAX_INTERSECTION_ELEMENTS,
    MAX_LAYOUT_WORK_UNITS,
    MAX_TOTAL_PATH_ELEMENTS,
    layout_limit,
    overlapping_bounds,
    validate_path,
)
from chemvas.ui.scene.scene_item_access import item_is_unavailable_for_scene_operation

if TYPE_CHECKING:
    from chemvas.ui.scene.scene_render_context import SceneRenderContext

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
    return check_scene_layout(canvas.render_context, sheet_only=sheet_only)


def check_scene_layout(
    context: SceneRenderContext, *, sheet_only: bool = False
) -> dict[str, object]:
    warnings = _sheet_boundary_warnings(context)
    if sheet_only:
        return _layout_report(warnings, sheet_only=True)
    entries = _collision_entries(context)
    candidates = []
    elements = 0
    complexity = 0
    for left, right in overlapping_bounds([entry.path for entry in entries]):
        rule = _collision_rule(entries[left], entries[right])
        if rule is None:
            continue
        candidates.append((left, right, rule))
        if len(candidates) > MAX_LAYOUT_WORK_UNITS:
            raise layout_limit(f"layout work limit of {MAX_LAYOUT_WORK_UNITS}")
        elements += (
            entries[left].path.elementCount() + entries[right].path.elementCount()
        )
        complexity += (
            entries[left].path.elementCount() * entries[right].path.elementCount()
        )
    # Complete broad-phase validation before allocating intersections or warnings.
    if elements > MAX_INTERSECTION_ELEMENTS:
        raise layout_limit(
            f"layout intersection limit of {MAX_INTERSECTION_ELEMENTS} path elements"
        )
    if complexity > MAX_INTERSECTION_COMPLEXITY:
        raise layout_limit(
            f"layout intersection-complexity limit of {MAX_INTERSECTION_COMPLEXITY}"
        )
    for left, right, (code, refs, message) in candidates:
        overlap = entries[left].path.intersected(entries[right].path)
        if _positive_path(overlap):
            warnings.append(_warning(code, refs, overlap.boundingRect(), message))
    return _layout_report(warnings, sheet_only=False)


@dataclass
class _CollisionEntry:
    ref: dict[str, object]
    path: QPainterPath


def _collision_entries(context: SceneRenderContext) -> list[_CollisionEntry]:
    entries: list[_CollisionEntry] = []
    total_elements = 0

    def add(ref: dict[str, object], path: QPainterPath) -> None:
        nonlocal total_elements
        validate_path(path)
        total_elements += path.elementCount()
        if total_elements > MAX_TOTAL_PATH_ELEMENTS:
            raise layout_limit(
                f"layout total-path limit of {MAX_TOTAL_PATH_ELEMENTS} elements"
            )
        if not path.isEmpty():
            entries.append(_CollisionEntry(ref, path))

    for atom_id, item in sorted(context.state.atom_graphics_state.atom_items.items()):
        if item.isVisible() and item.effectiveOpacity() > 0.0:
            add({"kind": "atom", "id": atom_id}, _atom_label_scene_path(item))
    for index, item in enumerate(context.state.scene_items("note_items")):
        if (
            not item_is_unavailable_for_scene_operation(item)
            and item.isVisible()
            and item.effectiveOpacity() > 0.0
        ):
            add({"kind": "note", "index": index}, note_paint_scene_path(item))
    arrows = [
        (index, item)
        for index, item in enumerate(context.state.scene_items("arrow_items"))
        if not item_is_unavailable_for_scene_operation(item)
    ]
    for index, arrow in arrows:
        for item in arrow.childItems():
            if item.data(0) != ARROW_LABEL_ROLE or not isinstance(
                item, QGraphicsTextItem
            ):
                continue
            if not item.isVisible() or item.effectiveOpacity() <= 0.0:
                continue
            side = item.data(1)
            if side not in {"above", "below"}:
                raise ValueError("Arrow label has no valid above/below side metadata.")
            add(
                {"kind": "arrow-label", "index": index, "side": side},
                note_paint_scene_path(item),
            )
    for atom_ids, path in _molecular_bond_paths(context):
        add({"kind": "bond", "atom_ids": atom_ids}, path)
    for index, item in enumerate(context.state.scene_items("mark_items")):
        if item_is_unavailable_for_scene_operation(item):
            continue
        metadata = item.data(1)
        if (
            isinstance(item, QGraphicsTextItem)
            and item.isVisible()
            and item.effectiveOpacity() > 0.0
            and isinstance(metadata, dict)
            and metadata.get("kind") in {"plus", "minus"}
            and type(metadata.get("atom_id")) is int
        ):
            add(
                {"kind": "mark", "index": index, "atom_id": metadata["atom_id"]},
                note_paint_scene_path(item),
            )
    for index, arrow in arrows:
        add({"kind": "arrow", "index": index}, _graphics_paint_scene_path(arrow))
    for index, item in enumerate(context.state.scene_items("shape_items")):
        if item_is_unavailable_for_scene_operation(item):
            continue
        border = _shape_border_scene_path(item)
        if border is not None:
            add({"kind": "shape", "index": index}, border)
    return entries


def _collision_rule(
    left: _CollisionEntry, right: _CollisionEntry
) -> tuple[str, list[dict[str, object]], str] | None:
    a, b = left.ref["kind"], right.ref["kind"]
    refs = [left.ref, right.ref]
    if a in {"atom", "note", "arrow-label"} and b in {"atom", "note", "arrow-label"}:
        message = (
            "Attached arrow label overlaps other text."
            if b == "arrow-label"
            else "Atom labels overlap."
            if a == b == "atom"
            else "Notes overlap."
            if a == b == "note"
            else "Atom label and note overlap."
        )
        return "text-text-overlap", refs, message
    if a == "atom" and b == "bond":
        if left.ref["id"] not in cast("list[int]", right.ref["atom_ids"]):
            return (
                "atom-bond-overlap",
                refs,
                "Atom label crosses a nonincident molecular bond.",
            )
    if a == "bond" and b == "mark":
        return (
            "charge-bond-overlap",
            refs[::-1],
            "Attached charge glyph crosses a molecular bond.",
        )
    if a in {"atom", "bond"} and b == "arrow":
        message = (
            "Arrow crosses an atom label."
            if a == "atom"
            else "Arrow crosses a molecular bond."
        )
        return "arrow-structure-overlap", refs[::-1], message
    if a == "arrow-label" and b in {"bond", "arrow", "shape"}:
        code = "text-shape-border-overlap" if b == "shape" else f"text-{b}-overlap"
        return code, refs, "Attached arrow label crosses painted geometry."
    if a == "note" and b == "shape":
        return "text-shape-border-overlap", refs, "Note text crosses a shape border."
    if a == "note" and b == "arrow":
        return "text-arrow-overlap", refs, "Note text crosses an arrow stroke."
    return None


def _layout_report(
    warnings: list[dict[str, object]], *, sheet_only: bool
) -> dict[str, object]:
    containment = (
        "Visible atoms, bonds, notes, marks, arrows and attached labels, "
        "shapes, TS brackets, orbitals, ring fills and full image rectangles outside the sheet."
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
                "Standalone note ink against arrow and line strokes.",
                "Attached arrow-label ink against molecular bonds and own or other arrow strokes.",
                "Notes and attached arrow-label ink against shape borders.",
                containment,
            ],
            "not_checked": [
                *unchecked,
                "Other collision pairs, including note-bond, bond-bond, arrow-arrow and charge-text pairs.",
                "Collisions involving images, TS brackets, orbitals, ring fills and other standalone marks.",
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


def _sheet_boundary_warnings(context: SceneRenderContext) -> list[dict[str, object]]:
    """Containment has no pairwise work and is shared by both check modes."""
    sheet = context.state.sheet_setup_state.rect.adjusted(
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

    for atom_id, item in sorted(context.state.atom_graphics_state.atom_items.items()):
        check(
            {"kind": "atom", "id": atom_id}, _sheet_item_bounds(item, atom_label=True)
        )
    for atom_id, item in sorted(context.state.atom_graphics_state.atom_dots.items()):
        check({"kind": "atom", "id": atom_id}, _sheet_item_bounds(item))
    for atom_ids, path in _molecular_bond_paths(context):
        check({"kind": "bond", "atom_ids": atom_ids}, path.boundingRect())
    for kind, items in (
        ("note", context.state.scene_items("note_items")),
        ("mark", context.state.scene_items("mark_items")),
        ("arrow", context.state.scene_items("arrow_items")),
        ("shape", context.state.scene_items("shape_items")),
        ("ts_bracket", context.state.scene_items("ts_bracket_items")),
        ("orbital", context.state.scene_items("orbital_items")),
        ("ring", context.state.scene_items("ring_items")),
        ("image", context.state.scene_items("image_items")),
    ):
        for index, item in enumerate(items):
            if item_is_unavailable_for_scene_operation(item):
                continue
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
    if item.data(0) == "image":
        # Preserve the entire original image area, including transparent margins.
        return item_export_bounds(item)
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


def _molecular_bond_paths(
    context: SceneRenderContext,
) -> list[tuple[list[int], QPainterPath]]:
    # A bond may have several painted pieces (parallel strokes, hashes, dots).
    # Report it once using stable document atom IDs, not its runtime slot.
    bond_paths = []
    for bond_id, items in sorted(context.state.bond_graphics_state.bond_items.items()):
        path = QPainterPath()
        for item in items:
            path = path.united(_graphics_paint_scene_path(item))
        bond = context.model.bond_for_id(bond_id)
        if bond is not None and not path.isEmpty():
            bond_paths.append((sorted((bond.a, bond.b)), path))
    return bond_paths


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
    if not item.isVisible() or item.effectiveOpacity() <= 0.0:
        return None
    pen = item.pen()
    if pen.style() == Qt.PenStyle.NoPen or pen.color().alpha() == 0:
        return None
    return item.mapToScene(_stroke_path(item.path(), pen))


def _stroke_path(path: QPainterPath, pen: Any) -> QPainterPath:
    if pen.style() == Qt.PenStyle.NoPen or pen.color().alpha() == 0:
        return QPainterPath()
    validate_path(path)
    stroker = QPainterPathStroker()
    stroker.setWidth(max(float(pen.widthF()), _GEOMETRY_EPSILON))
    stroker.setCapStyle(pen.capStyle())
    stroker.setJoinStyle(pen.joinStyle())
    dash_pattern = pen.dashPattern()
    if dash_pattern:
        # Bound dash expansion before Qt allocates the painted stroke.
        period = sum(dash_pattern) * max(float(pen.widthF()), _GEOMETRY_EPSILON)
        if period <= 0 or path.length() / period * len(dash_pattern) > 100_000:
            raise layout_limit(
                "layout dashed-stroke limit of 100000 segments", containment_only=False
            )
        stroker.setDashPattern(dash_pattern)
        stroker.setDashOffset(pen.dashOffset())
    painted = stroker.createStroke(path)
    validate_path(painted)
    return painted


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


__all__ = ["WARNING_CODES", "check_canvas_layout", "check_scene_layout"]
