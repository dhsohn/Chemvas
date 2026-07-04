from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from ui.bracket_types import LEGACY_TS_BRACKET_KIND, normalized_bracket_kind
from ui.canvas_atom_graphics_state import atom_items_for
from ui.canvas_model_access import atom_annotation_for, atom_for_id
from ui.shape_geometry import normalized_shape_kind, normalized_stroke_style

MarkCenterGetter = Callable[[Any], QPointF]

ARROW_KINDS = {
    "arrow",
    "equilibrium",
    "resonance",
    "curved_single",
    "curved_double",
    "inhibit",
    "dotted",
}


def embedded_scene_item_state(item) -> dict:
    data_method = getattr(item, "data", None)
    if not callable(data_method):
        return {}
    state = data_method(9)
    return dict(state) if isinstance(state, dict) else {}


def _typed_state_dict_for(item, item_type: type, converter: Callable[[Any], dict]) -> dict:
    embedded = embedded_scene_item_state(item)
    if embedded:
        return embedded
    if isinstance(item, item_type):
        return converter(item)
    return {}


def bond_state_dict(bond) -> dict:
    return {
        "a": bond.a,
        "b": bond.b,
        "order": bond.order,
        "style": bond.style,
        "color": bond.color,
    }


def atom_state_dict_for(canvas, atom_id: int) -> dict:
    atom = atom_for_id(canvas, atom_id)
    if atom is None:
        return {}
    explicit = bool(atom.explicit_label)
    if atom.element.upper() == "C" and atom_id in atom_items_for(canvas):
        explicit = True
    state = {
        "element": atom.element,
        "x": atom.x,
        "y": atom.y,
        "color": atom.color,
        "explicit_label": explicit,
    }
    annotation = atom_annotation_for(canvas, atom_id)
    if annotation:
        state["annotation"] = annotation
    return state


def ring_state_dict(ring_item: QGraphicsPolygonItem) -> dict:
    polygon = ring_item.polygon()
    points = [(polygon.at(index).x(), polygon.at(index).y()) for index in range(polygon.count())]
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


def ring_state_dict_for(canvas, ring_item) -> dict:
    del canvas
    return _typed_state_dict_for(ring_item, QGraphicsPolygonItem, ring_state_dict)


def note_state_dict(item: QGraphicsTextItem) -> dict:
    return {
        "kind": "note",
        "text": item.toPlainText(),
        "html": item.toHtml(),
        "x": item.pos().x(),
        "y": item.pos().y(),
    }


def note_state_dict_for(canvas, item) -> dict:
    del canvas
    return _typed_state_dict_for(item, QGraphicsTextItem, note_state_dict)


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


def mark_state_dict_for(canvas, item) -> dict:
    embedded = embedded_scene_item_state(item)
    if embedded:
        return embedded
    from ui.mark_item_access import mark_center_for

    return mark_state_dict(item, mark_center_getter=lambda mark_item: mark_center_for(canvas, mark_item))


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


def arrow_state_dict_for(canvas, item) -> dict:
    del canvas
    return _typed_state_dict_for(item, QGraphicsPathItem, arrow_state_dict)


def ts_bracket_state_dict(item: QGraphicsPathItem) -> dict:
    data = item.data(1) or {}
    rect = data.get("rect")
    if not isinstance(rect, QRectF):
        rect = item.sceneBoundingRect()
    state = {
        "kind": "ts_bracket",
        "left": rect.left(),
        "top": rect.top(),
        "right": rect.right(),
        "bottom": rect.bottom(),
    }
    bracket_kind = normalized_bracket_kind(data.get("bracket_kind"), default=LEGACY_TS_BRACKET_KIND)
    if bracket_kind != LEGACY_TS_BRACKET_KIND:
        state["bracket_kind"] = bracket_kind
    return state


def ts_bracket_state_dict_for(canvas, item) -> dict:
    del canvas
    return _typed_state_dict_for(item, QGraphicsPathItem, ts_bracket_state_dict)


def shape_state_dict(item: QGraphicsPathItem) -> dict:
    data = item.data(1) or {}
    rect = data.get("rect")
    if not isinstance(rect, QRectF):
        rect = item.sceneBoundingRect()
    state: dict[str, object] = {
        "kind": "shape",
        "left": rect.left(),
        "top": rect.top(),
        "right": rect.right(),
        "bottom": rect.bottom(),
        "shape_kind": normalized_shape_kind(data.get("shape_kind")),
        "stroke_style": normalized_stroke_style(data.get("stroke_style")),
    }
    fill = item.brush().color()
    if fill.alphaF() > 0.0:
        state["fill"] = fill.name()
        state["fill_alpha"] = fill.alphaF()
    return state


def shape_state_dict_for(canvas, item) -> dict:
    del canvas
    return _typed_state_dict_for(item, QGraphicsPathItem, shape_state_dict)


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


def orbital_state_dict_for(canvas, item) -> dict:
    del canvas
    return _typed_state_dict_for(item, QGraphicsItemGroup, orbital_state_dict)


def scene_item_state(item, *, mark_center_getter: MarkCenterGetter) -> dict:
    if item is None:
        return {}
    data_method = getattr(item, "data", None)
    if not callable(data_method):
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
    if kind == "shape" and isinstance(item, QGraphicsPathItem):
        return shape_state_dict(item)
    if kind == "orbital" and isinstance(item, QGraphicsItemGroup):
        return orbital_state_dict(item)
    if kind in ARROW_KINDS and isinstance(item, QGraphicsPathItem):
        return arrow_state_dict(item)
    embedded = embedded_scene_item_state(item)
    if embedded:
        return embedded
    return {}


def scene_item_state_for(canvas, item) -> dict:
    if item is not None:
        from ui.mark_item_access import mark_center_for

        state = scene_item_state(item, mark_center_getter=lambda mark_item: mark_center_for(canvas, mark_item))
        if state:
            return state
    return {}


__all__ = [
    "ARROW_KINDS",
    "MarkCenterGetter",
    "arrow_state_dict",
    "arrow_state_dict_for",
    "atom_state_dict_for",
    "bond_state_dict",
    "embedded_scene_item_state",
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
    "shape_state_dict",
    "shape_state_dict_for",
    "ts_bracket_state_dict",
    "ts_bracket_state_dict_for",
]
