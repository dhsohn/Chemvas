from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from ui.bracket_types import restored_bracket_kind
from ui.note_html_sanitizer import sanitize_note_html
from ui.note_item_access import set_committed_note_html_for, set_committed_note_text_for
from ui.scene_item_state_serialization import (
    ARROW_KINDS,
    MarkCenterGetter,
    arrow_state_dict,
    arrow_state_dict_for,
    atom_state_dict_for,
    bond_state_dict,
    embedded_scene_item_state,
    mark_state_dict,
    mark_state_dict_for,
    note_state_dict,
    note_state_dict_for,
    orbital_state_dict,
    orbital_state_dict_for,
    ring_state_dict,
    ring_state_dict_for,
    scene_item_state,
    scene_item_state_for,
    shape_state_dict,
    shape_state_dict_for,
    ts_bracket_state_dict,
    ts_bracket_state_dict_for,
)
from ui.shape_geometry import normalized_shape_kind, normalized_stroke_style

MarkCenterSetter = Callable[[Any, QPointF], None]
NoteStyleApplier = Callable[[QGraphicsTextItem], None]
RingFillBrushGetter = Callable[[], QBrush]
TsBracketPathBuilder = Callable[..., Any]
ShapeItemBuilder = Callable[..., QGraphicsPathItem]
ArrowItemBuilder = Callable[[QPointF, QPointF, str], QGraphicsPathItem]
CurvedArrowPathSetter = Callable[[QGraphicsPathItem, QPointF, QPointF, QPointF, bool], None]


def _float_state_value(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def _point_from_state(value: object) -> QPointF | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = value
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return QPointF(float(x), float(y))


def _points_from_state(value: object) -> list[QPointF]:
    if not isinstance(value, (list, tuple)):
        return []
    points: list[QPointF] = []
    for point_value in value:
        point = _point_from_state(point_value)
        if point is not None:
            points.append(point)
    return points


def ts_bracket_rect_from_state(state: Mapping[str, object]) -> QRectF | None:
    rect = state.get("rect")
    if isinstance(rect, (list, tuple)) and len(rect) == 4:
        numeric_rect: list[float] = []
        for value in rect:
            if not isinstance(value, (int, float)):
                return None
            numeric_rect.append(float(value))
        x, y, width, height = numeric_rect
        return QRectF(float(x), float(y), float(width), float(height)).normalized()

    coords = (
        state.get("left"),
        state.get("top"),
        state.get("right"),
        state.get("bottom"),
    )
    numeric_coords: list[float] = []
    for value in coords:
        if not isinstance(value, (int, float)):
            return None
        numeric_coords.append(float(value))
    left, top, right, bottom = numeric_coords
    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()


def ts_bracket_kind_from_state(state: Mapping[str, object]) -> str:
    return restored_bracket_kind(state.get("bracket_kind"))


def shape_rect_from_state(state: Mapping[str, object]) -> QRectF | None:
    return ts_bracket_rect_from_state(state)


def shape_kind_from_state(state: Mapping[str, object]) -> str:
    return normalized_shape_kind(state.get("shape_kind"))


def shape_stroke_from_state(state: Mapping[str, object]) -> str:
    return normalized_stroke_style(state.get("stroke_style"))


def shape_fill_from_state(state: Mapping[str, object]) -> QColor | None:
    fill = state.get("fill")
    if not isinstance(fill, str) or not fill:
        return None
    color = QColor(fill)
    alpha = state.get("fill_alpha", 1.0)
    color.setAlphaF(float(alpha) if isinstance(alpha, (int, float)) else 1.0)
    return color


def _build_ts_bracket_path(builder: TsBracketPathBuilder, rect: QRectF, bracket_kind: str):
    try:
        return builder(rect, bracket_kind)
    except TypeError:
        return builder(rect)


def apply_scene_item_state(
    item,
    state: Mapping[str, object],
    *,
    model_atoms: Mapping[int, Any],
    note_style_applier: NoteStyleApplier,
    mark_center_setter: MarkCenterSetter,
    ring_fill_brush_getter: RingFillBrushGetter,
    ts_bracket_path_builder: TsBracketPathBuilder,
    bond_color: str,
    build_arrow_item: ArrowItemBuilder,
    set_curved_arrow_path: CurvedArrowPathSetter,
    orbital_base_handle_dist: float,
    build_shape_item: ShapeItemBuilder | None = None,
) -> None:
    if item is None or not state:
        return
    kind = state.get("kind")
    if kind == "note" and isinstance(item, QGraphicsTextItem):
        html = sanitize_note_html(state.get("html"))
        if html is not None:
            item.setHtml(html)
        else:
            item.setPlainText(str(state.get("text", "")))
        set_committed_note_text_for(item, item.toPlainText())
        set_committed_note_html_for(item, item.toHtml())
        item.setPos(QPointF(_float_state_value(state.get("x"), 0.0), _float_state_value(state.get("y"), 0.0)))
        note_style_applier(item)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        return
    if kind == "mark":
        if isinstance(item, QGraphicsTextItem):
            text = state.get("text")
            if text is not None:
                item.setPlainText(str(text))
        data = item.data(1) or {}
        data.update(
            {
                "kind": state.get("mark_kind", data.get("kind")),
                "atom_id": state.get("atom_id"),
                "dx": state.get("dx"),
                "dy": state.get("dy"),
                "text": state.get("text"),
            }
        )
        item.setData(1, data)
        center = mark_center_from_state(state, model_atoms)
        if center is not None:
            mark_center_setter(item, center)
        return
    if kind == "ring" and isinstance(item, QGraphicsPolygonItem):
        points = _points_from_state(state.get("points"))
        if len(points) >= 3:
            item.setPolygon(QPolygonF(points))
        color = state.get("color")
        alpha = state.get("alpha", 0.0)
        if color:
            fill = QColor(str(color))
            fill.setAlphaF(float(alpha) if isinstance(alpha, (int, float)) else 0.0)
            item.setBrush(fill)
        else:
            item.setBrush(ring_fill_brush_getter())
        return
    if kind == "ts_bracket" and isinstance(item, QGraphicsPathItem):
        rect = ts_bracket_rect_from_state(state)
        if rect is None:
            return
        bracket_kind = ts_bracket_kind_from_state(state)
        # The rect is in scene coordinates, so the rebuilt path is absolute.
        # Clear any translation left by a prior drag/nudge (move_item shifts
        # item.pos() via moveBy) or the item would render double-offset.
        item.setPos(0.0, 0.0)
        item.setPath(_build_ts_bracket_path(ts_bracket_path_builder, rect, bracket_kind))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(bond_color)))
        item.setData(1, {"rect": QRectF(rect), "bracket_kind": bracket_kind})
        return
    if kind == "shape" and isinstance(item, QGraphicsPathItem):
        if build_shape_item is None:
            return
        rect = shape_rect_from_state(state)
        if rect is None:
            return
        shape_kind = shape_kind_from_state(state)
        stroke_style = shape_stroke_from_state(state)
        rebuilt = build_shape_item(rect, shape_kind, stroke_style, shape_fill_from_state(state))
        item.setPath(rebuilt.path())
        item.setPen(rebuilt.pen())
        item.setBrush(rebuilt.brush())
        item.setData(0, "shape")
        item.setData(1, {"rect": QRectF(rect), "shape_kind": shape_kind, "stroke_style": stroke_style})
        return
    if kind == "orbital" and isinstance(item, QGraphicsItemGroup):
        center_point = _point_from_state(state.get("center"))
        if center_point is not None:
            previous = item.data(1) or {}
            old_center = previous.get("center")
            if isinstance(old_center, QPointF):
                # The lobe geometry does not rebuild on apply, so translate the
                # group to follow the new absolute center (flip/rotate/restore
                # only change metadata otherwise, leaving the glyph behind).
                item.moveBy(center_point.x() - old_center.x(), center_point.y() - old_center.y())
            item.setData(1, {"center": center_point, "base_handle_dist": orbital_base_handle_dist})
            # Transform origin is item-local: the lobes sit around center - pos,
            # so rotation still pivots about the true lobe center after a move.
            item.setTransformOriginPoint(
                QPointF(center_point.x() - item.pos().x(), center_point.y() - item.pos().y())
            )
        item.setScale(_float_state_value(state.get("scale"), item.scale()))
        item.setRotation(_float_state_value(state.get("rotation"), item.rotation()))
        return
    if kind in ARROW_KINDS and isinstance(item, QGraphicsPathItem):
        start_pt = _point_from_state(state.get("start"))
        end_pt = _point_from_state(state.get("end"))
        if start_pt is None or end_pt is None:
            return
        # start/end are scene coordinates, so the rebuilt path is absolute.
        # Clear any translation left by a prior drag/nudge (move_item shifts
        # item.pos() via moveBy) or the arrow would render double-offset.
        item.setPos(0.0, 0.0)
        control_pt = _point_from_state(state.get("control"))
        double = bool(state.get("double", False))
        if kind in {"curved_single", "curved_double"} and control_pt is not None:
            set_curved_arrow_path(item, start_pt, end_pt, control_pt, double)
            data = {"start": start_pt, "end": end_pt, "control": control_pt, "double": double}
        else:
            rebuilt = build_arrow_item(start_pt, end_pt, str(kind))
            item.setPath(rebuilt.path())
            item.setPen(rebuilt.pen())
            item.setBrush(rebuilt.brush())
            data = {"start": start_pt, "end": end_pt, "control": None, "double": double}
        item.setData(0, kind)
        item.setData(2, data)


def mark_center_from_state(state: Mapping[str, object], model_atoms: Mapping[int, Any]) -> QPointF | None:
    center = None
    atom_id = state.get("atom_id")
    dx = state.get("dx")
    dy = state.get("dy")
    if isinstance(atom_id, int) and atom_id in model_atoms:
        atom = model_atoms[atom_id]
        if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
            center = QPointF(atom.x + dx, atom.y + dy)
    if center is None:
        x = state.get("x")
        y = state.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            center = QPointF(float(x), float(y))
    return center


__all__ = [
    "ARROW_KINDS",
    "MarkCenterGetter",
    "apply_scene_item_state",
    "arrow_state_dict",
    "arrow_state_dict_for",
    "atom_state_dict_for",
    "bond_state_dict",
    "embedded_scene_item_state",
    "mark_center_from_state",
    "mark_state_dict",
    "mark_state_dict_for",
    "note_state_dict",
    "note_state_dict_for",
    "orbital_state_dict",
    "orbital_state_dict_for",
    "ring_state_dict",
    "ring_state_dict_for",
    "scene_item_state",
    "scene_item_state_for",
    "shape_fill_from_state",
    "shape_kind_from_state",
    "shape_rect_from_state",
    "shape_state_dict",
    "shape_state_dict_for",
    "shape_stroke_from_state",
    "ts_bracket_kind_from_state",
    "ts_bracket_rect_from_state",
    "ts_bracket_state_dict",
    "ts_bracket_state_dict_for",
]
