from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from chemvas.bootstrap import document_patch as cli
from chemvas.domain.document.inspection import (
    component_inventory,
    inspect_component_inventory,
)
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.document_patch import inspect_document_graph

if TYPE_CHECKING:
    from pathlib import Path


def _external(charge: str, *, note: bool = False) -> bytes:
    caption = '<t id="30" p="20 100"><s>original</s></t>' if note else ""
    return (
        '<CDXML><page BoundingBox="0 0 200 200"><fragment id="10">'
        f'<n id="20" p="50 50" Element="7" Charge="{charge}"/>'
        f"</fragment>{caption}</page></CDXML>"
    ).encode()


@pytest.mark.parametrize("charge", [-2, -1, 0, 1, 2])
def test_native_charge_inspection_is_detached_and_repeatable(charge: int) -> None:
    state = parse_cdxml_document(_external(str(charge)), preserve_source=True).state
    before = deepcopy(state)
    inventory = inspect_component_inventory(state)
    assert inventory.components[0].formal_charge == charge
    assert inventory.model.atom_annotations[0] == {"formal_charge": charge}
    assert (
        component_inventory(state, inventory.model).components == inventory.components
    )
    assert inspect_document_graph(state)["atoms"][0]["annotation"] == {
        "formal_charge": charge
    }
    assert state == before
    assert state["marks"] == []


def test_invalid_native_charge_does_not_report_zero() -> None:
    state = parse_cdxml_document(_external("invalid"), preserve_source=True).state
    with pytest.raises(ValueError):
        inspect_document_graph(state)


@pytest.mark.parametrize("kind", ["plus", "radical", "minus"])
def test_native_charge_does_not_double_count_or_hide_conflicting_marks(
    kind: str,
) -> None:
    state = parse_cdxml_document(_external("1"), preserve_source=True).state
    state["marks"] = [{"atom_id": 0, "kind": kind}]
    if kind == "minus":
        with pytest.raises(ValueError, match="Conflicting native charge"):
            inspect_document_graph(state)
    else:
        component = inspect_document_graph(state)["components"][0]
        assert component["formal_charge"] == 1
        assert component["radical_electrons"] == int(kind == "radical")


def test_deleted_native_atom_does_not_contribute_charge() -> None:
    state = parse_cdxml_document(_external("1"), preserve_source=True).state
    state["model"]["atoms"] = {}
    assert inspect_document_graph(state)["components"] == []


@pytest.mark.parametrize("note", [False, True])
@pytest.mark.usefixtures("qt_application")
def test_external_note_patch_roundtrip_preserves_charge_and_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], note: bool
) -> None:
    source = tmp_path / "external.cdxml"
    raw = _external("-1", note=note)
    source.write_bytes(raw)
    before_stat = source.stat()
    assert cli.run(["inspect-document", str(source)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["components"][0]["formal_charge"] == -1
    patch = tmp_path / "patch.json"
    patch.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": inspected["source_sha256"],
                "operations": [
                    {
                        "op": "add_note",
                        "note_index": int(note) + i,
                        "note": {"text": text, "x": 10 + i * 20, "y": 20},
                    }
                    for i, text in enumerate(["memo", "second"])
                ],
            }
        )
    )
    assert cli.run(["apply-patch", str(source), str(patch), "--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    output = tmp_path / "patched.cdxml"
    assert (
        cli.run(["apply-patch", str(source), str(patch), "--output", str(output)]) == 0
    )
    saved = json.loads(capsys.readouterr().out)
    assert dry["candidate_sha256"] == saved["candidate_sha256"]
    assert saved["candidate_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert source.read_bytes() == raw
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns
    root = ET.fromstring(output.read_bytes())
    original_node = ET.fromstring(raw).find(".//n")
    assert root.find(".//n").attrib == original_node.attrib
    assert len(root.findall(".//n")) == 1
    assert len(root.findall(".//graphic")) == 0
    # Check both snapshot reopening and a consumer that reads native XML only.
    native = ET.tostring(root)
    for content in (output.read_bytes(), native):
        state = parse_cdxml_document(content, preserve_source=True).state
        report = inspect_document_graph(state)
        assert report["components"][0]["formal_charge"] == -1
        assert report["note_count"] == int(note) + 2
        assert [n["text"] for n in report["notes"]][-2:] == ["memo", "second"]
