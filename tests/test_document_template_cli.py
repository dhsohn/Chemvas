from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

from chemvas.bootstrap import document_template as cli
from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state


def _files(tmp_path):
    source, request, output = (
        tmp_path / name
        for name in ("source.chemvas", "template.json", "inserted.chemvas")
    )
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
            "notes": [{"text": "preserve 12.30", "x": 400, "y": 200}],
        }
    )
    write_document(source, state, CANVAS_FILE_VERSION)
    request.write_text(
        json_text(
            {
                "format": "chemvas-template-insertion",
                "version": 1,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "ring_size": 6,
                "style": "benzene",
                "position": [100.5, 100],
                "anchor": {"kind": "free"},
            }
        )
    )
    return source, request, output


def _run(source, request, *destination):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "insert-template",
            str(source),
            "--request",
            str(request),
            *map(str, destination),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": "app", "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_cli_native_dry_run_and_write_have_identical_hash_and_preserve_source(tmp_path):
    source, request, output = _files(tmp_path)
    before = source.read_bytes()
    dry = _run(source, request, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert set(tmp_path.iterdir()) == {source, request}
    written = _run(source, request, "--output", output)
    assert written.returncode == 0, written.stderr
    first, second = json.loads(dry.stdout), json.loads(written.stdout)
    assert (
        first["candidate_sha256"]
        == second["candidate_sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert first["written"] is False and second["written"] is True
    assert second["added_atom_ids"] == list(range(6))
    assert source.read_bytes() == before
    candidate = read_document(output)
    assert len(candidate.state["ring_fills"]) == 1
    assert sum(b["order"] == 2 for b in candidate.state["model"]["bonds"]) == 3
    assert candidate.state["notes"] == read_document(source).state["notes"]


@pytest.mark.parametrize(
    "case",
    [
        "hash",
        "duplicate",
        "nan",
        "oversized_request",
        "oversized_source",
        "records",
        "existing_output",
        "symlink",
        "source_output",
        "output_extension",
        "missing_parent",
    ],
)
def test_cli_refuses_invalid_input_or_destination_before_native_work(
    tmp_path, monkeypatch, capsys, case
):
    source, request, output = _files(tmp_path)
    if case == "hash":
        raw = json.loads(request.read_text())
        raw["source_sha256"] = "b" * 64
        request.write_text(json.dumps(raw))
    elif case == "duplicate":
        request.write_text('{"version":1,"version":1}')
    elif case == "nan":
        request.write_text('{"position":[NaN,0]}')
    elif case == "oversized_request":
        monkeypatch.setattr(cli, "MAX_REQUEST_BYTES", 20)
    elif case == "oversized_source":
        monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", 20)
    elif case == "records":
        monkeypatch.setattr(cli, "MAX_GRAPHICS_RECORDS", 10)
    elif case == "existing_output":
        output.write_bytes(b"do not overwrite")
    elif case == "symlink":
        output.symlink_to(tmp_path / "missing.chemvas")
    elif case == "source_output":
        output = source
    elif case == "output_extension":
        output = output.with_suffix(".json")
    else:
        output = tmp_path / "missing" / "new.chemvas"
    original = source.read_bytes()
    prior_output = output.read_bytes() if output.is_file() else None
    monkeypatch.setattr(
        cli,
        "offscreen_canvas",
        lambda *a, **k: pytest.fail("must reject before Qt construction"),
    )
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "insert-template",
                str(source),
                "--request",
                str(request),
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert "chemvas: error:" in capsys.readouterr().err
    assert source.read_bytes() == original
    if prior_output is not None:
        assert output.read_bytes() == prior_output
    elif case != "symlink":
        assert not output.exists()


def test_native_failure_leaves_source_and_destination_untouched(tmp_path, monkeypatch):
    source, request, output = _files(tmp_path)
    original = source.read_bytes()
    monkeypatch.setattr(
        cli,
        "insert_template",
        lambda *a: (_ for _ in ()).throw(RuntimeError("injected native failure")),
    )
    with pytest.raises(SystemExit):
        cli.run(
            [
                "insert-template",
                str(source),
                "--request",
                str(request),
                "--output",
                str(output),
            ]
        )
    assert source.read_bytes() == original
    assert not output.exists()


def test_publish_race_does_not_replace_existing_destination(tmp_path, monkeypatch):
    source, request, output = _files(tmp_path)
    original = source.read_bytes()

    def concurrent_output(*args):
        output.write_bytes(b"concurrent document")
        return read_document(source).state, []

    monkeypatch.setattr(cli, "insert_template", concurrent_output)
    with pytest.raises(SystemExit):
        cli.run(
            [
                "insert-template",
                str(source),
                "--request",
                str(request),
                "--output",
                str(output),
            ]
        )
    assert source.read_bytes() == original
    assert output.read_bytes() == b"concurrent document"
    assert not list(tmp_path.glob("*.staging-*"))


def test_candidate_bound_is_checked_before_publish(tmp_path, monkeypatch):
    source, request, output = _files(tmp_path)
    state = read_document(source).state
    state["notes"][0]["text"] = "x" * (len(source.read_bytes()) + 500)
    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(source.read_bytes()) + 1)
    monkeypatch.setattr(cli, "insert_template", lambda *a: (state, []))
    with pytest.raises(SystemExit):
        cli.run(
            [
                "insert-template",
                str(source),
                "--request",
                str(request),
                "--output",
                str(output),
            ]
        )
    assert not output.exists()
