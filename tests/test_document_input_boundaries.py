"""Malformed agent-authored documents fail before reaching Qt consumers."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chemvas.domain.document import build_document_payload, extract_document_state
from chemvas.features.document_composition import compose_document_state


def _state():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "O", "x": 0, "y": 0}],
            "bonds": [],
        }
    )


@pytest.mark.parametrize("section", ["groups", "shapes", "atom_annotations"])
def test_null_collections_are_not_valid_documents(section):
    state = _state()
    if section == "atom_annotations":
        state["model"][section] = {"0": None}
    else:
        state[section] = None
    with pytest.raises(ValueError, match=section):
        build_document_payload(state, 7)


@pytest.mark.parametrize(
    "text", ["+" * 100_000, "\ud800"], ids=["oversized", "surrogate"]
)
def test_unsafe_mark_text_rejected_without_constructing_glyph_paths(text):
    state = _state()
    state["marks"] = [
        {
            "kind": "plus",
            "text": text,
            "atom_id": None,
            "dx": None,
            "dy": None,
            "x": 0,
            "y": 0,
        }
    ]
    with pytest.raises(ValueError, match="mark.*text"):
        build_document_payload(state, 7)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bond_length_px", 1e10),
        ("text_font_size", 0),
        ("arrow_head_scale", 99),
        ("text_alignment", "middle"),
    ],
)
def test_settings_errors_identify_the_invalid_field(field, value):
    state = _state()
    state["settings"][field] = value
    with pytest.raises(ValueError, match=field):
        build_document_payload(state, 7)


@pytest.mark.parametrize("field", ["text", "html"])
def test_note_unicode_error_has_field_and_index(field):
    state = _state()
    state["notes"] = [{"text": "ok", "x": 0, "y": 0, field: "\ud800"}]
    with pytest.raises(ValueError, match=rf"notes\[0\].*{field}"):
        build_document_payload(state, 7)


def test_invalid_atom_coordinate_error_has_stable_id_and_field():
    state = _state()
    state["model"]["atoms"][0]["x"] = "not a coordinate"
    with pytest.raises(ValueError, match=r"atoms\[0\].*x"):
        build_document_payload(state, 7)


def test_unsupported_file_version_reports_expected_version():
    payload = build_document_payload(_state(), 7)
    payload["version"] = 6
    with pytest.raises(ValueError, match="version.*7"):
        extract_document_state(payload)


@pytest.mark.parametrize(
    "note",
    [
        {"text": "\ud800", "style": {"italic": True}},
        {"runs": [{"text": "ok"}, {"text": "\ud800"}]},
    ],
)
def test_composition_unicode_error_identifies_note_before_html_processing(note):
    with pytest.raises(ValueError, match="note 0.*text.*Unicode"):
        compose_document_state(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": [],
                "bonds": [],
                "notes": [{"x": 0, "y": 0, **note}],
            }
        )


@pytest.mark.parametrize("source", ["https://example.com/a.png", "missing.png"])
def test_image_source_errors_identify_image_index(source):
    from chemvas.bootstrap.document_composition import _read_image_source

    with pytest.raises(ValueError, match="image 0 source"):
        compose_document_state(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": [],
                "bonds": [],
                "images": [{"source": source, "x": 0, "y": 0}],
            },
            image_source_reader=lambda path: _read_image_source(
                Path("/nonexistent"), path
            ),
        )


@pytest.mark.parametrize("command", ["inspect-document", "check-layout"])
def test_cli_rejects_null_annotations_without_traceback_or_mutation(tmp_path, command):
    payload = build_document_payload(_state(), 7)
    payload["state"]["model"]["atom_annotations"] = {"0": None}
    source = tmp_path / "invalid.chemvas"
    source.write_text(json.dumps(payload), encoding="utf-8")
    before = source.read_bytes()
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "app"),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            command,
            str(source),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2, result.stderr
    assert "atom_annotations" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert source.read_bytes() == before
