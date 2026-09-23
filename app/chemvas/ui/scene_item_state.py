from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from chemvas.features.annotations import (
    normalized_bracket_kind,
    normalized_shape_kind,
    normalized_stroke_style,
    sanitize_note_html,
)
from chemvas.ui.image_item import ImageItem
from chemvas.ui.note_item_access import (
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from chemvas.ui.ring_fill_state import set_ring_fill_brush
from chemvas.ui.scene_item_state_serialization import (
    ARROW_KINDS,
    MarkCenterGetter,
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
    shape_state_dict_for,
    ts_bracket_state_dict_for,
)

MarkCenterSetter = Callable[[Any, QPointF], None]
MarkColorSetter = Callable[[Any, str | None], None]
NoteStyleApplier = Callable[[QGraphicsTextItem], None]
RingFillBrushGetter = Callable[[], QBrush]


def scene_item_history_state(item, state: dict) -> dict:
    """Add exact local mark geometry to an already serialized history payload.

    Attachment offsets remain the document/clipboard contract, but atom+offset
    arithmetic can round differently from the original Qt glyph position.
    Keep this history-only field out of the caller's serialized state.
    """
    if state.get("kind") != "mark":
        return state
    position = item.pos()
    return {**state, "item_pos": (position.x(), position.y())}


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
    return normalized_bracket_kind(state["bracket_kind"])


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


def _apply_note_state(
    item: QGraphicsTextItem,
    state: Mapping[str, object],
    note_style_applier: NoteStyleApplier,
) -> None:
    html = sanitize_note_html(state.get("html"))
    if html is not None:
        item.setHtml(html)
    else:
        item.setPlainText(str(state.get("text", "")))
    set_committed_note_text_for(item, item.toPlainText())
    set_committed_note_html_for(item, item.toHtml())
    item.setPos(
        QPointF(
            _float_state_value(state.get("x"), 0.0),
            _float_state_value(state.get("y"), 0.0),
        )
    )
    note_style_applier(item)
    item.setRotation(_float_state_value(state.get("rotation"), 0.0))
    item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)


def apply_scene_item_state(
    item,
    state: Mapping[str, object],
    *,
    model_atoms: Mapping[int, Any],
    note_style_applier: NoteStyleApplier,
    mark_center_setter: MarkCenterSetter,
    mark_color_setter: MarkColorSetter,
    ring_fill_brush_getter: RingFillBrushGetter,
    orbital_base_handle_dist: float,
) -> None:
    if item is None or not state:
        return
    kind = state.get("kind")
    if kind == "image" and isinstance(item, ImageItem):
        item.apply_image_state(state)
        return
    if kind == "note" and isinstance(item, QGraphicsTextItem):
        _apply_note_state(item, state, note_style_applier)
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
        mark_color_setter(item, cast("str | None", state.get("color")))
        _restore_mark_position(item, state, model_atoms, mark_center_setter)
        return
    if kind == "ring" and isinstance(item, QGraphicsPolygonItem):
        points = _points_from_state(state.get("points"))
        if len(points) >= 3:
            item.setPolygon(QPolygonF(points))
        color = state.get("color")
        alpha = state.get("alpha", 0.0)
        if color:
            fill = QColor(str(color))
            source_alpha = float(alpha) if isinstance(alpha, (int, float)) else 0.0
            fill.setAlphaF(source_alpha)
            set_ring_fill_brush(item, fill, source_alpha=source_alpha)
        else:
            set_ring_fill_brush(item, ring_fill_brush_getter())
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
                item.moveBy(
                    center_point.x() - old_center.x(), center_point.y() - old_center.y()
                )
            item.setData(
                1,
                {"center": center_point, "base_handle_dist": orbital_base_handle_dist},
            )
            # Transform origin is item-local: the lobes sit around center - pos,
            # so rotation still pivots about the true lobe center after a move.
            item.setTransformOriginPoint(
                QPointF(
                    center_point.x() - item.pos().x(), center_point.y() - item.pos().y()
                )
            )
        item.setScale(_float_state_value(state.get("scale"), item.scale()))
        item.setRotation(_float_state_value(state.get("rotation"), item.rotation()))
        return


def _restore_mark_position(item, state, model_atoms, mark_center_setter) -> None:
    position = _point_from_state(state.get("item_pos"))
    if position is not None:
        # Exact geometry history may carry the original local position.
        # Qt ignores fuzzy-equal positions; atom restore may have put this
        # mark one ulp from its recorded location, so reset the translation.
        item.setPos(0.0, 0.0)
        item.setPos(position)
    else:
        # Document/clipboard states retain their atom-relative semantics.
        center = mark_center_from_state(state, model_atoms)
        if center is not None:
            mark_center_setter(item, center)


def mark_center_from_state(
    state: Mapping[str, object], model_atoms: Mapping[int, Any]
) -> QPointF | None:
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
    "scene_item_history_state",
    "scene_item_state",
    "scene_item_state_for",
    "shape_fill_from_state",
    "shape_kind_from_state",
    "shape_rect_from_state",
    "shape_state_dict_for",
    "shape_stroke_from_state",
    "ts_bracket_kind_from_state",
    "ts_bracket_rect_from_state",
    "ts_bracket_state_dict_for",
]
