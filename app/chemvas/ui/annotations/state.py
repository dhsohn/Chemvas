"""Shared annotation state owned by the Qt rendering boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsTextItem,
)

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.features.annotations import (
    normalized_bracket_kind,
    normalized_shape_kind,
    normalized_stroke_style,
    sanitize_note_html,
)
from chemvas.ui.annotations.items import ImageItem, NoteItem, OrbitalItem, RingFillItem
from chemvas.ui.annotations.marks import MarkItem
from chemvas.ui.canvas.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas.canvas_model_access import (
    atom_annotation_for,
    atom_for_id,
)
from chemvas.ui.scene.note_item_access import (
    set_committed_note_html_for,
    set_committed_note_text_for,
)

MarkCenterGetter = Callable[[Any], QPointF]

# The document schema owns the arrow kinds; the scene layer reads the same set.
ARROW_KINDS = VALID_ARROW_KINDS


def embedded_scene_item_state(item) -> dict:
    data_method = getattr(item, "data", None)
    if not callable(data_method):
        return {}
    state = data_method(9)
    return dict(state) if isinstance(state, dict) else {}


def _typed_state_dict_for(
    item, item_type: type, converter: Callable[[Any], dict]
) -> dict:
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


def ring_state_dict(ring_item: RingFillItem) -> dict:
    return ring_item.ring_state()


def ring_state_dict_for(canvas, ring_item) -> dict:
    del canvas
    if isinstance(ring_item, RingFillItem):
        return ring_state_dict(ring_item)
    return embedded_scene_item_state(ring_item)


def note_state_dict(item: QGraphicsTextItem) -> dict:
    if isinstance(item, NoteItem):
        return item.note_state()
    html = sanitize_note_html(item.toHtml()) or ""
    return {
        "kind": "note",
        "text": item.toPlainText(),
        "html": html,
        "x": item.pos().x(),
        "y": item.pos().y(),
        **({"rotation": item.rotation()} if item.rotation() else {}),
    }


def note_state_dict_for(canvas, item) -> dict:
    del canvas
    if isinstance(item, NoteItem):
        return item.note_state()
    return _typed_state_dict_for(item, QGraphicsTextItem, note_state_dict)


def mark_state_dict(item, *, mark_center_getter: MarkCenterGetter) -> dict:
    if isinstance(item, MarkItem):
        return item.mark_state()
    data = item.data(1) or {}
    center = mark_center_getter(item)
    mark_kind = data.get("kind")
    if mark_kind not in {"plus", "minus", "circled_plus", "circled_minus", "radical"}:
        mark_kind = "plus"
    return {
        "kind": "mark",
        "mark_kind": mark_kind,
        "text": data.get("text"),
        "atom_id": data.get("atom_id"),
        "dx": data.get("dx"),
        "dy": data.get("dy"),
        "x": center.x(),
        "y": center.y(),
        **({"color": data["color"]} if "color" in data else {}),
    }


def mark_state_dict_for(canvas, item) -> dict:
    if isinstance(item, MarkItem):
        return item.mark_state()
    embedded = embedded_scene_item_state(item)
    if embedded:
        return embedded
    from chemvas.ui.scene.mark_item_access import mark_center_for

    return mark_state_dict(
        item, mark_center_getter=lambda mark_item: mark_center_for(canvas, mark_item)
    )


def arrow_state_dict_for(canvas, item) -> dict:
    from chemvas.domain.document import arrow_to_state

    return _typed_state_dict_for(
        item,
        QGraphicsPathItem,
        lambda arrow: arrow_to_state(canvas.render_context.arrows.record(arrow)),
    )


def ts_bracket_state_dict_for(canvas, item) -> dict:
    embedded = embedded_scene_item_state(item)
    if embedded:
        return {
            "kind": "ts_bracket",
            "left": embedded["left"],
            "top": embedded["top"],
            "right": embedded["right"],
            "bottom": embedded["bottom"],
            "bracket_kind": normalized_bracket_kind(embedded["bracket_kind"]),
        }
    # The record says what the bracket is; the item is not asked.
    from chemvas.ui.annotations.records import (
        ts_bracket_state_from_record_for,
    )

    return _typed_state_dict_for(
        item,
        QGraphicsPathItem,
        lambda ts_bracket_item: ts_bracket_state_from_record_for(
            canvas, ts_bracket_item
        ),
    )


def shape_state_dict_for(canvas, item) -> dict:
    # The record says what the shape is; the item is not asked.
    from chemvas.ui.annotations.records import shape_state_from_record_for

    return _typed_state_dict_for(
        item,
        QGraphicsPathItem,
        lambda shape_item: shape_state_from_record_for(canvas, shape_item),
    )


def orbital_state_dict(item: OrbitalItem) -> dict:
    return item.orbital_state()


def orbital_state_dict_for(canvas, item) -> dict:
    del canvas
    return _typed_state_dict_for(item, OrbitalItem, orbital_state_dict)


def scene_item_state(item, *, mark_center_getter: MarkCenterGetter) -> dict:
    if item is None:
        return {}
    data_method = getattr(item, "data", None)
    if not callable(data_method):
        return {}
    kind = item.data(0)
    if kind == "image" and isinstance(item, ImageItem):
        return item.image_state()
    if kind == "ring" and isinstance(item, RingFillItem):
        return ring_state_dict(item)
    if kind == "note" and isinstance(item, QGraphicsTextItem):
        return note_state_dict(item)
    if kind == "mark":
        return mark_state_dict(item, mark_center_getter=mark_center_getter)
    if kind == "orbital" and isinstance(item, OrbitalItem):
        return orbital_state_dict(item)
    embedded = embedded_scene_item_state(item)
    if embedded:
        return embedded
    return {}


def _item_kind(item) -> object:
    data_method = getattr(item, "data", None)
    return data_method(0) if callable(data_method) else None


def scene_item_state_for(canvas, item) -> dict:
    if item is not None:
        from chemvas.ui.scene.mark_item_access import mark_center_for

        if _item_kind(item) in ARROW_KINDS and isinstance(item, QGraphicsPathItem):
            return arrow_state_dict_for(canvas, item)
        if _item_kind(item) == "shape" and isinstance(item, QGraphicsPathItem):
            return shape_state_dict_for(canvas, item)
        if _item_kind(item) == "ts_bracket" and isinstance(item, QGraphicsPathItem):
            return ts_bracket_state_dict_for(canvas, item)
        state = scene_item_state(
            item,
            mark_center_getter=lambda mark_item: mark_center_for(canvas, mark_item),
        )
        if state:
            return state
    return {}


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
    if kind == "ring" and isinstance(item, RingFillItem):
        item.apply_ring_state(state)
        return

    if kind == "orbital" and isinstance(item, OrbitalItem):
        before = item.orbital_state()
        center = _point_from_state(state.get("center"))
        item.apply_orbital_state(
            {
                "center": before["center"]
                if center is None
                else (center.x(), center.y()),
                "scale": _float_state_value(
                    state.get("scale"), cast("float", before["scale"])
                ),
                "rotation": _float_state_value(
                    state.get("rotation"), cast("float", before["rotation"])
                ),
            }
        )


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
