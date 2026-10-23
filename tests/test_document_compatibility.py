from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from chemvas.bootstrap import document_patch as patch_cli
from chemvas.core.document_io import (
    parse_document,
    read_exact_snapshot,
    write_snapshot,
)
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_files import read_exact_document as read_cdxml_exact
from tests.document_file_helpers import encode_payload

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "document-v7"


def test_retired_archive_rejects_compact_huge_numbers_before_expansion():
    # A subprocess timeout also protects this regression from hanging the suite
    # if an unchecked Decimal-to-int conversion is reintroduced.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from chemvas.domain.document.retired_endpoint_data import (
    canonicalize_precomplex_state,
)
from chemvas.domain.json_io import strict_json_loads
for token in ("1e1000000000", "-1e1000000000", "1e4096", "1e309"):
    payload = '{"kind":"candidate_ensemble","opaque":{"values":[' + token + ']}}'
    for read in (
            lambda text: canonicalize_precomplex_state(strict_json_loads(text)),
    ):
        try:
            read(payload)
        except ValueError as exc:
            assert "out of range" in str(exc)
        else:
            raise AssertionError("Huge archived number was accepted")
ordinary = '{"kind":"candidate_ensemble","values":[1e3,1.25,0e1000000000]}'
import json
value = json.loads(canonicalize_precomplex_state(strict_json_loads(ordinary))[1])
assert value["values"] == [1000.0, 1.25, 0.0]
assert all(type(item) is float for item in value["values"])
assert json.loads(canonicalize_precomplex_state(value)[1]) == value
""",
        ],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "app"),
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stdout + result.stderr


FROZEN_SHA256 = {
    "minimal": "872e42a2d1d6635279e28c3efbc8540f68918c87026ae62a052d32aa98d7403e",
    "extended": "24d8b3cc358f00f5ca9188e56f7a6b39dbc4c57cebb224cd67f98eb81f91bd7e",
    # Written by Chemvas 0.15.0 with a reviewed candidate_ensemble pair on S01.
    "legacy-reviewed-precomplex": (
        "3d14aeb67cdda436c23220ec960f5283fcb683dbb94319add177b076ca81bdf4"
    ),
}


def _stored_precomplex(state: dict) -> list[dict]:
    return [
        step[side]["precomplex"]
        for step in state["calculation_plan"]["steps"]
        for side in ("reactant", "product")
    ]


def _frozen_document(name: str) -> tuple[bytes, dict]:
    raw = (FIXTURE_ROOT / f"{name}.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256[name]
    payload = json.loads(raw)
    assert payload["version"] == 7
    return raw, payload


@pytest.mark.parametrize("name", FROZEN_SHA256)
def test_frozen_v7_native_read_write_preserves_complete_state(name, tmp_path):
    original_bytes, original = _frozen_document(name)
    path = FIXTURE_ROOT / f"{name}.json"

    read = read_exact_snapshot(path)
    document = read.document

    assert read.source_bytes == original_bytes
    assert document.source_sha256 == FROZEN_SHA256[name]
    assert document.payload == original
    assert document.state == original["state"]
    before = deepcopy(document.state)
    output = tmp_path / "resaved.chemvas"
    written = write_snapshot(output, document.state, CANVAS_FILE_VERSION)
    saved = read_exact_snapshot(output)
    reopened = saved.document
    assert written.payload["version"] == CANVAS_FILE_VERSION
    assert reopened.state == {**original["state"], "last_smiles_input": None}
    assert document.state == before
    assert written.source_sha256 == hashlib.sha256(saved.source_bytes).hexdigest()
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("name", FROZEN_SHA256)
def test_frozen_v7_inspect_dry_run_and_patch_preserve_other_state(
    name, tmp_path, capsys
):
    original_bytes, original = _frozen_document(name)
    original_bytes = encode_payload(original)
    source = tmp_path / "source.cdxml"
    source.write_bytes(original_bytes)
    source_sha256 = hashlib.sha256(original_bytes).hexdigest()

    assert patch_cli.run(["inspect-document", str(source)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["source_sha256"] == source_sha256
    assert inspection["chemvas_document_version"] == CANVAS_FILE_VERSION
    assert inspection["atom_count"] == len(original["state"]["model"]["atoms"])
    request = {
        "format": "chemvas-graph-patch",
        "version": 1,
        "source_sha256": source_sha256,
        "operations": [
            {"op": "update_atom", "atom_id": 0, "changes": {"color": "#ff0000"}}
        ],
    }
    request_path = tmp_path / "patch.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    request_bytes = request_path.read_bytes()
    argv = ["apply-patch", str(source), str(request_path)]

    assert patch_cli.run([*argv, "--dry-run"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert not dry_run["written"]
    assert set(tmp_path.iterdir()) == {source, request_path}
    output = tmp_path / "patched.cdxml"
    assert patch_cli.run([*argv, "--output", str(output)]) == 0
    applied = json.loads(capsys.readouterr().out)
    candidate = read_cdxml_exact(output)
    expected = deepcopy(original["state"])
    expected["last_smiles_input"] = None
    expected["model"]["atoms"]["0"]["color"] = "#ff0000"
    assert candidate.document.state == expected
    assert applied["written"]
    assert dry_run["candidate_sha256"] == applied["candidate_sha256"]
    assert (
        applied["candidate_sha256"]
        == hashlib.sha256(candidate.source_bytes).hexdigest()
    )
    assert applied["source_sha256"] == source_sha256
    assert source.read_bytes() == original_bytes
    assert request_path.read_bytes() == request_bytes


def test_legacy_reviewed_precomplex_objects_survive_native_read_and_resave(tmp_path):
    original_bytes, original = _frozen_document("legacy-reviewed-precomplex")
    stored = _stored_precomplex(original["state"])
    assert [item["kind"] for item in stored] == ["candidate_ensemble"] * 2
    assert all("selection" in item and item["candidates"] for item in stored)

    document = read_exact_snapshot(
        FIXTURE_ROOT / "legacy-reviewed-precomplex.json"
    ).document
    assert _stored_precomplex(document.state) == stored
    output = tmp_path / "resaved.chemvas"
    write_snapshot(output, document.state, CANVAS_FILE_VERSION)
    saved = read_exact_snapshot(output)
    reopened = saved.document

    # The re-saved file spells the same objects, not merely an equal state.
    assert _stored_precomplex(json.loads(saved.source_bytes)["state"]) == stored
    assert _stored_precomplex(reopened.state) == stored
    second = tmp_path / "resaved-again.chemvas"
    write_snapshot(second, reopened.state, CANVAS_FILE_VERSION)
    assert second.read_bytes() == saved.source_bytes
    assert (FIXTURE_ROOT / "legacy-reviewed-precomplex.json").read_bytes() == (
        original_bytes
    )


@pytest.mark.parametrize("token", ["1e309", "1e400", "-2e308"])
def test_archive_number_beyond_float_range_is_rejected_on_open(token, tmp_path):
    # Reading turns every JSON fraction or exponent into a float. An archived
    # number that becomes infinite there would open but could never be saved.
    raw, _payload = _frozen_document("legacy-reviewed-precomplex")
    spelled = '"target_distance_angstrom": 3.0'
    text = raw.decode("utf-8")
    assert spelled in text
    path = tmp_path / "overflow.chemvas"
    path.write_text(
        text.replace(spelled, f'"target_distance_angstrom": {token}', 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="out of range"):
        read_exact_snapshot(path)


def test_graph_patch_moving_an_atom_keeps_legacy_reviewed_precomplex(tmp_path, capsys):
    original_bytes, original = _frozen_document("legacy-reviewed-precomplex")
    original_bytes = encode_payload(original)
    source = tmp_path / "source.cdxml"
    source.write_bytes(original_bytes)
    request_path = tmp_path / "patch.json"
    request_path.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": hashlib.sha256(original_bytes).hexdigest(),
                "operations": [{"op": "move_atom", "atom_id": 0, "x": -3.0, "y": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "patched.cdxml"

    assert (
        patch_cli.run(
            ["apply-patch", str(source), str(request_path), "--output", str(output)]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["written"]
    patched = (
        read_cdxml_exact(output)
        if output.suffix == ".cdxml"
        else read_exact_snapshot(output)
    ).document
    assert patched.state["model"]["atoms"]["0"]["x"] == -3.0
    assert patched.state["calculation_plan"] == original["state"]["calculation_plan"]
    assert source.read_bytes() == original_bytes


@pytest.mark.parametrize("version", [6, 999, 7.0, "7", True])
def test_frozen_v7_reader_does_not_accept_unknown_or_invalid_versions(version):
    _, payload = _frozen_document("minimal")
    payload["version"] = version
    before = deepcopy(payload)

    with pytest.raises(ValueError):
        parse_document(payload)
    assert payload == before


@pytest.mark.parametrize("location", ["envelope", "state", "atom", "mark"])
def test_frozen_v7_reader_still_rejects_unknown_fields(location):
    _, payload = _frozen_document("extended")
    target = {
        "envelope": payload,
        "state": payload["state"],
        "atom": payload["state"]["model"]["atoms"]["0"],
        "mark": payload["state"]["marks"][0],
    }[location]
    target["unknown_field"] = True
    before = deepcopy(payload)

    with pytest.raises(ValueError):
        parse_document(payload)
    assert payload == before
