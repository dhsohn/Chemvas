from __future__ import annotations

import io
from decimal import Decimal
from unittest.mock import Mock

import pytest

from chemvas.bootstrap import document_cli_shared


@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
def test_json_request_bounds_read_and_retains_exact_bytes(extra_bytes) -> None:
    limit = 32
    raw = b' {"x": 1.25}' + b" " * (limit + extra_bytes - 12)
    stream = io.BytesIO(raw)
    read = Mock(wraps=stream.read)
    stream.read = read
    path = Mock()
    path.open.return_value = stream
    if extra_bytes > 0:
        with pytest.raises(ValueError, match="^request too large$"):
            document_cli_shared.read_json_request(
                path,
                max_bytes=limit,
                limit_message="request too large",
                invalid_message="bad request",
            )
    else:
        result = document_cli_shared.read_json_request(
            path,
            max_bytes=limit,
            limit_message="request too large",
            invalid_message="bad request",
        )
        assert result == (raw, {"x": Decimal("1.25")})
        assert isinstance(result[1]["x"], Decimal)
    path.open.assert_called_once_with("rb")
    read.assert_called_once_with(limit + 1)
    assert stream.closed


@pytest.mark.parametrize(
    "raw",
    [b"", b"{", b'{"x": 1, "x": 2}', b"NaN", b'"\xff"'],
    ids=["empty", "syntax", "duplicate", "nonstandard", "encoding"],
)
def test_json_request_preserves_invalid_message_and_closes_stream(raw) -> None:
    stream = io.BytesIO(raw)
    path = Mock()
    path.open.return_value = stream
    with pytest.raises(ValueError, match="^bad request$") as error:
        document_cli_shared.read_json_request(
            path,
            max_bytes=len(raw),
            limit_message="request too large",
            invalid_message="bad request",
        )
    assert isinstance(error.value.__cause__, (ValueError, RecursionError, UnicodeError))
    assert stream.closed


def test_json_request_relabels_decoder_recursion_errors(monkeypatch) -> None:
    stream = io.BytesIO(b"[]")
    path = Mock()
    path.open.return_value = stream
    failure = RecursionError("decoder depth")
    monkeypatch.setattr(
        document_cli_shared, "strict_json_loads", Mock(side_effect=failure)
    )
    with pytest.raises(ValueError, match="^bad request$") as error:
        document_cli_shared.read_json_request(
            path, max_bytes=16, limit_message="too large", invalid_message="bad request"
        )
    assert error.value.__cause__ is failure
    assert stream.closed


def test_json_request_does_not_relabel_io_errors() -> None:
    path = Mock()
    failure = PermissionError("cannot open request")
    path.open.side_effect = failure
    with pytest.raises(PermissionError) as error:
        document_cli_shared.read_json_request(
            path, max_bytes=16, limit_message="request too large", invalid_message="bad"
        )
    assert error.value is failure


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
