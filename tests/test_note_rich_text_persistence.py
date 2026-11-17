"""Note heading, pre and table HTML survive commit, snapshot, and file round trips."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTextCursor, QTextDocument, QTextTable

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
_TABLE_SPAN_HTML = (
    "<table><tr>"
    '<td colspan="2" rowspan="2">AB</td></tr><tr></tr>'
    "<tr><td>C</td><td>D</td></tr></table>"
)
_TABLE_NESTED_HTML = (
    "<table><tr><td><table><tr><td>in</td></tr></table></td><td>out</td></tr></table>"
)
_TABLE_NESTED_TEXT = "\n\nin\n\nout\n"
_TABLE_TEXT = "\nA\nB\nC\nD\n"
_TABLE_SPAN_TEXT = "\nAB\nC\nD\n"
_PLAIN_CONTROL = "A  x\nB\tC"
_HEADING_SPACES_TEXT = "A   b"


def _cell_text(cell) -> str:
    start, end = cell.firstCursorPosition(), cell.lastCursorPosition()
    cursor = QTextCursor(start)
    cursor.setPosition(start.position(), QTextCursor.MoveMode.MoveAnchor)
    cursor.setPosition(end.position(), QTextCursor.MoveMode.KeepAnchor)
    return cursor.selectedText().replace("\u2029", "\n").strip()


def _table_cell_shapes(table) -> tuple:
    cells = []
    for row in range(table.rows()):
        for column in range(table.columns()):
            cell = table.cellAt(row, column)
            if not cell.isValid() or cell.row() != row or cell.column() != column:
                continue
            cells.append(
                (row, column, cell.rowSpan(), cell.columnSpan(), _cell_text(cell))
            )
    return tuple(cells)


def _collect_tables(frame) -> list:
    tables = []
    for child in frame.childFrames():
        if isinstance(child, QTextTable):
            tables.append((child.rows(), child.columns(), _table_cell_shapes(child)))
            tables.extend(_collect_tables(child))
        else:
            tables.extend(_collect_tables(child))
    return tables


def _note_qt_structure(document) -> tuple:
    blocks = []
    block = document.begin()
    while block.isValid():
        block_format = block.blockFormat()
        blocks.append(
            (
                block_format.headingLevel(),
                block_format.nonBreakableLines(),
                block.text(),
            )
        )
        block = block.next()
    return (tuple(blocks), tuple(_collect_tables(document.rootFrame())))


def _structure_from_html(html: str) -> tuple:
    document = QTextDocument()
    document.setHtml(html)
    return _note_qt_structure(document)


def _assert_note_matches_structure(note, expected: tuple) -> None:
    assert _note_qt_structure(note.document()) == expected


def _heading_block_texts(document) -> tuple[str, ...]:
    return tuple(
        text
        for heading_level, _pre, text in _note_qt_structure(document)[0]
        if heading_level > 0
    )


def _commit_html_note(drawing, html: str, *, route: str = "cmd_v") -> tuple:
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    note = canvas.runtime_state.note_items()[-1]
    _set_note_clipboard(html=html)
    _paste_into_note(window, canvas, route)
    expected_text = note.toPlainText()
    qt_structure = _note_qt_structure(note.document())
    _commit_note_by_defocus(window, canvas)
    return window, canvas, note, expected_text, qt_structure


def _note_matching_text(canvas, text: str):
    return next(n for n in canvas.runtime_state.note_items() if n.toPlainText() == text)


@pytest.mark.parametrize(
    ("html", "expected_text"),
    [
        (_HEADING_HTML, _HEADING_TEXT),
        (_PRE_HTML, _PRE_TEXT),
        (_TABLE_HTML, _TABLE_TEXT),
        (_TABLE_SPAN_HTML, _TABLE_SPAN_TEXT),
        (_TABLE_NESTED_HTML, _TABLE_NESTED_TEXT),
        (None, _PLAIN_CONTROL),
    ],
    ids=["heading", "pre", "table", "table-span", "table-nested", "plain"],
)
@pytest.mark.parametrize("route", ["cmd_v", "edit_menu"])
def test_rich_note_html_survives_commit_snapshot_and_file_roundtrip(
    drawing, tmp_path, html, expected_text, route
):
    if html is not None:
        window, canvas, note, live_text, expected_structure = _commit_html_note(
            drawing, html, route=route
        )
    else:
        window, canvas, note, live_text = _commit_plain_note(
            drawing, expected_text, route=route
        )
        expected_structure = _note_qt_structure(note.document())
    assert live_text == expected_text
    _assert_note_matches_structure(note, expected_structure)

    session = canvas.services.canvas_document_session_service
    state = session.snapshot_state()
    record = next(n for n in state["notes"] if n["text"] == expected_text)
    if record.get("html"):
        assert _structure_from_html(record["html"]) == expected_structure

    session.restore_state(state)
    restored = _note_matching_text(canvas, expected_text)
    assert restored.toPlainText() == expected_text
    _assert_note_matches_structure(restored, expected_structure)

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
    _assert_note_matches_structure(reopened, expected_structure)

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
    _assert_note_matches_structure(copied, expected_structure)


def test_heading_preserves_internal_spaces_through_commit_and_reopen(drawing, tmp_path):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    note = canvas.runtime_state.note_items()[-1]
    _set_note_clipboard(html="<h1>.</h1>")
    _paste_into_note(window, canvas, "cmd_v")
    cursor = QTextCursor(note.document())
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.removeSelectedText()
    block_format = cursor.blockFormat()
    block_format.setHeadingLevel(1)
    cursor.setBlockFormat(block_format)
    cursor.insertText(_HEADING_SPACES_TEXT)
    expected_structure = _note_qt_structure(note.document())
    assert _heading_block_texts(note.document()) == (_HEADING_SPACES_TEXT,)

    _commit_note_by_defocus(window, canvas)
    assert _heading_block_texts(note.document()) == (_HEADING_SPACES_TEXT,)
    _assert_note_matches_structure(note, expected_structure)

    path = tmp_path / "heading-spaces.cdxml"
    assert window.services.document_action_service.save_canvas_to_path(
        window, str(path)
    )
    payload = read_payload(path.read_text(encoding="utf-8"))
    record = next(
        n for n in payload["state"]["notes"] if _HEADING_SPACES_TEXT in n["text"]
    )
    stored = QTextDocument()
    stored.setHtml(record["html"])
    assert _heading_block_texts(stored) == (_HEADING_SPACES_TEXT,)
    window.services.canvas_document_service.replace_canvas_with_state(
        window, canvas, state=payload["state"], file_path=str(path)
    )
    reopened = _note_matching_text(canvas, _HEADING_SPACES_TEXT)
    assert _heading_block_texts(reopened.document()) == (_HEADING_SPACES_TEXT,)
    _assert_note_matches_structure(reopened, expected_structure)


def test_oversized_table_note_save_and_reopen_completes(drawing, tmp_path):
    wide = "".join(f"<td>{i}</td>" for i in range(101))
    narrow = "".join("<tr><td>x</td></tr>" for _ in range(99))
    html = f"<table><tr>{wide}</tr>{narrow}</table>"
    window, canvas, note, _live_text = _commit_html_note(drawing, html)[:4]
    record = note.note_state()
    assert "<table" not in record["html"].lower()

    path = tmp_path / "oversized-table.cdxml"
    assert window.services.document_action_service.save_canvas_to_path(
        window, str(path)
    )
    payload = read_payload(path.read_text(encoding="utf-8"))
    record = payload["state"]["notes"][-1]
    assert "<table" not in record.get("html", "").lower()
    window.services.canvas_document_service.replace_canvas_with_state(
        window, canvas, state=payload["state"], file_path=str(path)
    )
    reopened = canvas.runtime_state.note_items()[-1]
    plain = reopened.toPlainText()
    assert "0" in plain and "x" in plain
    assert not reopened.document().rootFrame().childFrames()


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
