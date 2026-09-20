"""Scene records follow the items retained by the document and its history."""

from __future__ import annotations

import gc
import os
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas_scene_reset_access import clear_scene_for
from chemvas.ui.canvas_shape_state import shape_state_for
from chemvas.ui.canvas_ts_bracket_state import ts_bracket_state_for
from chemvas.ui.shape_record_access import shape_id_for_item
from chemvas.ui.transactions.document import document_transaction
from chemvas.ui.ts_bracket_record_access import ts_bracket_id_for_item
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    view = build_canvas_view()
    yield view
    view.close()
    app.processEvents()


@pytest.fixture(params=["shape", "ts_bracket"])
def kind(request):
    return request.param


def _add(canvas, kind, offset=0.0):
    service = canvas.services.scene_decoration.scene_decoration_service
    return getattr(service, f"add_{kind}")(QRectF(offset, 20.0, 60.0, 40.0))


def _records(canvas, kind):
    state_for = shape_state_for if kind == "shape" else ts_bracket_state_for
    return state_for(canvas).records


def _record_id(item, kind):
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


def test_undo_and_redo_keep_the_same_item_and_record(canvas, kind):
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    record = _records(canvas, kind)[record_id]
    item_ref = weakref.ref(item)
    del item
    history = canvas.services.history_service

    history.undo()
    gc.collect()
    assert item_ref() is not None
    assert item_ref().scene() is None
    assert _records(canvas, kind) == {record_id: record}

    history.redo()
    assert item_ref().scene() is canvas.scene()
    assert _record_id(item_ref(), kind) == record_id
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


def test_delete_history_keeps_the_record_until_its_command_is_evicted(canvas, kind):
    history = canvas.services.history_service
    history.state.limit = 2
    item = _add(canvas, kind)
    record_id = _record_id(item, kind)
    item_ref = weakref.ref(item)
    item.setSelected(True)
    canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
    del item

    _add(canvas, kind, 100.0)
    gc.collect()
    assert item_ref() is not None
    assert record_id in _records(canvas, kind)

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
        canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
        del item
    gc.collect()

    # Each deleted item is held by its add and delete commands. Only the last
    # fifty pairs fit in the default hundred-command history.
    assert len(history.state.history) == 100
    assert len(_records(canvas, kind)) == 50
    assert sum(item_ref() is not None for item_ref in item_refs) == 50

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

    assert item_ref() is not None
    assert len(history.state.redo_stack) == 1
    assert _records(canvas, kind) == {record_id: record}
    history.redo()
    assert item_ref().scene() is canvas.scene()


def test_failed_new_record_render_leaves_existing_records_unchanged(canvas, kind):
    _add(canvas, kind)
    before = dict(_records(canvas, kind))

    with (
        mock.patch(
            f"chemvas.ui.{kind}_record_access.render_{kind}_item",
            side_effect=RuntimeError("render failed"),
        ),
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
            "chemvas.ui.scene_item_lifecycle_service.append_scene_item_for",
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

    clear_scene_for(canvas)
    assert sip.isdeleted(item)
    del item
    gc.collect()

    assert item_ref() is None
    assert record_id not in _records(canvas, kind)
