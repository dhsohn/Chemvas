"""Public acceptance documents retain their distinctive content after saving."""

from __future__ import annotations

import base64
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.annotations import LabelRun, parse_arrow_label
from chemvas.features.document_files import read_document

DOCUMENTS = Path(__file__).resolve().parents[1] / "examples/release-validation"
COUNTS = {
    "01-basic": (16, 16, 0, 1),
    "02-reactants": (18, 18, 4, 1),
    "03-notation": (7, 4, 2, 1),
    "04-mixed": (3, 2, 1, 0),
    "05-native": (3, 2, 2, 1),
}


@pytest.mark.parametrize("name,expected", COUNTS.items())
def test_release_document_inventory(name, expected):
    state = read_document(DOCUMENTS / f"{name}.cdxml").state
    assert (
        len(state["model"]["atoms"]),
        len(state["model"]["bonds"]),
        len(state["notes"]),
        len(state["arrows"]),
    ) == expected


def test_release_document_distinctive_content():
    basic = read_document(DOCUMENTS / "01-basic.cdxml").state
    assert parse_arrow_label(basic["arrows"][0]["labels"]["above"]) == (
        LabelRun("MnO", "normal"),
        LabelRun("2", "sub"),
    )

    reactants = read_document(DOCUMENTS / "02-reactants.cdxml").state
    assert [note["text"] for note in reactants["notes"]] == ["1", "2", "3", "+"]
    # Each caption belongs visually below its own six-atom fragment. This also
    # catches the original failure mode of stacking captions below the pair.
    atoms = reactants["model"]["atoms"]
    for index, note in enumerate(reactants["notes"][:3]):
        fragment = [atoms[str(atom)] for atom in range(index * 6, index * 6 + 6)]
        left, right = min(a["x"] for a in fragment), max(a["x"] for a in fragment)
        assert left < note["x"] < right
        assert note["y"] > max(a["y"] for a in fragment)

    notation = read_document(DOCUMENTS / "03-notation.cdxml").state
    assert notation["model"]["atom_annotations"] == {
        "5": {"formal_charge": 1},
        "6": {"formal_charge": -1},
    }
    assert [b["style"] for b in notation["model"]["bonds"]] == [
        "wedge",
        "hash",
        "single",
        "single",
    ]
    assert notation["notes"][0]["text"] == "H2O / ΔG‡"
    assert "vertical-align:sub" in notation["notes"][0]["html"]
    assert "vertical-align:super" in notation["notes"][0]["html"]

    mixed = read_document(DOCUMENTS / "04-mixed.cdxml").state
    assert mixed["groups"] == [{"atoms": [0, 1, 2], "items": [["notes", 0]]}]
    assert mixed["notes"][0]["text"] == "Group A\n한글 α + H2O"
    assert mixed["shapes"][0]["stroke_style"] == "dashed"
    assert len(mixed["images"]) == 1
    with Image.open(
        io.BytesIO(base64.b64decode(mixed["images"][0]["data_base64"]))
    ) as image:
        assert image.size == (120, 60)
        assert image.getpixel((30, 30)) == (36, 116, 181)
        assert image.getpixel((90, 30)) == (230, 138, 46)


@pytest.mark.parametrize("name", COUNTS)
def test_release_document_save_and_reopen_preserves_state(tmp_path, name):
    source = DOCUMENTS / f"{name}.cdxml"
    original = source.read_bytes()
    with offscreen_canvas(read_document(source).state, command="release-roundtrip") as (
        _,
        service,
    ):
        # Qt normalizes native text on loading. Compare the complete live state
        # at the save boundary, rather than only counting serialized objects.
        before = json.loads(json.dumps(service.snapshot_state()))
        saved = tmp_path / f"{name}-한글 copy.cdxml"
        service.save_to_file(str(saved))
        after = read_document(saved).state
        service.apply_state(after)
        assert json.loads(json.dumps(service.snapshot_state())) == before
        assert after == before
    assert source.read_bytes() == original


def test_native_fixture_has_no_snapshot_and_preserves_native_style(tmp_path):
    source = DOCUMENTS / "05-native.cdxml"
    assert b"ChemvasDocument:" not in source.read_bytes()
    state = read_document(source).state
    assert state["model"]["atoms"][2]["element"] == "O"
    assert state["model"]["bonds"][1]["order"] == 2
    assert "#1a59a6" in state["notes"][0]["html"]
    assert state["notes"][0]["text"] == "Native sample"
    with offscreen_canvas(state, command="native-style") as (_, service):
        saved = tmp_path / "native-saved.cdxml"
        service.save_to_file(str(saved))
    before, after = (
        ET.fromstring(source.read_bytes()),
        ET.fromstring(saved.read_bytes()),
    )
    for xpath in ("./fonttable", "./colortable", "./page/t"):
        assert ET.tostring(after.find(xpath)) == ET.tostring(before.find(xpath))
    old_fragment = before.find("./page/fragment")
    new_fragment = after.find("./page/fragment")
    assert new_fragment.attrib == old_fragment.attrib
    for tag in ("n", "b"):
        assert [e.attrib for e in new_fragment.findall(tag)] == [
            e.attrib for e in old_fragment.findall(tag)
        ]
    # Saving assigns an ID to the previously anonymous atom-label <t>. That
    # identity normalization must preserve its position, style and text.
    old_label = old_fragment.find("./n/t")
    new_label = new_fragment.find("./n/t")
    assert new_label.attrib.keys() == old_label.attrib.keys() | {"id"}
    assert new_label.attrib["p"] == old_label.attrib["p"]
    assert ET.tostring(new_label.find("s")) == ET.tostring(old_label.find("s"))
