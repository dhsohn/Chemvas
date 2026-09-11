"""Malformed agent-authored documents fail before reaching Qt consumers."""

import hashlib
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


def _referenced_state():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": 0, "y": 0},
                {"id": 1, "element": "C", "x": 20, "y": 0},
                {"id": 2, "element": "C", "x": 10, "y": 20},
                {"id": 3, "element": "O", "x": 50, "y": 0, "formal_charge": -1},
            ],
            "bonds": [
                {"a": 0, "b": 1, "order": 1},
                {"a": 1, "b": 2, "order": 1},
                {"a": 2, "b": 0, "order": 1},
            ],
            "ring_fills": [{"atom_ids": [0, 1, 2], "color": "#ffcc00", "alpha": 1.0}],
        }
    )


def _set_reference(state, section, value):
    if section == "marks":
        state[section][0]["atom_id"] = value
    else:
        state[section][0]["atom_ids"][0] = value


@pytest.mark.parametrize("section", ["marks", "ring_fills"])
@pytest.mark.parametrize("value", ["0", "3", "00", "٣", True, 0.0, -1, {}, []])
def test_native_reference_values_require_integers_without_mutating_input(
    section, value
):
    state = _referenced_state()
    payload = build_document_payload(state, 7)
    _set_reference(payload["state"], section, value)
    before = json.dumps(payload)
    with pytest.raises(ValueError, match=rf"{section}\[0\].*atom_id"):
        extract_document_state(payload)
    assert json.dumps(payload) == before


def test_json_object_keys_remain_valid_with_integer_reference_values():
    payload = json.loads(json.dumps(build_document_payload(_referenced_state(), 7)))
    state = extract_document_state(payload)
    assert "3" in state["model"]["atoms"]
    assert state["model"]["atom_annotations"]["3"]["formal_charge"] == -1
    assert state["marks"][0]["atom_id"] == 3
    assert state["ring_fills"][0]["atom_ids"] == [0, 1, 2]


@pytest.mark.parametrize("section", ["marks", "ring_fills"])
@pytest.mark.parametrize(
    "command",
    ["inspect", "inspect-document", "render-document", "check-layout", "apply-patch"],
)
def test_all_cli_readers_reject_string_references_without_output(
    tmp_path, section, command
):
    payload = build_document_payload(_referenced_state(), 7)
    _set_reference(payload["state"], section, "3" if section == "marks" else "0")
    source = tmp_path / "invalid.chemvas"
    source.write_text(json.dumps(payload), encoding="utf-8")
    before = source.read_bytes()
    output = tmp_path / (
        "output.png" if command == "render-document" else "output.chemvas"
    )
    args = [command, str(source)]
    if command == "render-document":
        args += ["--output", str(output)]
    elif command == "apply-patch":
        patch = tmp_path / "patch.json"
        patch.write_text(
            json.dumps(
                {
                    "format": "chemvas-graph-patch",
                    "version": 1,
                    "source_sha256": hashlib.sha256(before).hexdigest(),
                    "operations": [{"op": "move_atom", "atom_id": 0, "x": 1, "y": 0}],
                }
            ),
            encoding="utf-8",
        )
        args += [str(patch), "--output", str(output)]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            *args,
        ],
        env=dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen",
            PYTHONPATH=str(Path(__file__).resolve().parents[1] / "app"),
        ),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert f"{section}[0]" in result.stderr
    assert "atom_id" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert source.read_bytes() == before
    assert not output.exists()


@pytest.mark.parametrize("section", ["marks", "ring_fills"])
def test_desktop_rejects_string_references_before_replacing_document(tmp_path, section):
    from unittest import mock

    from PyQt6.QtCore import QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
    from chemvas.ui.main_window_ports import (
        active_canvas_for_window,
        services_for_window,
    )
    from chemvas.ui.structure_mutation_access import add_bond_between_points_for

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = build_main_window()
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    try:
        add_bond_between_points_for(canvas, QPointF(0, 0), QPointF(20, 0))
        history = canvas.services.history_service
        history.undo()
        assert history.can_redo()
        before = snapshot_canvas_state_for(canvas)
        stacks = history.capture_stack_snapshot()
        payload = build_document_payload(_referenced_state(), 7)
        _set_reference(payload["state"], section, "3" if section == "marks" else "0")
        source = tmp_path / "invalid.chemvas"
        source.write_text(json.dumps(payload), encoding="utf-8")
        source_bytes = source.read_bytes()
        message_box = mock.Mock()
        target_provider = mock.Mock()
        assert not services.document_action_service.load_canvas_from_path(
            window,
            str(source),
            message_box=message_box,
            target_provider=target_provider,
        )
        message_box.warning.assert_called_once()
        assert f"{section}[0]" in message_box.warning.call_args.args[2]
        target_provider.assert_not_called()
        assert snapshot_canvas_state_for(canvas) == before
        history.verify_stack_snapshot(stacks)
        assert source.read_bytes() == source_bytes
    finally:
        services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()
