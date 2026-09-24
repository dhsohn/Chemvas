"""Note color edits share the document history and rollback owners."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QTextCursor

from chemvas.ui.annotations.state import note_state_dict_for
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.note_item_access import NoteTextState
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_access import create_scene_item_from_state
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("text", [" memo", "memo ", " memo ", "\nmemo\n"])
def test_same_color_on_restored_note_preserves_redo(canvas, text):
    color = QColor("#000000")
    service = canvas.services.scene_operations.canvas_color_mutation_service
    source = create_scene_item_from_state(
        canvas, {"kind": "note", "text": text, "x": 0.0, "y": 0.0}
    )
    service.apply_color_to_items([source], color)
    saved = note_state_dict_for(canvas, source)
    note = create_scene_item_from_state(canvas, saved)
    history = canvas.services.history_service
    add_arrow_for(canvas, QPointF(0, 40), QPointF(100, 40), "arrow")
    history.undo()
    before = snapshot_canvas_document_state(canvas)
    stack = history.capture_stack_snapshot()

    service.apply_color_to_items([note], color)

    assert snapshot_canvas_document_state(canvas) == before
    assert history.can_redo()
    history.verify_stack_snapshot(stack)


@pytest.mark.parametrize("pending", [False, True])
def test_failed_publication_restores_note_editor_and_redo(canvas, monkeypatch, pending):
    note = create_scene_item_from_state(
        canvas, {"kind": "note", "text": "memo", "x": 0.0, "y": 0.0}
    )
    history = canvas.services.history_service
    add_arrow_for(canvas, QPointF(0, 40), QPointF(100, 40), "arrow")
    history.undo()
    if pending:
        note.setPlainText("memo typed")
    note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
    cursor = note.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    note.setTextCursor(cursor)
    before = snapshot_canvas_document_state(canvas)
    editor = NoteTextState.capture(note)
    stack = history.capture_stack_snapshot()
    push = history.push

    def publish_then_fail(command):
        push(command)
        raise RuntimeError("failed after publication")

    monkeypatch.setattr(history, "push", publish_then_fail)
    with pytest.raises(RuntimeError, match="after publication"):
        canvas.services.scene_operations.canvas_color_mutation_service.apply_color_to_items(
            [note], QColor("#cc3344")
        )

    assert snapshot_canvas_document_state(canvas) == before
    assert NoteTextState.capture(note) == editor
    history.verify_stack_snapshot(stack)


@pytest.mark.parametrize("operation", ["undo", "redo"])
def test_failed_color_playback_restores_editor_and_allows_retry(
    canvas, monkeypatch, operation
):
    note = create_scene_item_from_state(
        canvas, {"kind": "note", "text": "memo", "x": 0.0, "y": 0.0}
    )
    note.setPlainText("memo typed")
    service = canvas.services.scene_operations.canvas_color_mutation_service
    service.apply_color_to_items([note], QColor("#cc3344"))
    history = canvas.services.history_service
    if operation == "redo":
        history.undo()
    before = snapshot_canvas_document_state(canvas)
    editor = NoteTextState.capture(note)
    stack = history.capture_stack_snapshot()
    apply = NoteTextState.apply
    failed = False

    def apply_then_fail(state, item):
        nonlocal failed
        apply(state, item)
        if not failed:
            failed = True
            raise RuntimeError("failed after applying text")

    monkeypatch.setattr(NoteTextState, "apply", apply_then_fail)
    with pytest.raises(RuntimeError, match="after applying text"):
        getattr(history, operation)()
    assert snapshot_canvas_document_state(canvas) == before
    assert NoteTextState.capture(note) == editor
    history.verify_stack_snapshot(stack)
    getattr(history, operation)()
    assert snapshot_canvas_document_state(canvas) != before
