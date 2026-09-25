import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from chemvas.bootstrap import document_patch as patch_cli
from chemvas.core.document_io import parse_document, read_document, write_document
from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.domain.document.schema import DOCUMENT_SCHEMA_READERS
from tests.test_document_compatibility import _svg_bytes

FIXTURE = Path(__file__).parent / "fixtures/document-v8/extended.chemvas"


def payload():
    raw = FIXTURE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "014d74db0f13c21ebe5a62e549be6169ec2c285ed165577a44132af8d4c778e8"
    )
    return json.loads(raw)


def test_v8_frozen_roundtrip_and_writer_table(tmp_path):
    original = payload()
    document = read_document(FIXTURE)
    assert document.payload == original
    assert CANVAS_FILE_VERSION == 8
    written = write_document(
        tmp_path / "saved.chemvas", document.state, CANVAS_FILE_VERSION
    )
    assert written.payload == {
        **original,
        "state": {**original["state"], "last_smiles_input": None},
    }
    assert (
        written.payload["min_reader"]
        == DOCUMENT_SCHEMA_READERS[8, written.payload["schema"]]
    )
    assert read_document(tmp_path / "saved.chemvas").state == {
        **original["state"],
        "last_smiles_input": None,
    }
    svg = tmp_path / "editable.svg"
    svg.write_bytes(_svg_bytes(original))
    assert extract_chemvas_document_from_svg(svg).payload == original


@pytest.mark.parametrize(
    "collection,field", [("notes", "rotation"), ("images", "z"), ("shapes", "z")]
)
def test_v7_cannot_smuggle_new_fields(collection, field):
    state = deepcopy(payload()["state"])
    for name, key in [("notes", "rotation"), ("images", "z"), ("shapes", "z")]:
        for item in state[name]:
            if (name, key) != (collection, field):
                item.pop(key, None)
    with pytest.raises(ValueError, match="requires v8"):
        build_document_payload(state, 7)
    with pytest.raises(ValueError, match="requires v8"):
        parse_document({"type": "chemvas", "version": 7, "state": state})


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"schema": 0},
        {"schema": 1.0},
        {"min_reader": "future"},
        {"state": []},
        {"unknown": 1},
        {"type": "other"},
    ],
)
def test_malformed_wrapper_precedes_future_schema(change):
    candidate = {**payload(), "schema": 2, **change}
    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        parse_document(candidate)


def test_future_schema_and_unknown_version_errors():
    with pytest.raises(ValueError, match=r"format 8, schema 2.*up to schema 1.*0.19.0"):
        parse_document({**payload(), "schema": 2, "min_reader": "0.19.0"})
    with pytest.raises(ValueError, match=r"Unsupported.*99.*7, 8"):
        parse_document({"version": 99})
    # min_reader does not override the schema decision.
    assert (
        parse_document({**payload(), "min_reader": "99.0.0"}).state
        == payload()["state"]
    )
    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        parse_document({**payload(), "state": {**payload()["state"], "unknown": 1}})


def test_v8_graph_patch_preserves_features_and_format(tmp_path, capsys):
    assert patch_cli.run(["inspect-document", str(FIXTURE)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["document_format"] == {
        "version": 8,
        "schema": 1,
        "min_reader": "0.18.0",
    }
    request = tmp_path / "patch.json"
    request.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": report["source_sha256"],
                "operations": [
                    {"op": "update_atom", "atom_id": 0, "changes": {"color": "#ff0000"}}
                ],
            }
        )
    )
    output = tmp_path / "patched.chemvas"
    assert (
        patch_cli.run(
            ["apply-patch", str(FIXTURE), str(request), "--output", str(output)]
        )
        == 0
    )
    capsys.readouterr()
    candidate = read_document(output)
    expected = payload()
    expected["state"]["last_smiles_input"] = None
    expected["state"]["model"]["atoms"]["0"]["color"] = "#ff0000"
    assert candidate.payload == expected
