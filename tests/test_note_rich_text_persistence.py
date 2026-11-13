"""Note heading, pre and table HTML survive commit, snapshot, and file round trips."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTextDocument

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.features.annotations import sanitize_note_html
from chemvas.ui.export.cdxml_native_text import write_native_caption
from chemvas.ui.export.export_cdxml import CdxmlUnsupportedObjectError
from chemvas.ui.export.figure_export_service import FigureExportService
from chemvas.ui.window.main_window_ports import (
    copy_selection_for_window,
    history_service_for_window,
    paste_selection_for_window,
)
from tests.document_file_helpers import read_payload
from tests.gui_workflow_support import _click, _key, _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.test_cdxml_export import _simple_state
from tests.test_note_editing_workflows import (
    _commit_note_by_defocus,
    _paste_into_note,
    _set_note_clipboard,
)

_HEADING_HTML = "<h1>A</h1><h1>B</h1>"
_HEADING_TEXT = "A\nB"
_PRE_HTML = "<pre>A  x</pre><pre>B</pre>"
_PRE_TEXT = "A  x\nB"
_TABLE_HTML = (
    "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
)
_TABLE_TEXT = "\nA\nB\nC\nD\n"
_PLAIN_CONTROL = "A  x\nB\tC"


def _commit_html_note(drawing, html: str, *, route: str = "cmd_v") -> tuple:
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    note = canvas.runtime_state.note_items()[-1]
    _set_note_clipboard(html=html)
    _paste_into_note(window, canvas, route)
    expected = note.toPlainText()
    _commit_note_by_defocus(window, canvas)
    return window, canvas, note, expected


def _note_matching_text(canvas, text: str):
    return next(n for n in canvas.runtime_state.note_items() if n.toPlainText() == text)


@pytest.mark.parametrize(
    ("html", "expected_text"),
    [
        (_HEADING_HTML, _HEADING_TEXT),
        (_PRE_HTML, _PRE_TEXT),
        (_TABLE_HTML, _TABLE_TEXT),
        (None, _PLAIN_CONTROL),
    ],
    ids=["heading", "pre", "table", "plain"],
)
@pytest.mark.parametrize("route", ["cmd_v", "edit_menu"])
def test_rich_note_html_survives_commit_snapshot_and_file_roundtrip(
    drawing, tmp_path, html, expected_text, route
):
    window, canvas, note, live_text = (
        _commit_html_note(drawing, html, route=route)
        if html is not None
        else _commit_plain_note(drawing, expected_text, route=route)
    )
    assert live_text == expected_text

    session = canvas.services.canvas_document_session_service
    state = session.snapshot_state()
    record = next(n for n in state["notes"] if n["text"] == expected_text)
    assert record.get("html")

    session.restore_state(state)
    restored = _note_matching_text(canvas, expected_text)
    assert restored.toPlainText() == expected_text

    path = tmp_path / "rich-note.cdxml"
    assert window.services.document_action_service.save_canvas_to_path(
        window, str(path)
    )
    payload = read_payload(path.read_text(encoding="utf-8"))
    window.services.canvas_document_service.replace_canvas_with_state(
        window, canvas, state=payload["state"], file_path=str(path)
    )
    reopened = _note_matching_text(canvas, expected_text)
    assert reopened.toPlainText() == expected_text

    _tool(window, "select")
    _click(canvas, reopened.sceneBoundingRect().center())
    assert copy_selection_for_window(window)
    paste_selection_for_window(window)
    copied = next(
        item
        for item in canvas.runtime_state.note_items()
        if item is not reopened and item.toPlainText() == expected_text
    )
    assert copied.toPlainText() == expected_text


def _commit_plain_note(drawing, plain: str, *, route: str):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    note = canvas.runtime_state.note_items()[-1]
    _set_note_clipboard(plain=plain)
    _paste_into_note(window, canvas, route)
    expected = note.toPlainText()
    _commit_note_by_defocus(window, canvas)
    return window, canvas, note, expected


def test_heading_note_undo_redo_escape_reuse_live_document(drawing, tmp_path):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    note = canvas.runtime_state.note_items()[-1]
    _set_note_clipboard(html=_HEADING_HTML)
    _paste_into_note(window, canvas, "cmd_v")
    assert note.toPlainText() == _HEADING_TEXT

    history = history_service_for_window(window)
    _commit_note_by_defocus(window, canvas)
    assert note.toPlainText() == _HEADING_TEXT

    history.undo()
    history.redo()
    assert _note_matching_text(canvas, _HEADING_TEXT).toPlainText() == _HEADING_TEXT

    _tool(window, "note")
    _click(canvas, note.sceneBoundingRect().center())
    _key(canvas, Qt.Key.Key_Escape)
    assert note.toPlainText() == _HEADING_TEXT


def test_table_note_stays_refused_after_sanitized_restore_html(tmp_path):
    document = QTextDocument()
    document.setHtml(_TABLE_HTML)
    text = document.toPlainText()
    html = sanitize_note_html(document.toHtml())
    assert html is not None
    state = _simple_state(
        atoms={},
        bonds=[],
        notes=[{"text": text, "html": html, "x": 0.0, "y": 30.0}],
    )
    dest = tmp_path / "table-note.cdxml"
    dest.write_bytes(b"previous")
    with offscreen_document_scene(state, command="table-refusal") as context:
        note = context.state.note_items()[0]
        assert note.toPlainText() == text
        assert note.document().rootFrame().childFrames()
        with pytest.raises(CdxmlUnsupportedObjectError, match="table/frame"):
            FigureExportService(context).export_figure(str(dest), fmt="cdxml")
    assert dest.read_bytes() == b"previous"


def test_write_native_caption_preserves_heading_block_lines():
    document = QTextDocument()
    document.setHtml(_HEADING_HTML)
    html = sanitize_note_html(document.toHtml())
    assert html is not None
    state = {
        "text": _HEADING_TEXT,
        "html": html,
        "x": 10.0,
        "y": 20.0,
    }
    root = ET.fromstring(
        '<CDXML CaptionFont="3"><fonttable><font id="3" name="Arial"/>'
        '</fonttable><page id="1"><t id="2" p="0 0"><s font="3" size="10" face="0">old</s></t></page></CDXML>'
    )
    node = root.find(".//t")
    assert node is not None
    write_native_caption(root, node, state)
    assert "".join(node.itertext()) == _HEADING_TEXT
