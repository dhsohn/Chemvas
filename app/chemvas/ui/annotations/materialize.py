from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsTextItem,
)

from chemvas.domain.document import (
    AnnotationCollection,
    shape_from_state,
    ts_bracket_from_state,
)
from chemvas.domain.document.ring_fills import RingFill
from chemvas.features.annotations import sanitize_note_html
from chemvas.ui.annotations.items import ImageItem, NoteItem, OrbitalItem, RingFillItem
from chemvas.ui.annotations.records import set_shape_record, set_ts_bracket_record
from chemvas.ui.annotations.state import (
    ARROW_KINDS,
    MarkColorSetter,
    mark_center_from_state,
    shape_fill_from_state,
    shape_kind_from_state,
    shape_rect_from_state,
    shape_stroke_from_state,
    ts_bracket_kind_from_state,
    ts_bracket_rect_from_state,
)
from chemvas.ui.annotations.text import apply_note_style
from chemvas.ui.note_item_access import (
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from chemvas.ui.scene_record_ids import new_scene_record_id
from chemvas.ui.scene_selectability import make_item_selectable

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel
    from chemvas.domain.document.orbitals import Orbital
    from chemvas.ui.scene_render_context import SceneRenderContext

RingFillBrushGetter = Callable[[], Any]
NoteItemFactory = Callable[[], QGraphicsTextItem]
NoteStyleApplier = Callable[[QGraphicsTextItem], None]
MarkItemBuilder = Callable[[str], Any | None]
MarkCenterSetter = Callable[[Any, QPointF], None]
ArrowItemFactory = Callable[[Mapping[str, object]], QGraphicsPathItem]
TsBracketItemBuilder = Callable[..., QGraphicsPathItem]
ShapeItemBuilder = Callable[..., QGraphicsPathItem]
OrbitalItemsBuilder = Callable[[QPointF, str], list[Any]]


def restore_ring_projections(context: SceneRenderContext) -> list[RingFillItem]:
    """Rebuild lost ring views before an edit that uses scene-item history.

    The existing record IDs and order survive. Saving, copying and bond
    geometry read records directly and do not need this materialization.
    """
    document = context.state.ring_state
    views = context.state.scene_items_state.ring_items
    items = []
    for record_id in document.order:
        item = views.get(record_id)
        if item is None or sip.isdeleted(item):
            item = RingFillItem(document, context.model_provider, record_id)
            make_item_selectable(item)
            views[record_id] = item
        if item.scene() is not context.scene:
            context.scene.addItem(item)
        items.append(item)
    return items


def create_ring_item_from_state(
    ring_state: Mapping[str, object],
    *,
    document: AnnotationCollection[RingFill],
    model_provider: Callable[[], MoleculeModel],
    ring_fill_brush_getter: RingFillBrushGetter,
) -> RingFillItem | None:
    points = cast("list", ring_state.get("points", []))
    if len(points) < 3:
        return None
    color = ring_state.get("color")
    alpha = ring_state.get("alpha", 0.0)
    if color:
        fill = QColor(str(color))
        color = fill.name()
        source_alpha = float(alpha) if isinstance(alpha, (int, float)) else 0.0
    else:
        brush = ring_fill_brush_getter()
        color = brush.color().name() if brush.style() != Qt.BrushStyle.NoBrush else None
        source_alpha = brush.color().alphaF() if color else 0.0
    record_id = new_scene_record_id()
    document.records[record_id] = RingFill(
        tuple(cast("list[int]", ring_state.get("atom_ids") or ())),
        cast("str | None", color),
        source_alpha,
    )
    return RingFillItem(document, model_provider, record_id)


def create_note_item_from_state(
    note_state: Mapping[str, object],
    *,
    note_item_factory: NoteItemFactory,
    note_style_applier: NoteStyleApplier,
) -> QGraphicsTextItem:
    item = note_item_factory()
    html = sanitize_note_html(note_state.get("html"))
    if html is not None:
        item.setHtml(html)
    else:
        item.setPlainText(str(note_state.get("text", "")))
    item.setData(0, "note")
    item.setPos(
        QPointF(
            float(cast("Any", note_state.get("x", 0.0))),
            float(cast("Any", note_state.get("y", 0.0))),
        )
    )
    note_style_applier(item)
    item.setRotation(float(cast("Any", note_state.get("rotation", 0.0))))
    # The committed baseline must match the styled live document, otherwise
    # merely entering/leaving a restored note records a false format edit.
    set_committed_note_text_for(item, item.toPlainText())
    set_committed_note_html_for(item, item.toHtml())
    item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return item


def create_mark_item_from_state(
    mark_state: Mapping[str, object],
    *,
    model_atoms: Mapping[int, Any],
    build_mark_item: MarkItemBuilder,
    set_mark_center: MarkCenterSetter,
    set_mark_color: MarkColorSetter,
) -> Any | None:
    center = mark_center_from_state(mark_state, model_atoms)
    if center is None:
        return None
    mark_kind = mark_state.get("mark_kind")
    kind = mark_kind if isinstance(mark_kind, str) else "plus"
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
    set_mark_color(item, cast("str | None", mark_state.get("color")))
    set_mark_center(item, center)
    return item


def create_ts_bracket_item_from_state(
    ts_bracket_state: Mapping[str, object],
    *,
    build_ts_bracket_item: TsBracketItemBuilder,
) -> QGraphicsPathItem | None:
    rect = ts_bracket_rect_from_state(ts_bracket_state)
    if rect is None:
        return None
    bracket_kind = ts_bracket_kind_from_state(ts_bracket_state)
    return build_ts_bracket_item(rect, bracket_kind)


def create_shape_item_from_state(
    shape_state: Mapping[str, object],
    *,
    build_shape_item: ShapeItemBuilder,
) -> QGraphicsPathItem | None:
    rect = shape_rect_from_state(shape_state)
    if rect is None:
        return None
    return build_shape_item(
        rect,
        shape_kind_from_state(shape_state),
        shape_stroke_from_state(shape_state),
        fill=shape_fill_from_state(shape_state),
    )


def create_orbital_item_from_state(
    orbital_state: Mapping[str, object],
    *,
    document: AnnotationCollection[Orbital],
    build_orbital_items: OrbitalItemsBuilder,
    orbital_base_handle_dist: float,
) -> QGraphicsItemGroup | None:
    center = orbital_state.get("center")
    if center is None:
        return None
    center_point = QPointF(*cast("Any", center))
    kind = str(orbital_state.get("orbital_kind", "s"))
    items = build_orbital_items(center_point, kind)
    if not items:
        return None
    return OrbitalItem(orbital_state, document, items, orbital_base_handle_dist)


def create_scene_item_from_state(
    context: SceneRenderContext,
    state: Mapping[str, object],
    *,
    note_item_factory: NoteItemFactory | None = None,
):
    """Materialize one annotation through the shared document renderer.

    The editor supplies its note focus handler; geometry and document records
    are identical in an editor and a standalone scene.
    """
    decorations = context.decorations
    kind = state.get("kind")
    if kind == "image":
        return ImageItem(state, context.state.image_state)
    if kind == "ring":
        return create_ring_item_from_state(
            state,
            document=context.state.ring_state,
            model_provider=context.model_provider,
            ring_fill_brush_getter=context.renderer.ring_fill_brush,
        )
    if kind == "note":
        return create_note_item_from_state(
            state,
            note_item_factory=note_item_factory
            or (lambda: NoteItem(context.state.note_state)),
            note_style_applier=lambda item: apply_note_style(
                item, context.state.text_style_state
            ),
        )
    if kind == "mark":
        return create_mark_item_from_state(
            state,
            model_atoms=context.model.atoms,
            build_mark_item=decorations.build_mark_item,
            set_mark_center=decorations.set_mark_center,
            set_mark_color=decorations.apply_mark_color,
        )
    if kind == "ts_bracket":
        item = create_ts_bracket_item_from_state(
            state, build_ts_bracket_item=decorations.build_ts_bracket_item
        )
        if item is not None:
            set_ts_bracket_record(
                context, item, ts_bracket_from_state(state, error="Invalid TS bracket.")
            )
        return item
    if kind == "shape":
        item = create_shape_item_from_state(
            state, build_shape_item=decorations.build_shape_item
        )
        if item is not None:
            set_shape_record(
                context, item, shape_from_state(state, error="Invalid shape.")
            )
        return item
    if kind == "orbital":
        return create_orbital_item_from_state(
            state,
            document=context.state.orbital_state,
            build_orbital_items=decorations.build_orbital_items,
            orbital_base_handle_dist=context.renderer.style.bond_length_px * 0.8,
        )
    if kind in ARROW_KINDS:
        return context.arrows.create_from_state(state)
    return None
