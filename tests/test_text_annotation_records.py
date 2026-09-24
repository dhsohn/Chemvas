"""Text editor signals publish values; save and chemistry read document records."""

import gc
from unittest import mock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.domain.document import CLIPBOARD_SELECTION_VERSION
from chemvas.domain.document.marks import mark_to_state
from chemvas.features.annotations import sanitize_note_html
from chemvas.ui.annotations.state import (
    atom_state_dict_for,
    bond_state_dict,
    mark_state_dict,
    note_state_dict,
)
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.mark_item_access import mark_kinds_by_atom_for, sync_marks_for_atom_for
from chemvas.ui.scene_clipboard_access import (
    build_selection_clipboard_payload_for_canvas,
)
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.structure_mutation_access import add_atom_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def test_native_text_format_undo_and_blocked_replacement_publish_document_values(
    canvas,
):
    note = canvas.services.interaction.note_controller.create_text_note(
        QPointF(1.25, -3.5), "H2O"
    )
    document = note.document()
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" solution")
    record = canvas.runtime_state.note_state.records[note.record_id]
    assert record.text == "H2O solution"
    document.undo()
    assert canvas.runtime_state.note_state.records[note.record_id].text == "H2O"
    document.redo()
    cursor.select(QTextCursor.SelectionType.Document)
    style = QTextCharFormat()
    style.setForeground(QColor("#cc3344"))
    cursor.mergeCharFormat(style)
    record = canvas.runtime_state.note_state.records[note.record_id]
    assert record.html == sanitize_note_html(note.toHtml())
    assert "#cc3344" in record.html
    document.blockSignals(True)
    try:
        note.setHtml("<p>blocked <b>replacement</b></p>")
    finally:
        document.blockSignals(False)
    record = canvas.runtime_state.note_state.records[note.record_id]
    assert record.text == "blocked replacement"
    assert record.html == sanitize_note_html(note.toHtml())
    note.setPos(5.125, -7.25)
    note.setRotation(37.5)
    state = note_state_dict(note)
    assert (state["x"], state["y"], state["rotation"]) == (5.125, -7.25, 37.5)
    with (
        mock.patch.object(note, "toPlainText", side_effect=AssertionError("Qt read")),
        mock.patch.object(note, "toHtml", side_effect=AssertionError("Qt read")),
        mock.patch.object(note, "pos", side_effect=AssertionError("Qt read")),
        mock.patch.object(note, "rotation", side_effect=AssertionError("Qt read")),
    ):
        assert note_state_dict(note) == state
        saved = (
            canvas.services.document.canvas_document_session_service.snapshot_state()
        )
        assert saved["notes"] == [
            {key: value for key, value in state.items() if key != "kind"}
        ]


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("loss", ["detach", "destroy", "release"])
def test_lost_mark_view_preserves_copy_and_electronic_annotation(canvas, kind, loss):
    atom_id = add_atom_for(canvas, "N", 10.25, -13.5)
    mark = add_mark_for_atom_for(canvas, atom_id, QPointF(22.5, -17.25), kind=kind)
    state = mark.mark_state()
    record_id = mark.record_id
    # The QVariant role is a derived read, not another mutable metadata owner.
    assert QGraphicsItem.data(mark, 1) is None
    metadata = mark.data(1)
    metadata["kind"] = "other"
    assert mark.mark_state() == state
    with mock.patch.object(mark, "pos", side_effect=AssertionError("Qt read")):
        assert (
            mark_state_dict(mark, mark_center_getter=lambda _: pytest.fail("Qt read"))
            == state
        )
    before = canvas.services.document.canvas_document_session_service.snapshot_state()
    annotation = dict(canvas.model.atom_annotations[atom_id])
    if loss == "destroy":
        sip.delete(mark)
    else:
        canvas.scene().removeItem(mark)
    if loss == "release":
        canvas.runtime_state.scene_items_state.mark_items.pop(record_id)
        canvas.runtime_state.mark_registry.clear()
        canvas.services.history_service.clear()
        del mark
        gc.collect()
    assert mark_kinds_by_atom_for(canvas) == {atom_id: [kind]}
    sync_marks_for_atom_for(canvas, atom_id)
    assert canvas.model.atom_annotations[atom_id] == annotation
    assert (
        canvas.services.document.canvas_document_session_service.snapshot_state()
        == before
    )
    payload = build_selection_clipboard_payload_for_canvas(
        canvas,
        selected_items=[],
        explicit_atom_ids={atom_id},
        selected_bond_ids=set(),
        bonds=[],
        atom_state_getter=lambda i: atom_state_dict_for(canvas, i),
        bond_state_getter=bond_state_dict,
        scene_item_state_getter=lambda _: pytest.fail("view serialization"),
        version=CLIPBOARD_SELECTION_VERSION,
    )
    assert payload["marks"] == [
        mark_to_state(canvas.runtime_state.mark_state.records[record_id])
    ]
