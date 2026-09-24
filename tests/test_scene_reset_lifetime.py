"""Document replacement owns reset and lifetime, not SMILES preview loading."""

import gc
import weakref
from unittest import mock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def test_document_replacement_clears_selection_and_pending_rdkit_warmup(canvas):
    session = canvas.services.canvas_document_session_service
    blank = session.snapshot_state()
    old_highlight = QGraphicsRectItem(QRectF(0, 0, 10, 10))
    canvas.scene().addItem(old_highlight)
    selection_style = canvas.runtime_state.selection_state
    selection_style.suspend_outline = True
    selection_info = canvas.runtime_state.selection_info_state
    callback = mock.Mock()
    selection_info.callback = callback
    selection_info.signature = (frozenset({7}), frozenset({8}))
    selection_info.pending_signature = selection_info.signature
    selection_info.cache = ("OLD", "999.99")
    selection_info.rdkit_warmup_pending = True
    timer = canvas.runtime_state.rdkit_idle_timer
    timer.start()

    session.apply_state(blank)

    assert sip.isdeleted(old_highlight) or old_highlight.scene() is None
    assert not selection_style.suspend_outline
    assert selection_info.signature is None
    assert selection_info.pending_signature is None
    assert selection_info.cache == ("", "")
    assert not selection_info.rdkit_warmup_pending
    callback.assert_called_once_with("", "")
    with (
        mock.patch.object(canvas.rdkit, "preload") as preload,
        mock.patch.object(canvas.rdkit, "compute_props") as compute,
    ):
        canvas.runtime_state.rdkit_idle_warmup_bridge.warm_when_idle()
    preload.assert_not_called()
    compute.assert_not_called()
    assert not timer.isActive()


@pytest.mark.parametrize("iteration", range(3))
def test_replacement_releases_old_note_while_application_stays_alive(
    canvas, qt_application, iteration
):
    session = canvas.services.canvas_document_session_service
    blank = session.snapshot_state()
    note = canvas.services.note_controller.create_text_note(
        QPointF(1, 2), f"temporary note {iteration}"
    )
    reference = weakref.ref(note)

    session.apply_state(blank)
    del note
    gc.collect()
    qt_application.processEvents()
    gc.collect()

    assert reference() is None
    assert QApplication.instance() is qt_application
    assert not sip.isdeleted(qt_application)
    assert session.snapshot_state() == blank


@pytest.mark.parametrize("delete_before_refresh", [False, True])
def test_queued_hover_refresh_is_owned_by_the_canvas(
    qt_application, monkeypatch, delete_before_refresh
):
    from PyQt6.QtGui import QEnterEvent

    view = build_canvas_view()
    refresh = mock.Mock()
    monkeypatch.setattr(view.services.hover, "refresh", refresh)
    view.viewportEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    refresh.assert_not_called()
    if delete_before_refresh:
        schedule_canvas_deletion_for(view)
        qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)
        assert sip.isdeleted(view)
    try:
        qt_application.processEvents()
        if delete_before_refresh:
            refresh.assert_not_called()
        else:
            refresh.assert_called_once_with()
    finally:
        if not sip.isdeleted(view):
            schedule_canvas_deletion_for(view)
            qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)
