from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document.schema import (
    VALID_ARROW_KINDS,
    VALID_ORBITAL_KINDS,
    VALID_SHAPE_KINDS,
    VALID_TS_BRACKET_KINDS,
)
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.document_files import read_document
from chemvas.ui.export.cdxml_document_writer import serialize_cdxml_document
from chemvas.ui.window.main_window_path_logic import (
    is_desktop_document_path,
    resolve_save_as_path,
)


def sample_state():
    return json.loads(
        (Path(__file__).parent / "fixtures/document-v8/extended.json").read_text()
    )["state"]


def normalized(state):
    return json.loads(json.dumps(state))


CASES = (
    [("all", None)]
    + [("arrows", kind) for kind in sorted(VALID_ARROW_KINDS)]
    + [("orbitals", kind) for kind in sorted(VALID_ORBITAL_KINDS)]
    + [("shapes", kind) for kind in sorted(VALID_SHAPE_KINDS)]
    + [("ts_brackets", kind) for kind in sorted(VALID_TS_BRACKET_KINDS)]
)


@pytest.mark.parametrize("collection,kind", CASES)
def test_new_document_all_elements_save_reopen(tmp_path, collection, kind):
    state = sample_state()
    if collection != "all":
        record = state[collection][0]
        record[
            {"shapes": "shape_kind", "ts_brackets": "bracket_kind"}.get(
                collection, "kind"
            )
        ] = kind
        if collection == "arrows":
            record.pop("labels", None)
            record.pop("mirrored", None)
            if kind.startswith("curved"):
                record["control"] = [130, 110]
    with offscreen_canvas(state, command="test-cdxml-save") as (canvas, service):
        before = normalized(service.snapshot_state())
        path = tmp_path / "new.cdxml"
        service.save_to_file(str(path))
        raw = path.read_bytes()
        assert ET.fromstring(raw).tag == "CDXML"
        loaded = read_document(path)
        assert loaded.state == before
        service.apply_state(loaded.state)
        assert normalized(service.snapshot_state()) == before
        # A second save must preserve edits and must not grow nested snapshots.
        second = serialize_cdxml_document(canvas, service.snapshot_state())
        assert parse_cdxml_document(second).state == before
        assert second.count(b"<!-- ChemvasDocument:") == 1
        native = raw[: raw.rfind(b"\n<!-- ChemvasDocument:")]
        projected = parse_cdxml_document(native, preserve_source=True)
        assert projected.state["model"]["atoms"] or projected.state["images"]


def test_cdxml_only_paths_and_old_json_rejection(tmp_path):
    assert resolve_save_as_path("new") == "new.cdxml"
    assert not is_desktop_document_path("old.chemvas")
    path = tmp_path / "renamed.cdxml"
    path.write_text(
        json.dumps({"type": "chemvas", "version": 10, "state": sample_state()})
    )
    with pytest.raises(ValueError, match="CDXML"):
        read_document(path)
    with offscreen_canvas(sample_state(), command="test-old-format") as (_, service):
        with pytest.raises(ValueError, match="cdxml"):
            service.save_to_file(str(tmp_path / "old.chemvas"))
        assert not (tmp_path / "old.chemvas").exists()


def test_flat_mixed_document_keeps_native_atoms_and_valid_references():
    state = sample_state()
    state.pop("perspective", None)
    with offscreen_canvas(state, command="test-native-mixed-save") as (canvas, service):
        root = ET.fromstring(serialize_cdxml_document(canvas, service.snapshot_state()))
    assert len(list(root.iter("n"))) >= len(state["model"]["atoms"])
    assert list(root.iter("b"))
    assert list(root.iter("embeddedobject"))
    identities = [
        e.attrib["id"] for e in root.iter() if "id" in e.attrib and e.tag != "font"
    ]
    assert len(identities) == len(set(identities))
    fonts = {e.attrib["id"] for e in root.findall("./fonttable/font")}
    for element in root.iter():
        for key in ("B", "E", "SupersededBy"):
            if key in element.attrib:
                assert element.attrib[key] in identities
        if "font" in element.attrib:
            assert element.attrib["font"] in fonts


def test_mixed_document_renders_identically_after_reopen(tmp_path):
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter

    from chemvas.ui.canvas.sheet_setup_access import sheet_rect_for

    def render(canvas):
        image = QImage(1400, 1000, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            canvas.scene().render(
                painter, QRectF(0, 0, 1400, 1000), sheet_rect_for(canvas)
            )
        finally:
            painter.end()
        return image

    with offscreen_canvas(sample_state(), command="test-pixel-roundtrip") as (
        canvas,
        service,
    ):
        before = render(canvas)
        path = tmp_path / "mixed.cdxml"
        service.save_to_file(str(path))
        service.apply_state(read_document(path).state)
        assert render(canvas) == before


def test_visual_projection_keeps_native_molecule_paint_order():
    from chemvas.bootstrap.web_adapter import edit_document, new_document

    state = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
    )["document"]["state"]

    def molecule_order(raw):
        fragment = ET.fromstring(raw).find("./page/fragment")
        assert fragment is not None
        return [
            e.tag
            for e in sorted(
                (e for e in fragment.iter() if "Z" in e.attrib),
                key=lambda e: int(e.attrib["Z"]),
            )
        ]

    with offscreen_canvas(state, command="test-mixed-paint-order") as (canvas, service):
        before = molecule_order(
            serialize_cdxml_document(canvas, service.snapshot_state())
        )
        state["orbitals"] = sample_state()["orbitals"]
        service.apply_state(state)
        after = molecule_order(
            serialize_cdxml_document(canvas, service.snapshot_state())
        )
        assert after == before
