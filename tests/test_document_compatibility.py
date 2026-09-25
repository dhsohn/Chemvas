from __future__ import annotations

import base64
import hashlib
import json
import zlib
from copy import deepcopy
from pathlib import Path

import pytest

from chemvas.bootstrap import document_patch as patch_cli
from chemvas.core.document_io import (
    parse_document,
    read_exact_document,
    write_document,
)
from chemvas.core.svg_roundtrip import (
    extract_chemvas_document_from_svg,
    extract_chemvas_svg_payload,
)
from chemvas.domain.document import CANVAS_FILE_VERSION

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "document-v7"
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
    raw = (FIXTURE_ROOT / f"{name}.chemvas").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256[name]
    payload = json.loads(raw)
    assert payload["version"] == 7
    return raw, payload


def _svg_bytes(document: dict, scope: str = "sheet") -> bytes:
    # Intentionally do not call create_editable_svg_payload: the reader must
    # consume the historical envelope even after writer defaults change.
    envelope = {
        "type": "chemvas-svg-source",
        "version": 1,
        "scope": scope,
        "document": document,
    }
    encoded = base64.b64encode(
        zlib.compress(json.dumps(envelope).encode("utf-8"))
    ).decode("ascii")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
        '<metadata><chemvas:source encoding="base64+zlib+json" '
        'type="chemvas-svg-source" version="1">'
        f"{encoded}</chemvas:source></metadata></svg>"
    ).encode()


@pytest.mark.parametrize("name", FROZEN_SHA256)
def test_frozen_v7_native_read_write_preserves_complete_state(name, tmp_path):
    original_bytes, original = _frozen_document(name)
    path = FIXTURE_ROOT / f"{name}.chemvas"

    raw, document = read_exact_document(path)

    assert raw == original_bytes
    assert document.source_sha256 == FROZEN_SHA256[name]
    assert document.payload == original
    assert document.state == original["state"]
    before = deepcopy(document.state)
    output = tmp_path / "resaved.chemvas"
    written = write_document(output, document.state, CANVAS_FILE_VERSION)
    saved_bytes, reopened = read_exact_document(output)
    assert written.payload["version"] == CANVAS_FILE_VERSION
    assert reopened.state == {**original["state"], "last_smiles_input": None}
    assert document.state == before
    assert written.source_sha256 == hashlib.sha256(saved_bytes).hexdigest()
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("name", FROZEN_SHA256)
@pytest.mark.parametrize("scope", ["sheet", "selection"])
def test_literal_v7_editable_svg_readers_preserve_complete_state(name, scope, tmp_path):
    original_bytes, original = _frozen_document(name)
    path = tmp_path / "historical.svg"
    svg_bytes = _svg_bytes(original, scope)
    path.write_bytes(svg_bytes)

    document = extract_chemvas_document_from_svg(path)
    payload = extract_chemvas_svg_payload(path)

    assert document.payload == original
    assert document.state == original["state"]
    assert payload == {
        "type": "chemvas-svg-source",
        "version": 1,
        "scope": scope,
        "document": original,
    }
    assert path.read_bytes() == svg_bytes
    assert (FIXTURE_ROOT / f"{name}.chemvas").read_bytes() == original_bytes


@pytest.mark.parametrize("name", FROZEN_SHA256)
def test_frozen_v7_inspect_dry_run_and_patch_preserve_other_state(
    name, tmp_path, capsys
):
    original_bytes, original = _frozen_document(name)
    source = tmp_path / "source.chemvas"
    source.write_bytes(original_bytes)
    source_sha256 = hashlib.sha256(original_bytes).hexdigest()

    assert patch_cli.run(["inspect-document", str(source)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["source_sha256"] == source_sha256
    assert inspection["chemvas_document_version"] == 7
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
    output = tmp_path / "patched.chemvas"
    assert patch_cli.run([*argv, "--output", str(output)]) == 0
    applied = json.loads(capsys.readouterr().out)
    candidate_bytes, candidate = read_exact_document(output)
    expected = deepcopy(original["state"])
    expected["last_smiles_input"] = None
    expected["model"]["atoms"]["0"]["color"] = "#ff0000"
    assert candidate.state == expected
    assert applied["written"]
    assert dry_run["candidate_sha256"] == applied["candidate_sha256"]
    assert applied["candidate_sha256"] == hashlib.sha256(candidate_bytes).hexdigest()
    assert applied["source_sha256"] == source_sha256
    assert source.read_bytes() == original_bytes
    assert request_path.read_bytes() == request_bytes


def test_legacy_reviewed_precomplex_objects_survive_native_read_and_resave(tmp_path):
    original_bytes, original = _frozen_document("legacy-reviewed-precomplex")
    stored = _stored_precomplex(original["state"])
    assert [item["kind"] for item in stored] == ["candidate_ensemble"] * 2
    assert all("selection" in item and item["candidates"] for item in stored)

    _raw, document = read_exact_document(
        FIXTURE_ROOT / "legacy-reviewed-precomplex.chemvas"
    )
    assert _stored_precomplex(document.state) == stored
    output = tmp_path / "resaved.chemvas"
    write_document(output, document.state, CANVAS_FILE_VERSION)
    saved_bytes, reopened = read_exact_document(output)

    # The re-saved file spells the same objects, not merely an equal state.
    assert _stored_precomplex(json.loads(saved_bytes)["state"]) == stored
    assert _stored_precomplex(reopened.state) == stored
    second = tmp_path / "resaved-again.chemvas"
    write_document(second, reopened.state, CANVAS_FILE_VERSION)
    assert second.read_bytes() == saved_bytes
    assert (FIXTURE_ROOT / "legacy-reviewed-precomplex.chemvas").read_bytes() == (
        original_bytes
    )


def test_graph_patch_moving_an_atom_keeps_legacy_reviewed_precomplex(tmp_path, capsys):
    original_bytes, original = _frozen_document("legacy-reviewed-precomplex")
    source = tmp_path / "source.chemvas"
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
    output = tmp_path / "patched.chemvas"

    assert (
        patch_cli.run(
            ["apply-patch", str(source), str(request_path), "--output", str(output)]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["written"]
    _bytes, patched = read_exact_document(output)
    assert patched.state["model"]["atoms"]["0"]["x"] == -3.0
    assert patched.state["calculation_plan"] == original["state"]["calculation_plan"]
    assert source.read_bytes() == original_bytes


@pytest.mark.parametrize("version", [6, 999, 7.0, "7", True])
def test_frozen_v7_reader_does_not_accept_unknown_or_invalid_versions(
    version, tmp_path
):
    _, payload = _frozen_document("minimal")
    payload["version"] = version
    before = deepcopy(payload)

    with pytest.raises(ValueError):
        parse_document(payload)
    path = tmp_path / "unsupported.svg"
    svg_bytes = _svg_bytes(payload)
    path.write_bytes(svg_bytes)
    with pytest.raises(ValueError):
        extract_chemvas_document_from_svg(path)
    assert payload == before
    assert path.read_bytes() == svg_bytes


@pytest.mark.parametrize("location", ["envelope", "state", "atom", "mark"])
def test_frozen_v7_reader_still_rejects_unknown_fields(location, tmp_path):
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
    path = tmp_path / "unknown-field.svg"
    path.write_bytes(_svg_bytes(payload))
    with pytest.raises(ValueError):
        extract_chemvas_document_from_svg(path)
    assert payload == before
