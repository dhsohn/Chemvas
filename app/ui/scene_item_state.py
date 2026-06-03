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

MarkCenterGetter = Callable[[Any], QPointF]
MarkCenterSetter = Callable[[Any, QPointF], None]
NoteStyleApplier = Callable[[QGraphicsTextItem], None]
RingFillBrushGetter = Callable[[], QBrush]
TsBracketPathBuilder = Callable[[QRectF], Any]
ArrowItemBuilder = Callable[[QPointF, QPointF, str], QGraphicsPathItem]
CurvedArrowPathSetter = Callable[[QGraphicsPathItem, QPointF, QPointF, QPointF, bool], None]

ARROW_KINDS = {
    "arrow",
    "equilibrium",
    "resonance",
    "curved_single",
    "curved_double",
    "inhibit",
    "dotted",
}


def ring_state_dict(ring_item: QGraphicsPolygonItem) -> dict:
    polygon = ring_item.polygon()
    points = [(point.x(), point.y()) for point in polygon]
    brush = ring_item.brush()
    color = brush.color().name() if brush.style() != Qt.BrushStyle.NoBrush else None
    alpha = brush.color().alphaF() if brush.style() != Qt.BrushStyle.NoBrush else 0.0
    return {
        "kind": "ring",
        "points": points,
        "atom_ids": ring_item.data(2),
        "color": color,
        "alpha": alpha,
    }


def note_state_dict(item: QGraphicsTextItem) -> dict:
    return {
        "kind": "note",
        "text": item.toPlainText(),
        "x": item.pos().x(),
        "y": item.pos().y(),
    }


def mark_state_dict(item, *, mark_center_getter: MarkCenterGetter) -> dict:
    data = item.data(1) or {}
    center = mark_center_getter(item)
    return {
        "kind": "mark",
        "mark_kind": data.get("kind"),
        "text": data.get("text"),
        "atom_id": data.get("atom_id"),
        "dx": data.get("dx"),
        "dy": data.get("dy"),
        "x": center.x(),
        "y": center.y(),
    }


def arrow_state_dict(item: QGraphicsPathItem) -> dict:
    data = item.data(2) or {}
    start = data.get("start")
    end = data.get("end")
    control = data.get("control")
    return {
        "kind": item.data(0),
        "start": (start.x(), start.y()) if isinstance(start, QPointF) else None,
        "end": (end.x(), end.y()) if isinstance(end, QPointF) else None,
        "control": (control.x(), control.y()) if isinstance(control, QPointF) else None,
        "double": bool(data.get("double", False)),
    }


def ts_bracket_state_dict(item: QGraphicsPathItem) -> dict:
    data = item.data(1) or {}
    rect = data.get("rect")
    if not isinstance(rect, QRectF):
        rect = item.sceneBoundingRect()
    return {
        "kind": "ts_bracket",
        "left": rect.left(),
        "top": rect.top(),
        "right": rect.right(),
        "bottom": rect.bottom(),
    }


def ts_bracket_rect_from_state(state: Mapping[str, object]) -> QRectF | None:
    coords = (
        state.get("left"),
        state.get("top"),
        state.get("right"),
        state.get("bottom"),
    )
    if not all(isinstance(value, (int, float)) for value in coords):
        return None
    left, top, right, bottom = (float(value) for value in coords)
    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()


def orbital_state_dict(item: QGraphicsItemGroup) -> dict:
    data = item.data(1) or {}
    center = data.get("center")
    meta = item.data(2) or {}
    return {
        "kind": "orbital",
        "orbital_kind": meta.get("kind", "s"),
        "center": (center.x(), center.y()) if isinstance(center, QPointF) else None,
        "scale": item.scale(),
        "rotation": item.rotation(),
    }


def scene_item_state(item, *, mark_center_getter: MarkCenterGetter) -> dict:
    if item is None:
        return {}
    kind = item.data(0)
    if kind == "ring" and isinstance(item, QGraphicsPolygonItem):
        return ring_state_dict(item)
    if kind == "note" and isinstance(item, QGraphicsTextItem):
        return note_state_dict(item)
    if kind == "mark":
        return mark_state_dict(item, mark_center_getter=mark_center_getter)
    if kind == "ts_bracket" and isinstance(item, QGraphicsPathItem):
        return ts_bracket_state_dict(item)
    if kind == "orbital" and isinstance(item, QGraphicsItemGroup):
        return orbital_state_dict(item)
    if kind in ARROW_KINDS and isinstance(item, QGraphicsPathItem):
        return arrow_state_dict(item)
    return {}


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
) -> None:
    if item is None or not state:
        return
    kind = state.get("kind")
    if kind == "note" and isinstance(item, QGraphicsTextItem):
        item.setPlainText(str(state.get("text", "")))
        item._last_text = item.toPlainText()
        item.setPos(QPointF(float(state.get("x", 0.0)), float(state.get("y", 0.0))))
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
        points = [QPointF(x, y) for x, y in state.get("points", [])]
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
        item.setPath(ts_bracket_path_builder(rect))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(bond_color)))
        item.setData(1, {"rect": QRectF(rect)})
        return
    if kind == "orbital" and isinstance(item, QGraphicsItemGroup):
        center = state.get("center")
        if center is not None:
            center_point = QPointF(*center)
            item.setData(1, {"center": center_point, "base_handle_dist": orbital_base_handle_dist})
            item.setTransformOriginPoint(center_point)
        item.setScale(float(state.get("scale", item.scale())))
        item.setRotation(float(state.get("rotation", item.rotation())))
        return
    if kind in ARROW_KINDS and isinstance(item, QGraphicsPathItem):
        start = state.get("start")
        end = state.get("end")
        if start is None or end is None:
            return
        start_pt = QPointF(*start)
        end_pt = QPointF(*end)
        control = state.get("control")
        double = bool(state.get("double", False))
        if kind in {"curved_single", "curved_double"} and control is not None:
            control_pt = QPointF(*control)
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
