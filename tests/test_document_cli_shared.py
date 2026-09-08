from __future__ import annotations

import pytest

from chemvas.bootstrap import document_cli_shared


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("win32", "windows"), ("linux", "offscreen"), ("darwin", "offscreen")],
)
def test_qt_platform(platform: str, expected: str) -> None:
    assert document_cli_shared.qt_platform(platform) == expected


def test_graphics_record_count_includes_model_and_scene_records() -> None:
    state: dict[str, object] = {
        "model": {"atoms": {0: {}}, "bonds": [{"a": 0, "b": 1}]},
        "notes": [{"text": "n"}],
        "arrows": [{"kind": "arrow"}],
    }

    assert document_cli_shared.graphics_record_count(state) == 4


def test_offscreen_canvas_preserves_an_existing_application_font(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication

    from chemvas.features.document_composition import compose_document_state

    app = QApplication.instance() or QApplication([])
    original = app.font()
    chosen = QFont("Courier New", 18, QFont.Weight.Bold)
    app.setFont(chosen)
    expected = app.font()
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
        }
    )
    try:
        with document_cli_shared.offscreen_canvas(state, command="test"):
            assert app.font() == expected
        assert app.font() == expected
    finally:
        app.setFont(original)


def test_json_text_is_deterministic_and_newline_terminated() -> None:
    assert (
        document_cli_shared.json_text({"b": 1, "a": [1.5, "å"]})
        == '{\n  "a": [\n    1.5,\n    "å"\n  ],\n  "b": 1\n}\n'
    )
