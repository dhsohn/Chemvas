"""History retains values and IDs; detached projections can be collected."""

from __future__ import annotations

import gc
import os
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from chemvas.ui.annotations.arrows import ARROW_ID_ROLE
from chemvas.ui.annotations.projections import find_projection
from chemvas.ui.annotations.records import shape_id_for_item, ts_bracket_id_for_item
from chemvas.ui.transactions.document import document_transaction
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    view = build_canvas_view()
    yield view
    view.close()
    app.processEvents()


@pytest.fixture(params=["shape", "ts_bracket", "arrow", "curved_double", "line"])
def kind(request):
    return request.param


def _add(canvas, kind, offset=0.0):
    service = canvas.services.scene_decoration_service
    if kind not in {"shape", "ts_bracket"}:
        return service.add_arrow(QPointF(offset, 20), QPointF(offset + 60, 20), kind)
    return getattr(service, f"add_{kind}")(QRectF(offset, 20.0, 60.0, 40.0))


def _records(canvas, kind):
    if kind not in {"shape", "ts_bracket"}:
        return canvas.runtime_state.arrow_state.records
    return getattr(canvas.runtime_state, f"{kind}_state").records


def _record_id(item, kind):
    if kind not in {"shape", "ts_bracket"}:
        return item.data(ARROW_ID_ROLE)
    id_for = shape_id_for_item if kind == "shape" else ts_bracket_id_for_item
    return id_for(item)


def test_attached_records_survive_history_clear(canvas, kind):
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    record = _records(canvas, kind)[record_id]
    item_ref = weakref.ref(item)
    del item

    canvas.services.history_service.clear()
    gc.collect()

    assert item_ref() is not None
    assert item_ref().scene() is canvas.scene()
    assert _records(canvas, kind) == {record_id: record}


def test_undo_and_redo_recreate_projection_with_same_id_and_value(canvas, kind):
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    record = _records(canvas, kind)[record_id]
    item_ref = weakref.ref(item)
    del item
    history = canvas.services.history_service

    history.undo()
    gc.collect()
    assert item_ref() is None
    assert _records(canvas, kind) == {}

    history.redo()
    restored = find_projection(canvas, record_id)
    assert restored.scene() is canvas.scene()
    assert _record_id(restored, kind) == record_id
    assert _records(canvas, kind) == {record_id: record}


def test_a_new_edit_releases_the_discarded_redo_record(canvas, kind):
    old = _add(canvas, kind)
    old_id = _record_id(old, kind)
    old_ref = weakref.ref(old)
    history = canvas.services.history_service
    history.undo()
    del old

    new = _add(canvas, kind, 100.0)
    gc.collect()

    assert old_ref() is None
    assert old_id not in _records(canvas, kind)
    assert _record_id(new, kind) > old_id
    assert len(_records(canvas, kind)) == 1


def test_delete_history_releases_detached_projection_before_command_eviction(
    canvas, kind
):
    history = canvas.services.history_service
    history.state.limit = 2
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    item_ref = weakref.ref(item)
    item.setSelected(True)
    canvas.services.scene_delete_controller.delete_selected_items()
    del item

    _add(canvas, kind, 100.0)
    gc.collect()
    assert item_ref() is None
    assert record_id not in _records(canvas, kind)

    _add(canvas, kind, 200.0)
    gc.collect()
    assert item_ref() is None
    assert record_id not in _records(canvas, kind)
    assert len(_records(canvas, kind)) == 2


def test_repeated_deletes_are_bounded_by_the_default_history_limit(canvas, kind):
    history = canvas.services.history_service
    assert history.state.limit == 100
    item_refs = []
    for index in range(120):
        item = _add(canvas, kind, float(index))
        item_refs.append(weakref.ref(item))
        item.setSelected(True)
        canvas.services.scene_delete_controller.delete_selected_items()
        del item
    gc.collect()

    # Only value payloads remain in the last fifty add/delete pairs.
    assert len(history.state.history) == 100
    assert len(_records(canvas, kind)) == 0
    assert all(item_ref() is None for item_ref in item_refs)

    history.clear()
    gc.collect()
    assert all(item_ref() is None for item_ref in item_refs)
    assert _records(canvas, kind) == {}


def test_rollback_keeps_records_for_the_restored_history(canvas, kind):
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    record = _records(canvas, kind)[record_id]
    item_ref = weakref.ref(item)
    history = canvas.services.history_service
    history.undo()
    del item

    with pytest.raises(RuntimeError, match="edit failed"):
        with document_transaction(canvas, history_service=history):
            _add(canvas, kind, 100.0)
            raise RuntimeError("edit failed")
    gc.collect()

    assert item_ref() is None
    assert len(history.state.redo_stack) == 1
    assert _records(canvas, kind) == {}
    history.redo()
    assert find_projection(canvas, record_id).scene() is canvas.scene()
    assert _records(canvas, kind) == {record_id: record}


def test_failed_new_record_render_leaves_existing_records_unchanged(canvas, kind):
    _add(canvas, kind)
    before = dict(_records(canvas, kind))

    failure = (
        mock.patch(
            f"chemvas.ui.annotations.records.render_{kind}_item",
            side_effect=RuntimeError("render failed"),
        )
        if kind in {"shape", "ts_bracket"}
        else mock.patch.object(
            canvas.render_context.arrows,
            "render_record",
            side_effect=RuntimeError("render failed"),
        )
    )

    with (
        failure,
        pytest.raises(RuntimeError, match="render failed") as error,
    ):
        _add(canvas, kind, 100.0)

    # Keep the traceback's item alive: cleanup must precede finalization.
    assert str(error.value) == "render failed"
    assert _records(canvas, kind) == before


def test_failed_attach_leaves_existing_records_unchanged(canvas, kind):
    _add(canvas, kind)
    before = dict(_records(canvas, kind))

    with (
        mock.patch(
            "chemvas.ui.scene.scene_item_lifecycle_service.append_scene_item_for",
            side_effect=RuntimeError("attach failed"),
        ),
        pytest.raises(RuntimeError, match="attach failed") as error,
    ):
        _add(canvas, kind, 100.0)

    assert str(error.value) == "attach failed"
    assert _records(canvas, kind) == before


def test_destroyed_qt_items_release_records_without_reading_the_wrapper(canvas, kind):
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    item_ref = weakref.ref(item)

    canvas.services.canvas_scene_reset_service.clear_scene()
    assert sip.isdeleted(item)
    del item
    gc.collect()

    assert item_ref() is None
    assert record_id not in _records(canvas, kind)
