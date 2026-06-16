from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from ui.graphics_items import NoSelectPolygonItem
from ui.note_item_access import set_committed_note_text_for
from ui.scene_item_state import (
    ARROW_KINDS,
    mark_center_from_state,
    ts_bracket_rect_from_state,
)

RingFillBrushGetter = Callable[[], Any]
NoteItemFactory = Callable[[], QGraphicsTextItem]
NoteStyleApplier = Callable[[QGraphicsTextItem], None]
MarkItemBuilder = Callable[[str], Any | None]
MarkCenterSetter = Callable[[Any, QPointF], None]
ArrowItemBuilder = Callable[[QPointF, QPointF, str], QGraphicsPathItem]
CurvedArrowPathSetter = Callable[[QGraphicsPathItem, QPointF, QPointF, QPointF, bool], None]
TsBracketItemBuilder = Callable[[Any], QGraphicsPathItem]
OrbitalItemsBuilder = Callable[[QPointF, str], list[Any]]


def create_ring_item_from_state(
    ring_state: Mapping[str, object],
    *,
    ring_fill_brush_getter: RingFillBrushGetter,
) -> QGraphicsPolygonItem | None:
    points = [QPointF(x, y) for x, y in cast(Any, ring_state.get("points", []))]
    if len(points) < 3:
        return None
    ring_item = NoSelectPolygonItem(QPolygonF(points))
    color = ring_state.get("color")
    alpha = ring_state.get("alpha", 0.0)
    if color:
        fill = QColor(str(color))
        fill.setAlphaF(float(alpha) if isinstance(alpha, (int, float)) else 0.0)
        ring_item.setBrush(fill)
    else:
        ring_item.setBrush(ring_fill_brush_getter())
    ring_item.setPen(QPen(Qt.PenStyle.NoPen))
    ring_item.setData(0, "ring")
    ring_item.setData(2, ring_state.get("atom_ids"))
    return ring_item


def create_note_item_from_state(
    note_state: Mapping[str, object],
    *,
    note_item_factory: NoteItemFactory,
    note_style_applier: NoteStyleApplier,
) -> QGraphicsTextItem:
    item = note_item_factory()
    item.setPlainText(str(note_state.get("text", "")))
    set_committed_note_text_for(item, item.toPlainText())
    item.setData(0, "note")
    item.setPos(QPointF(float(cast(Any, note_state.get("x", 0.0))), float(cast(Any, note_state.get("y", 0.0)))))
    note_style_applier(item)
    item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return item


def create_mark_item_from_state(
    mark_state: Mapping[str, object],
    *,
    model_atoms: Mapping[int, Any],
    build_mark_item: MarkItemBuilder,
    set_mark_center: MarkCenterSetter,
) -> Any | None:
    center = mark_center_from_state(mark_state, model_atoms)
    if center is None:
        return None
    kind = str(mark_state.get("mark_kind", "plus"))
    item = build_mark_item(kind)
    if item is None:
        return None
    data = {
        "kind": kind,
        "atom_id": mark_state.get("atom_id"),
    }
    dx = mark_state.get("dx")
    dy = mark_state.get("dy")
    if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
        data["dx"] = float(dx)
        data["dy"] = float(dy)
    text = mark_state.get("text")
    if text is not None and isinstance(item, QGraphicsTextItem):
        item.setPlainText(str(text))
        data["text"] = str(text)
    item.setData(0, "mark")
    item.setData(1, data)
    set_mark_center(item, center)
    return item


def create_arrow_item_from_state(
    arrow_state: Mapping[str, object],
    *,
    build_arrow_item: ArrowItemBuilder,
    set_curved_arrow_path: CurvedArrowPathSetter,
) -> QGraphicsPathItem | None:
    kind = str(arrow_state.get("kind", "arrow"))
    start = arrow_state.get("start")
    end = arrow_state.get("end")
    if start is None or end is None:
        return None
    start_pt = QPointF(*cast(Any, start))
    end_pt = QPointF(*cast(Any, end))
    item = build_arrow_item(start_pt, end_pt, kind)
    item.setData(0, kind)
    control = arrow_state.get("control")
    double = bool(arrow_state.get("double", False))
    data = {"start": start_pt, "end": end_pt, "control": None, "double": double}
    if kind in {"curved_single", "curved_double"} and control is not None:
        control_pt = QPointF(*cast(Any, control))
        set_curved_arrow_path(item, start_pt, end_pt, control_pt, double)
        data["control"] = control_pt
    item.setData(2, data)
    return item


def create_ts_bracket_item_from_state(
    ts_bracket_state: Mapping[str, object],
    *,
    build_ts_bracket_item: TsBracketItemBuilder,
) -> QGraphicsPathItem | None:
    rect = ts_bracket_rect_from_state(ts_bracket_state)
    if rect is None:
        return None
    return build_ts_bracket_item(rect)


def create_orbital_item_from_state(
    orbital_state: Mapping[str, object],
    *,
    build_orbital_items: OrbitalItemsBuilder,
    orbital_base_handle_dist: float,
) -> QGraphicsItemGroup | None:
    center = orbital_state.get("center")
    if center is None:
        return None
    center_point = QPointF(*cast(Any, center))
    kind = str(orbital_state.get("orbital_kind", "s"))
    items = build_orbital_items(center_point, kind)
    if not items:
        return None
    group = QGraphicsItemGroup()
    for item in items:
        group.addToGroup(item)
    group.setData(0, "orbital")
    group.setData(
        1,
        {
            "center": QPointF(center_point),
            "base_handle_dist": orbital_base_handle_dist,
        },
    )
    group.setData(2, {"kind": kind})
    group.setTransformOriginPoint(center_point)
    group.setScale(float(cast(Any, orbital_state.get("scale", 1.0))))
    group.setRotation(float(cast(Any, orbital_state.get("rotation", 0.0))))
    return group


def create_scene_item_from_state(
    state: Mapping[str, object],
    *,
    model_atoms: Mapping[int, Any],
    note_item_factory: NoteItemFactory,
    note_style_applier: NoteStyleApplier,
    build_mark_item: MarkItemBuilder,
    set_mark_center: MarkCenterSetter,
    ring_fill_brush_getter: RingFillBrushGetter,
    build_arrow_item: ArrowItemBuilder,
    set_curved_arrow_path: CurvedArrowPathSetter,
    build_ts_bracket_item: TsBracketItemBuilder,
    build_orbital_items: OrbitalItemsBuilder,
    orbital_base_handle_dist: float,
):
    kind = state.get("kind")
    if kind == "ring":
        return create_ring_item_from_state(state, ring_fill_brush_getter=ring_fill_brush_getter)
    if kind == "note":
        return create_note_item_from_state(
            state,
            note_item_factory=note_item_factory,
            note_style_applier=note_style_applier,
        )
    if kind == "mark":
        return create_mark_item_from_state(
            state,
            model_atoms=model_atoms,
            build_mark_item=build_mark_item,
            set_mark_center=set_mark_center,
        )
    if kind == "ts_bracket":
        return create_ts_bracket_item_from_state(state, build_ts_bracket_item=build_ts_bracket_item)
    if kind == "orbital":
        return create_orbital_item_from_state(
            state,
            build_orbital_items=build_orbital_items,
            orbital_base_handle_dist=orbital_base_handle_dist,
        )
    if kind in ARROW_KINDS:
        return create_arrow_item_from_state(
            state,
            build_arrow_item=build_arrow_item,
            set_curved_arrow_path=set_curved_arrow_path,
        )
    return None
