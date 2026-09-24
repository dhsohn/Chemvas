"""Explicit document records for focused ring projection test doubles."""

from PyQt6.QtCore import Qt

from chemvas.domain.document import AnnotationCollection, Atom, MoleculeModel
from chemvas.domain.document.ring_fills import RingFill
from chemvas.ui.annotations.items import RingFillItem
from chemvas.ui.scene.scene_record_ids import new_scene_record_id


def make_ring(
    polygon=(),
    *,
    canvas=None,
    document=None,
    model=None,
    atom_ids=None,
    color=None,
    alpha=0.0,
    item_type=RingFillItem,
):
    points = [(point.x(), point.y()) for point in polygon]
    if atom_ids is None:
        atom_ids = list(range(len(points)))
    if model is None:
        model = (
            canvas.model
            if canvas is not None
            else MoleculeModel(
                atoms={
                    i: Atom("C", *point)
                    for i, point in zip(atom_ids, points, strict=False)
                }
            )
        )
    if document is None:
        document = (
            canvas.runtime_state.ring_state
            if canvas is not None
            else AnnotationCollection()
        )
    record_id = new_scene_record_id()
    document.records[record_id] = RingFill(tuple(atom_ids), color, alpha)
    provider = (lambda: canvas.model) if canvas is not None else (lambda: model)
    item = item_type(document, provider, record_id)
    item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
    return item


def bind_ring_double(canvas, item):
    """Seed one item double without changing the other records or their IDs."""
    document = canvas.runtime_state.ring_state
    if isinstance(item, RingFillItem):
        assert item.document is document
        record_id = item.record_id
    else:
        data = getattr(item, "data", lambda role: None)
        record_id = data(3)
        if type(record_id) is not int or record_id not in document.records:
            if type(record_id) is not int:
                record_id = new_scene_record_id()
            atom_ids = data(2)
            atom_ids = atom_ids if isinstance(atom_ids, (list, tuple)) else ()
            state = data(9)
            color, alpha = None, 0.0
            brush = getattr(item, "brush", None)
            if callable(brush) and brush().style() != Qt.BrushStyle.NoBrush:
                color, alpha = brush().color().name(), brush().color().alphaF()
            if isinstance(state, dict):
                atom_ids = state.get("atom_ids", atom_ids)
                color, alpha = state.get("color", color), state.get("alpha", alpha)
            document.records[record_id] = RingFill(tuple(atom_ids), color, alpha)
            setter = getattr(item, "setData", None)
            if callable(setter):
                setter(3, record_id)
    return record_id


def register_ring_double(canvas, item):
    record_id = bind_ring_double(canvas, item)
    canvas.runtime_state.ring_state.add(record_id)
    canvas.runtime_state.scene_items_state.ring_items[record_id] = item
    if hasattr(canvas.runtime_state.scene_items_state, "projections"):
        canvas.runtime_state.scene_items_state.projections[record_id] = item


def seed_ring_items(canvas, items):
    document = canvas.runtime_state.ring_state
    canvas.runtime_state.scene_items_state.ring_items = {}
    document.order.clear()
    for item in items:
        register_ring_double(canvas, item)
