from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from PyQt6.QtGui import QTextCharFormat, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QApplication, QGraphicsTextItem

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _composition(**items: object) -> dict[str, object]:
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [],
        "bonds": [],
        **items,
    }


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    "kind",
    [
        "square_pair",
        "parentheses_pair",
        "braces_pair",
        "double_dagger",
        "square_left",
        "parenthesis_left",
        "brace_left",
        "dagger",
    ],
)
def test_compose_ts_bracket_renders_a_native_object(tmp_path: Path, kind: str) -> None:
    bracket = {
        "bracket_kind": kind,
        "left": 10,
        "top": 10,
        "right": 90,
        "bottom": 70,
    }
    request = tmp_path / "bracket.json"
    request.write_text(
        json.dumps(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": [],
                "bonds": [],
                "ts_brackets": [bracket],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "bracket.chemvas"
    result = _run("compose-document", str(request), "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert read_document(output).state["ts_brackets"] == [
        {"kind": "ts_bracket", **bracket}
    ]
    svg = tmp_path / "bracket.svg"
    result = _run("render-document", str(output), "--output", str(svg))
    assert result.returncode == 0, result.stderr
    assert "<path" in svg.read_text(encoding="utf-8")


def test_note_runs_keep_text_and_mixed_typography(app) -> None:
    state = compose_document_state(
        _composition(
            notes=[
                {
                    "x": 0,
                    "y": 0,
                    "style": {"font_size": 18},
                    "runs": [
                        {
                            "text": "TS",
                            "style": {
                                "font_weight": 700,
                                "italic": True,
                                "color": "#075CAD",
                            },
                        },
                        {"text": "2", "style": {"vertical_align": "sub"}},
                        {"text": "‡", "style": {"vertical_align": "super"}},
                        {"text": "  <relay>\nnext"},
                    ],
                }
            ]
        )
    )
    note = state["notes"][0]
    assert note["text"] == "TS2‡  <relay>\nnext"
    document = QTextDocument()
    document.setHtml(note["html"])
    assert document.toPlainText() == note["text"]
    cursor = QTextCursor(document)
    cursor.setPosition(0)
    cursor.movePosition(
        QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
    )
    assert cursor.charFormat().fontWeight() == 700
    assert cursor.charFormat().fontItalic()
    assert cursor.charFormat().foreground().color().name() == "#075cad"
    assert cursor.charFormat().fontPointSize() == 18
    for position, alignment in [
        (2, QTextCharFormat.VerticalAlignment.AlignSubScript),
        (3, QTextCharFormat.VerticalAlignment.AlignSuperScript),
    ]:
        cursor.setPosition(position)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
        )
        assert cursor.charFormat().verticalAlignment() == alignment


@pytest.mark.parametrize(
    "run_texts",
    [
        pytest.param(["A\r\nB"], id="crlf-within-run"),
        pytest.param(["A\r", "\nB"], id="crlf-split"),
        pytest.param(["A\r", "", "\nB"], id="crlf-split-empty-run"),
        pytest.param(["A\rB"], id="lone-cr"),
        pytest.param(["A\nB"], id="lf"),
        pytest.param(["A\r", "", "B"], id="lone-cr-split-empty-run"),
        pytest.param(["A\r", "", "\n", "\nB"], id="following-lf-kept"),
        pytest.param(["A\r", " ", "\nB"], id="intervening-space-kept"),
        pytest.param([" A  \t\r", "\n B \t "], id="spaces-tabs"),
    ],
)
def test_cli_note_newlines_match_native_plain_text_after_roundtrip(
    app, tmp_path: Path, run_texts: list[str]
) -> None:
    source = "".join(run_texts)
    runs = [
        {"text": text, "style": {"font_weight": 700 if index == 0 else 400}}
        for index, text in enumerate(run_texts)
    ]
    request = tmp_path / "crlf.json"
    request.write_text(
        json.dumps(_composition(notes=[{"x": 0, "y": 0, "runs": runs}])),
        encoding="utf-8",
    )
    output = tmp_path / "crlf.chemvas"
    result = _run("compose-document", str(request), "--output", str(output))
    assert result.returncode == 0, result.stderr
    state = read_document(output).state
    assert state["notes"][0]["text"] == source
    reference = QTextDocument()
    reference.setPlainText(source)
    canvas = build_canvas_view()
    try:
        restore_canvas_state_for(canvas, state)
        for _ in range(2):
            scene = canvas.scene()
            assert scene is not None
            note = next(item for item in scene.items() if item.data(0) == "note")
            assert isinstance(note, QGraphicsTextItem)
            assert note.toPlainText() == reference.toPlainText()
            for character, weight in [
                ("A", 700),
                ("B", 700 if len(runs) == 1 else 400),
            ]:
                cursor = QTextCursor(note.document())
                cursor.setPosition(reference.toPlainText().index(character))
                cursor.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                assert cursor.charFormat().fontWeight() == weight
            saved = snapshot_canvas_state_for(canvas)
            assert saved["notes"][0]["text"] == reference.toPlainText()
            write_document(output, saved, CANVAS_FILE_VERSION)
            restore_canvas_state_for(canvas, read_document(output).state)
    finally:
        canvas.close()
        canvas.deleteLater()


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("A\r\nB", id="crlf"),
        pytest.param("A\rB", id="lone-cr"),
        pytest.param("A\nB", id="lf"),
        pytest.param(" A  \t\r\nB \t ", id="spaces-tabs"),
    ],
)
def test_styled_note_newlines_match_native_plain_text(app, source: str) -> None:
    state = compose_document_state(
        _composition(
            notes=[{"x": 0, "y": 0, "text": source, "style": {"italic": True}}]
        )
    )
    note = state["notes"][0]
    assert note["text"] == source
    reference = QTextDocument()
    reference.setPlainText(source)
    document = QTextDocument()
    document.setHtml(note["html"])
    for _ in range(2):
        assert document.toPlainText() == reference.toPlainText()
        for character in ("A", "B"):
            cursor = QTextCursor(document)
            cursor.setPosition(reference.toPlainText().index(character))
            cursor.movePosition(
                QTextCursor.MoveOperation.NextCharacter,
                QTextCursor.MoveMode.KeepAnchor,
            )
            assert cursor.charFormat().fontItalic()
        document.setHtml(document.toHtml())


def test_runs_survive_canvas_snapshot_and_restore(app) -> None:
    state = compose_document_state(
        _composition(
            notes=[
                {
                    "x": 12,
                    "y": 15,
                    "runs": [
                        {"text": "A  ", "style": {"font_weight": 700}},
                        {
                            "text": "relay",
                            "style": {"italic": True, "color": "#075CAD"},
                        },
                    ],
                }
            ],
            ts_brackets=[
                {
                    "bracket_kind": "square_pair",
                    "left": 0,
                    "top": 0,
                    "right": 150,
                    "bottom": 60,
                }
            ],
        )
    )
    canvas = build_canvas_view()
    try:
        restore_canvas_state_for(canvas, state)
        for _ in range(2):
            saved = snapshot_canvas_state_for(canvas)
            assert saved["notes"][0]["text"] == "A  relay"
            assert saved["ts_brackets"] == state["ts_brackets"]
            restore_canvas_state_for(canvas, saved)
            scene = canvas.scene()
            assert scene is not None
            note = next(item for item in scene.items() if item.data(0) == "note")
            assert isinstance(note, QGraphicsTextItem)
            cursor = QTextCursor(note.document())
            cursor.setPosition(4)
            assert cursor.charFormat().fontItalic()
            assert cursor.charFormat().foreground().color().name() == "#075cad"
    finally:
        canvas.close()
        canvas.deleteLater()


@pytest.mark.parametrize(
    "note, message",
    [
        ({"runs": [], "text": "x"}, "exactly one"),
        ({}, "exactly one"),
        ({"runs": []}, "must not be empty"),
        ({"runs": "x"}, "must be a JSON array"),
        ({"runs": [None]}, "must be a JSON object"),
        ({"runs": [{"text": 1}]}, "text must be a string"),
        ({"runs": [{"text": "x", "html": "<img>"}]}, "unknown keys"),
        ({"runs": [{"text": "x", "style": {"bold": True}}]}, "supported"),
        ({"runs": [{"text": "x", "style": {"font_size": 97}}]}, "font_size"),
        ({"runs": [{"text": "x", "style": {"italic": 1}}]}, "italic"),
        ({"runs": [{"text": "x", "style": {"vertical_align": []}}]}, "vertical_align"),
        ({"runs": [{"text": "x", "style": {"color": "red"}}]}, "color"),
        ({"runs": [{"text": "x"}] * 257}, "at most 256"),
    ],
)
def test_invalid_runs_are_rejected(note: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compose_document_state(_composition(notes=[{"x": 0, "y": 0, **note}]))


@pytest.mark.parametrize(
    "change, message",
    [
        ({"bracket_kind": "unknown"}, "bracket_kind"),
        ({"bracket_kind": []}, "bracket_kind"),
        ({"left": True}, "left"),
        ({"right": float("inf")}, "right"),
        ({"color": "#000000"}, "unknown keys"),
    ],
)
def test_invalid_brackets_are_rejected(change: dict[str, object], message: str) -> None:
    bracket = {
        "bracket_kind": "square_pair",
        "left": 0,
        "top": 0,
        "right": 40,
        "bottom": 60,
        **change,
    }
    with pytest.raises(ValueError, match=message):
        compose_document_state(_composition(ts_brackets=[bracket]))


def test_runs_escape_markup_and_accept_limit(app) -> None:
    state = compose_document_state(
        _composition(
            notes=[
                {
                    "x": 0,
                    "y": 0,
                    "runs": [{"text": '<img src="file:///a">'}] * 256,
                }
            ]
        )
    )
    html = state["notes"][0]["html"]
    assert "<img" not in html
    document = QTextDocument()
    document.setHtml(html)
    assert document.toPlainText() == '<img src="file:///a">' * 256


def test_composition_preserves_per_arrow_color() -> None:
    state = compose_document_state(
        _composition(
            arrows=[
                {
                    "kind": "curved_double",
                    "start": [0, 0],
                    "control": [30, -25],
                    "end": [60, 0],
                    "color": "#075CAD",
                }
            ]
        )
    )
    assert state["arrows"][0]["color"] == "#075CAD"


@pytest.mark.parametrize(
    "kind, expected", [("curved_double", True), ("curved_single", False)]
)
def test_curve_kind_controls_rendered_head_when_double_is_omitted(
    app, kind: str, expected: bool
) -> None:
    state = compose_document_state(
        _composition(
            arrows=[
                {
                    "kind": kind,
                    "start": [0, 0],
                    "control": [30, -25],
                    "end": [60, 0],
                }
            ]
        )
    )
    canvas = build_canvas_view()
    try:
        restore_canvas_state_for(canvas, state)
        assert snapshot_canvas_state_for(canvas)["arrows"][0]["double"] is expected
    finally:
        canvas.close()
        canvas.deleteLater()


@pytest.mark.parametrize("kind", ["curved_single", "curved_double"])
def test_omitted_curve_control_retains_native_geometry_after_roundtrip(
    app, kind
) -> None:
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas_arrow_build_service import CanvasArrowBuildService
    from chemvas.ui.canvas_scene_items_state import arrow_items_for

    state = compose_document_state(
        _composition(arrows=[{"kind": kind, "start": [0, 0], "end": [60, 0]}])
    )
    canvas = build_canvas_view()
    try:
        restore_canvas_state_for(canvas, state)
        expected = CanvasArrowBuildService(canvas).build_arrow_item(
            QPointF(0, 0), QPointF(60, 0), kind
        )
        control = expected.data(2)["control"]
        for _ in range(2):
            saved = snapshot_canvas_state_for(canvas)
            assert saved["arrows"][0]["control"] == (control.x(), control.y())
            assert saved["arrows"][0]["double"] is (kind == "curved_double")
            assert arrow_items_for(canvas)[0].path() == expected.path()
            restore_canvas_state_for(canvas, saved)
    finally:
        canvas.close()
        canvas.deleteLater()


@pytest.mark.parametrize(
    "kind, double", [("curved_double", False), ("curved_single", True)]
)
def test_contradictory_curve_head_is_rejected(kind: str, double: bool) -> None:
    with pytest.raises(ValueError, match="double must agree with kind"):
        compose_document_state(
            _composition(
                arrows=[
                    {
                        "kind": kind,
                        "start": [0, 0],
                        "control": [30, -25],
                        "end": [60, 0],
                        "double": double,
                    }
                ]
            )
        )
