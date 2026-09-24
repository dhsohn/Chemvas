"""Typing updates the unsaved marker without resnapshotting image payloads."""

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from chemvas.ui.canvas.canvas_document_metadata_state import mark_document_dirty_for
from chemvas.ui.canvas.canvas_window_access import notify_document_change_for
from chemvas.ui.molecule.structure_mutation_access import add_atom_for
from chemvas.ui.window import main_window_canvas_document_service as documents
from chemvas.ui.window import main_window_document_action_service as actions_module
from chemvas.ui.window.main_window_ports import services_for_window
from tests.gui_workflow_support import _key, _redo, _saved_note
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def test_live_note_keys_take_at_most_one_full_snapshot(drawing, tmp_path, monkeypatch):
    window, canvas = drawing
    _saved_note(drawing, tmp_path)
    snapshot = Mock(wraps=documents.snapshot_canvas_state_for)
    monkeypatch.setattr(documents, "snapshot_canvas_state_for", snapshot)

    QTest.keyClicks(canvas, "0123456789")

    assert window.isWindowModified()
    assert snapshot.call_count <= 1


def test_native_undo_and_retyping_saved_content_update_the_marker(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " changed")
    assert window.isWindowModified()
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not window.isWindowModified()
    _redo(canvas)
    assert window.isWindowModified()
    for _ in " changed":
        _key(canvas, Qt.Key.Key_Backspace)
    assert note.toPlainText() == "alpha beta gamma"
    assert not window.isWindowModified()


def test_saving_during_edit_resets_the_baseline_for_native_undo(drawing, tmp_path):
    window, canvas = drawing
    note = _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " saved")
    actions = services_for_window(window).document_action_service
    assert actions.save_canvas_to_path(window, str(tmp_path / "active.chemvas"))
    assert not window.isWindowModified()
    assert note.hasFocus()
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.isWindowModified()
    _redo(canvas)
    assert not window.isWindowModified()
    QTest.keyClicks(canvas, " next")
    assert window.isWindowModified()


@pytest.mark.parametrize("recovered", [False, True])
def test_returning_note_to_saved_text_keeps_other_dirty_content(
    drawing, tmp_path, recovered
):
    window, canvas = drawing
    _saved_note(drawing, tmp_path)
    if recovered:
        mark_document_dirty_for(canvas)
    else:
        add_atom_for(canvas, "N", 180, 100)
    QTest.keyClicks(canvas, " changed")
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.isWindowModified()
    assert services_for_window(window).canvas_document_service.is_dirty(canvas)


def test_format_only_edit_and_undo_use_the_saved_html(drawing, tmp_path):
    window, canvas = drawing
    _saved_note(drawing, tmp_path)
    _key(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    canvas.services.note_controller.toggle_text_bold()
    assert window.isWindowModified()
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not window.isWindowModified()


def test_authoritative_dirty_check_sees_unobserved_mutations(drawing, tmp_path):
    window, canvas = drawing
    _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, "x")
    _key(canvas, Qt.Key.Key_Backspace)
    assert not window.isWindowModified()
    # Model writes need not emit UI notifications. Close/save decisions must
    # still inspect the whole document rather than trust the editing hint.
    add_atom_for(canvas, "O", 170, 100)
    service = services_for_window(window).canvas_document_service
    assert service.is_dirty(canvas)
    notify_document_change_for(canvas)
    assert window.isWindowModified()


def test_failed_save_keeps_the_previous_note_baseline(drawing, tmp_path, monkeypatch):
    window, canvas = drawing
    _saved_note(drawing, tmp_path)
    QTest.keyClicks(canvas, " unsaved")
    write = Mock(side_effect=OSError("disk full"))
    monkeypatch.setattr(actions_module, "save_canvas_to_file_for", write)
    message_box = Mock()
    actions = services_for_window(window).document_action_service
    assert not actions.save_canvas_to_path(
        window, str(tmp_path / "failed.chemvas"), message_box=message_box
    )
    message_box.warning.assert_called_once()
    assert window.isWindowModified()
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not window.isWindowModified()
