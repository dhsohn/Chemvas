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


def test_json_text_is_deterministic_and_newline_terminated() -> None:
    assert (
        document_cli_shared.json_text({"b": 1, "a": [1.5, "å"]})
        == '{\n  "a": [\n    1.5,\n    "å"\n  ],\n  "b": 1\n}\n'
    )
