"""Document arrows retain their values and identity across edits and recovery."""

from dataclasses import replace

import pytest
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem

from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    Arrow,
    arrow_from_state,
    arrow_to_state,
)
from chemvas.ui.annotations.state import arrow_state_dict_for
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.transactions.document import document_transaction
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_record_owns_saved_values_and_edit_rebuilds_paint(canvas, kind):
    arrows = canvas.render_context.arrows
    item = canvas.services.scene_decoration_service.add_arrow(
        QPointF(10.2, 30.5), QPointF(110.7, 30.5), kind
    )
    state = arrow_state_dict_for(canvas, item)
    assert item.data(1) is None
    assert item.data(2) is None
    # Corrupted paint and legacy metadata cannot become the saved document.
    item.setPath(QPainterPath())
    item.setPos(500, 400)
    item.setData(2, {"start": QPointF(-1, -1), "color": "#ff0000"})
    assert arrow_state_dict_for(canvas, item) == state
    item.setData(2, None)
    canvas.services.move_controller.move_item(item, 3.0, -5.0)
    moved = arrow_state_dict_for(canvas, item)
    assert moved["start"] == (13.2, 25.5)
    assert moved["end"] == (113.7, 25.5)
    assert item.pos() == QPointF()
    assert not item.path().isEmpty()
    assert arrows.record(item).kind == kind


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_undo_redo_and_failed_edit_restore_exact_records_and_items(canvas, kind):
    service = canvas.services.scene_decoration_service
    item = service.add_arrow(QPointF(10.2, 20.3), QPointF(110.7, 30.4), kind)
    service.set_arrow_labels(item, {"above": "k_1", "below": "ΔG^‡"})
    item.setSelected(True)
    before = arrow_state_dict_for(canvas, item)
    path = item.path()
    children = list(item.childItems())
    records = dict(canvas.runtime_state.arrow_state.records)
    with pytest.raises(RuntimeError, match="failed edit"):
        with document_transaction(
            canvas, history_service=canvas.services.history_service
        ):
            canvas.services.scene_item_controller.apply_scene_item_state(
                item, {**before, "end": (200, 100), "color": "#123456"}
            )
            raise RuntimeError("failed edit")
    assert canvas.runtime_state.arrow_items() == [item]
    assert arrow_state_dict_for(canvas, item) == before
    assert canvas.runtime_state.arrow_state.records == records
    assert item.path() == path
    assert item.childItems() == children
    assert canvas.services.scene_transform_controller.translate_selected_items(0.1, 0.3)
    after = arrow_state_dict_for(canvas, item)
    canvas.services.history_service.undo()
    assert arrow_state_dict_for(canvas, item) == before
    canvas.services.history_service.redo()
    assert arrow_state_dict_for(canvas, item) == after
    assert canvas.runtime_state.arrow_items() == [item]


def test_missing_record_cannot_be_attached_or_serialized(canvas):
    item = QGraphicsPathItem()
    item.setData(0, "arrow")
    with pytest.raises(RuntimeError, match="without a record"):
        canvas.services.scene_item_controller.attach_scene_item(item)
    assert item.scene() is None
    assert canvas.runtime_state.arrow_items() == []
    with pytest.raises(RuntimeError, match="no record"):
        arrow_state_dict_for(canvas, item)


@pytest.mark.parametrize("failure", ["attach", "history"])
def test_failed_add_discards_record_even_while_exception_retains_item(
    canvas, monkeypatch, failure
):
    service = canvas.services.scene_decoration_service
    original = service.add_arrow(QPointF(), QPointF(40, 0), "arrow")
    records = dict(canvas.runtime_state.arrow_state.records)
    history = canvas.services.history_service
    commands = tuple(history.state.history)

    def fail(*args, **kwargs):
        raise RuntimeError("failed arrow add")

    if failure == "attach":
        monkeypatch.setattr(type(canvas.runtime_state), "append_scene_item", fail)
    else:
        monkeypatch.setattr(history, "push", fail)
    with pytest.raises(RuntimeError, match="failed arrow add") as retained_error:
        service.add_arrow(QPointF(0, 50), QPointF(40, 50), "curved_double")
    # The traceback keeps the failed item alive, so GC is not a rollback policy.
    assert retained_error.value.__traceback__ is not None
    assert canvas.runtime_state.arrow_state.records == records
    assert canvas.runtime_state.arrow_items() == [original]
    assert tuple(history.state.history) == commands


def test_curve_endpoint_edit_preserves_control_and_control_edit_redraws(canvas):
    arrows = canvas.render_context.arrows
    item = arrows.create_from_state(
        {
            "kind": "curved_double",
            "start": (0, 0),
            "end": (40, 0),
            "control": (20, 16),
            "double": True,
            "labels": {"above": "k_1"},
        }
    )
    canvas.services.scene_item_controller.attach_scene_item(item)
    mutation = canvas.services.handle_mutation_service
    mutation.update_arrow_endpoint(item, QPointF(-2, 0), "start")
    assert arrows.record(item).start == (-2, 0)
    assert arrows.record(item).control == (20, 16)
    mutation.update_curved_control(item, QPointF(19, 4))
    record = arrows.record(item)
    assert record.control == (19, 8)
    assert item.path() == arrows.build_curved_arrow_path(
        QPointF(-2, 0), QPointF(40, 0), QPointF(19, 8), True
    )
    assert item.pos() == QPointF()
    assert len(item.childItems()) == 1


def test_record_validation_refuses_invalid_edits_before_paint_changes(canvas):
    arrows = canvas.render_context.arrows
    item = arrows.build_arrow_item(QPointF(0, 0), QPointF(40, 0), "arrow")
    before, path = arrows.record(item), item.path()
    with pytest.raises(ValueError, match="Invalid arrow"):
        arrows.set_record(item, replace(before, end=(float("nan"), 0)))
    assert arrows.record(item) == before
    assert item.path() == path
    with pytest.raises(ValueError, match="Invalid arrow"):
        arrow_from_state({"kind": "arrow", "start": (0, 0)})


def test_record_copies_label_input_and_omits_removed_labels(canvas):
    labels = {"above": "k_1"}
    record = arrow_from_state(
        {"kind": "arrow", "start": (0, 0), "end": (40, 0), "labels": labels}
    )
    labels["above"] = "changed"
    assert arrow_to_state(record)["labels"] == {"above": "k_1"}
    assert "labels" not in arrow_to_state(replace(record, labels=()))
    assert (
        arrow_to_state(Arrow(kind="line", start=(0, 0), end=(40, 0)))["double"] is False
    )
