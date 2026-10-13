"""Patched notes remain native editable notes with normal document history."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeySequence, QTextCharFormat, QTextCursor
from PyQt6.QtTest import QTest

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from tests.document_patch_workflow_support import run_patch
from tests.gui_workflow_support import _click, _key, _redo, _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import qt_errors as qt_errors


def _formats(note):
    values = []
    for index in range(4):
        cursor = QTextCursor(note.document())
        cursor.setPosition(index)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
        )
        fmt = cursor.charFormat()
        values.append(
            (
                fmt.fontWeight(),
                fmt.fontPointSize(),
                fmt.foreground().color().name(),
                fmt.verticalAlignment(),
            )
        )
    return values


def test_patch_notes_support_native_edit_undo_redo_save_reopen(
    drawing, tmp_path, app, qt_errors
):
    window, canvas = drawing
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 2,
            "atoms": [{"id": 0, "element": "O", "x": -80, "y": 0}],
            "bonds": [],
            "notes": [{"text": "original caption", "x": -80, "y": 55}],
        }
    )
    state["groups"] = [{"atoms": [0], "items": [["notes", 0]]}]
    source = tmp_path / "source.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    source_bytes = source.read_bytes()
    result, output = run_patch(
        tmp_path,
        source,
        [
            {
                "op": "add_note",
                "note_index": 1,
                "note": {"text": "conditions", "x": 90, "y": 55},
            },
            {"op": "move_note", "note_index": 0, "x": -90, "y": 60},
            {
                "op": "update_note",
                "note_index": 0,
                "content": {
                    "runs": [
                        {"text": "H"},
                        {"text": "2", "style": {"vertical_align": "sub"}},
                        {"text": "O"},
                        {"text": "+", "style": {"vertical_align": "super"}},
                    ],
                    "style": {"font_size": 14, "font_weight": 700, "color": "#123456"},
                },
            },
        ],
    )
    assert result.returncode == 0, result.stderr
    actions = window.services.document_action_service
    assert actions.load_canvas_from_path(window, str(output))
    app.processEvents()
    documents = canvas.services.canvas_document_session_service
    note, untouched = canvas.runtime_state.note_items()
    assert note.toPlainText() == "H2O+"
    assert untouched.toPlainText() == "conditions"
    assert note.pos() == QPointF(-90, 60)
    formats = _formats(note)
    assert all(value[:3] == (700, 14, "#123456") for value in formats)
    assert formats[1][3] == QTextCharFormat.VerticalAlignment.AlignSubScript
    assert formats[3][3] == QTextCharFormat.VerticalAlignment.AlignSuperScript
    loaded = documents.snapshot_state()
    assert loaded["groups"] == state["groups"]
    assert not canvas.services.history_service.state.history

    _tool(window, "note")
    _click(canvas, note.sceneBoundingRect().center())
    assert note.hasFocus()
    QTest.keySequence(
        canvas, QKeySequence(QKeySequence.StandardKey.MoveToEndOfDocument)
    )
    QTest.keyClicks(canvas, " revised")
    assert note.toPlainText() == "H2O+ revised"
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "H2O+"
    _redo(canvas)
    assert note.toPlainText() == "H2O+ revised"
    _tool(window, "select")
    _click(canvas, QPointF(180, 140))
    committed = documents.snapshot_state()
    assert committed["notes"][0]["text"] == "H2O+ revised"
    _key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert documents.snapshot_state() == loaded
    _redo(canvas)
    assert documents.snapshot_state() == committed
    assert _formats(canvas.runtime_state.note_items()[0]) == formats
    saved = tmp_path / "gui-saved.chemvas"
    assert actions.save_canvas_to_path(window, str(saved))
    assert not window.isWindowModified()
    assert read_document(saved).state["notes"] == committed["notes"]
    assert actions.load_canvas_from_path(window, str(saved))
    app.processEvents()
    reopened = canvas.runtime_state.note_items()[0]
    assert reopened.toPlainText() == "H2O+ revised"
    assert reopened.pos() == QPointF(-90, 60)
    assert _formats(reopened) == formats
    assert documents.snapshot_state()["groups"] == state["groups"]
    assert source.read_bytes() == source_bytes
    assert not qt_errors
