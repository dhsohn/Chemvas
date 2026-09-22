"""Selection's transient state survives failed editor work as one runtime."""

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF
from PyQt6.QtGui import QColor

from chemvas.ui.canvas_group_state import register_group_for
from chemvas.ui.selection_queries import selection_snapshot_for
from chemvas.ui.selection_state import selection_for, selection_state_for
from chemvas.ui.transactions.document import DocumentSavepoint
from chemvas.ui.transactions.scene_runtime import (
    capture_scene_runtime,
    restore_scene_runtime,
)
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def test_document_restore_preserves_selection_state_and_both_list_identities(canvas):
    owner = selection_for(canvas)
    note_controller = canvas.services.interaction.note_controller
    notes = [
        note_controller.create_text_note(QPointF(x, 0), text)
        for x, text in ((0, "A"), (60, "B"))
    ]
    register_group_for(canvas, set(), notes)
    owner.select_note(notes[0])
    state = selection_state_for(canvas)
    selected_list, outline_list = state.selected_notes, state.outlines
    outlines = list(outline_list)
    color = QColor(state.color)
    assert selected_list == notes
    assert outlines
    snapshot = DocumentSavepoint.capture(canvas)

    # Both in-place mutation and replacement occur during real failed edits.
    selected_list.clear()
    outline_list.clear()
    state.selected_notes = []
    state.outlines = []
    state.color = QColor("red")
    state.suspend_outline = True
    outcome = snapshot.restore()

    assert outcome.authoritative and not outcome.errors
    assert selection_state_for(canvas) is state
    assert state.selected_notes is selected_list
    assert selected_list == notes
    assert state.outlines is outline_list
    assert outline_list == outlines
    assert state.color == color
    assert not state.suspend_outline


def test_scene_reset_clears_selection_without_replacing_owner(canvas):
    owner = selection_for(canvas)
    note = canvas.services.interaction.note_controller.create_text_note(QPointF(), "A")
    owner.select_note(note)
    state = selection_state_for(canvas)
    state.color = QColor("magenta")
    state.suspend_outline = True

    canvas.services.document.canvas_scene_reset_service.clear_scene()

    assert selection_for(canvas) is owner
    assert selection_state_for(canvas) is state
    assert state.selected_notes == []
    assert state.outlines == []
    assert not state.suspend_outline
    assert state.color == QColor("magenta")
    assert selection_snapshot_for(canvas) is None


def test_scene_runtime_restore_preserves_explicit_note_selection_identity(canvas):
    owner = selection_for(canvas)
    note = canvas.services.interaction.note_controller.create_text_note(QPointF(), "A")
    owner.select_note(note)
    state = selection_state_for(canvas)
    selected_list, outline_list = state.selected_notes, state.outlines
    snapshot = capture_scene_runtime(canvas)

    owner.clear_note_selection()
    canvas.scene().clearSelection()
    assert state.selected_notes is not selected_list
    errors = restore_scene_runtime(snapshot, collect_errors=True)

    assert not errors
    assert state.selected_notes is selected_list
    assert selected_list == [note]
    assert state.outlines is outline_list
