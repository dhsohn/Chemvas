"""Synthetic consumer metrics through the real public rendering command.

These fixtures test the explicit measurement contract, not native font rendering.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.bootstrap import document_render as cli
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.export.cdxml_consumer_validation import validate_consumer_objects

pytestmark = pytest.mark.usefixtures("qt_application")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _render(source, output, sidecar=None, *, width=170):
    args = [
        "render-document",
        str(source),
        "--output",
        str(output),
        "--width-mm",
        str(width),
    ]
    if sidecar is not None:
        args += ["--cdxml-layout-reference", str(sidecar)]
    return cli.run(args)


def _fixture(tmp_path, capsys, *, rotated=False):
    source = tmp_path / "source.chemvas"
    notes = [
        {"text": "A_A\n-1.0", "x": 20, "y": 20},
        {"text": "A_B\n-2.0", "x": 65, "y": 20},
        {"text": "anchor", "x": 250, "y": 180},
    ]
    if rotated:
        notes = [
            {"text": "rotated note", "x": 20, "y": 90, "rotation": -90},
            {"text": "anchor", "x": 250, "y": 180},
        ]
    state = {
        "model": serialize_model_state(
            MoleculeModel(
                atoms={
                    0: Atom("O", 20, 130, explicit_label=True),
                    1: Atom("C", 50, 130, explicit_label=True),
                },
                bonds=[Bond(0, 1)],
            )
        ),
        "notes": notes,
        "ring_fills": [],
        "marks": [],
        "arrows": [{"kind": "line", "start": [20, 150], "end": [50, 150]}],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }
    write_document(source, state, CANVAS_FILE_VERSION)
    producer = tmp_path / "before.cdxml"
    assert _render(source, producer, width=40 if rotated else 170) == 0
    capsys.readouterr()
    root = ET.fromstring(producer.read_bytes())
    native = deepcopy(root)
    texts = native.findall("./page/t")
    for t in texts:
        x, y = map(float, t.get("p").split())
        t.set("BoundingBox", f"{x} {y - 10} {x + 20} {y + 2}")
    if rotated:
        page = root.find("page")
        texts[0].set("BoundingBox", f"5 -6 20 {float(page.get('Height')) - 20}")
    else:
        second_x = float(texts[2].get("p").split()[0])
        x, y = map(float, texts[0].get("p").split())
        texts[0].set("BoundingBox", f"{x} {y - 10} {second_x + 2} {y + 2}")
    consumer = tmp_path / "consumer.cdxml"
    consumer.write_bytes(ET.tostring(native))
    payload = dict(
        version=2,
        producer_sha256=_hash(producer.read_bytes()),
        export_options={
            "format": "cdxml",
            "scope": "sheet",
            "sizing": "bond",
            "background": "white",
            "dpi": 300,
            "width_mm": 40 if rotated else 170,
            "max_height_mm": None,
            "min_font_pt": None,
        },
        label_bindings_sha256=None,
        producer_frame=list(map(float, root.find("page").get("BoundingBox").split())),
        consumer_frame=list(map(float, native.find("page").get("BoundingBox").split())),
        font_mapping={
            f.get("name"): f.get("name") for f in root.findall("./fonttable/font")
        },
        consumer_environment={
            "creation_program": "Chemvas",
            "platform": "synthetic test",
            "executable_sha256": "1" * 64,
        },
        source_sha256=_hash(source.read_bytes()),
        consumer_sha256=_hash(consumer.read_bytes()),
        consumer_file=consumer.name,
        notes=[0] if rotated else [0, 1],
    )
    sidecar = tmp_path / "layout.json"
    sidecar.write_text(json.dumps(payload))
    return source, producer, consumer, sidecar, payload


def test_caption_and_value_move_together_preserving_fixed_page_and_text(
    tmp_path, capsys
):
    source, before, consumer, sidecar, _ = _fixture(tmp_path, capsys)
    source_bytes = source.read_bytes()
    native_bytes = consumer.read_bytes()
    output = tmp_path / "after.cdxml"
    assert _render(source, output, sidecar) == 0
    report = json.loads(capsys.readouterr().out)
    original = ET.fromstring(before.read_bytes())
    corrected = ET.fromstring(output.read_bytes())
    a, b = original.findall("./page/t"), corrected.findall("./page/t")
    shifts = []
    for index, (left, right) in enumerate(zip(a, b, strict=True)):
        xy_a, xy_b = [list(map(float, t.get("p").split())) for t in (left, right)]
        if index in (2, 3):
            shifts.append(xy_b[0] - xy_a[0])
            assert xy_b[1] == xy_a[1]
            right.set("p", left.get("p"))
        assert ET.tostring(left) == ET.tostring(right)
    assert shifts[0] > 2
    assert shifts[0] == pytest.approx(shifts[1])
    assert ET.tostring(original) == ET.tostring(corrected)
    assert report["width_points"] == pytest.approx(170 * 72 / 25.4)
    assert report["cdxml_layout_reference"]["consumer_sha256"] == _hash(native_bytes)
    assert source.read_bytes() == source_bytes
    assert consumer.read_bytes() == native_bytes
    repeated = tmp_path / "default-again.cdxml"
    assert _render(source, repeated) == 0
    assert repeated.read_bytes() == before.read_bytes()


def test_rotated_note_uses_existing_page_margin_without_resizing(tmp_path, capsys):
    source, before, _, sidecar, _ = _fixture(tmp_path, capsys, rotated=True)
    output = tmp_path / "after.cdxml"
    assert _render(source, output, sidecar, width=40) == 0
    original = ET.fromstring(before.read_bytes())
    corrected = ET.fromstring(output.read_bytes())
    a, b = original.find("./page/t"), corrected.find("./page/t")
    ax, ay = map(float, a.get("p").split())
    bx, by = map(float, b.get("p").split())
    assert bx == ax
    assert by - ay == pytest.approx(6 + 72 / 25.4 + 0.02)
    b.set("p", a.get("p"))
    assert ET.tostring(original) == ET.tostring(corrected)


def _mutate_review_case(change, root, text, payload):
    if change == "producer_hash":
        payload["producer_sha256"] = "0" * 64
    elif change == "export_options":
        payload["export_options"]["width_mm"] = 160
    elif change == "label_hash":
        payload["label_bindings_sha256"] = "0" * 64
    elif change == "producer_frame":
        payload["producer_frame"][2] = 1
    elif change == "consumer_frame":
        root.find("page").set("BoundingBox", "0 0 1 1")
    elif change == "consumer_frame_rebound":
        root.find("page").set("BoundingBox", "0 0 1 1")
        payload["consumer_frame"] = [0, 0, 1, 1]
    elif change == "font_name":
        root.find("./fonttable/font").set("name", "Different Font")
    elif change == "font_id":
        text.find("s").set("font", "9999")
    elif change == "justify":
        text.set("Justification", "Right")
    elif change in {"caption_root", "caption_page", "caption_text"}:
        owner = {
            "caption_root": root,
            "caption_page": root.find("page"),
            "caption_text": text,
        }[change]
        owner.set("CaptionJustification", "Right")
    elif change in {"label_root", "label_page", "label_text"}:
        # Exercise inherited alignment, rather than an unchanged explicit override.
        if change != "label_text":
            for label in root.findall(".//n/t"):
                label.attrib.pop("LabelJustification", None)
        owner = {
            "label_root": root,
            "label_page": root.find("page"),
            "label_text": root.find(".//n/t"),
        }[change]
        owner.set("LabelJustification", "Right")
    elif change == "added_hydrogens":
        node = root.find(".//n")
        assert "NumHydrogens" not in node.attrib
        node.set("NumHydrogens", "9")
    elif change == "arrowhead":
        root.find(".//arrow").set("ArrowheadHead", "Full")
    elif change == "node_element":
        root.find(".//n").set("Element", "18")
    elif change == "node_position":
        root.find(".//n").set("p", "0 0")
    elif change == "bond_endpoint":
        root.find(".//b").set("E", "9999")
    elif change == "bond_order":
        root.find(".//b").set("Order", "2")
    elif change == "atom_label":
        root.find(".//n/t/s").text = "altered"
    elif change == "stroke_defaults":
        root.set("LineWidth", "9")
    elif change == "text_interpretation":
        text.set("InterpretChemically", "yes")
    elif change == "environment":
        root.set("CreationProgram", "Another consumer")
    else:
        return False
    return True


@pytest.mark.parametrize(
    "change,match",
    [
        ("source_hash", "source document"),
        ("consumer_hash", "consumer file"),
        ("extra_key", "invalid fields"),
        ("note_missing", "missing or hidden"),
        ("note_bool", "distinct note indices"),
        ("note_duplicate", "distinct note indices"),
        ("text", "changed caption text"),
        ("size", "size or face"),
        ("position", "changed caption position"),
        ("rotation", "changed caption rotation"),
        ("wrap", "rewrapped"),
        ("duplicate_id", "duplicate"),
        ("too_wide", "cannot fit"),
        ("nan_box", "finite"),
        ("unselected_collision", "different note selection"),
        ("producer_hash", "uncorrected producer"),
        ("export_options", "export options"),
        ("label_hash", "label bindings"),
        ("producer_frame", "producer frame"),
        ("consumer_frame", "consumer frame"),
        ("consumer_frame_rebound", "cannot fit"),
        ("font_name", "expected font mapping"),
        ("font_id", "undefined font ID"),
        ("justify", "justification"),
        ("caption_root", "justification"),
        ("caption_page", "justification"),
        ("caption_text", "justification"),
        ("label_root", "justification"),
        ("label_page", "justification"),
        ("label_text", "justification"),
        ("added_hydrogens", "hydrogen count"),
        ("arrowhead", "arrow semantics"),
        ("node_element", "semantics or topology"),
        ("node_position", "n geometry"),
        ("bond_endpoint", "semantics or topology"),
        ("bond_order", "semantics or topology"),
        ("atom_label", "caption text"),
        ("environment", "consumer environment"),
        ("stroke_defaults", "drawing scale or stroke defaults"),
        ("text_interpretation", "text interpretation"),
    ],
)
def test_invalid_measurement_refuses_without_writing(tmp_path, capsys, change, match):
    source, _, consumer, sidecar, payload = _fixture(tmp_path, capsys)
    root = ET.fromstring(consumer.read_bytes())
    text = root.find("./page/t")
    if _mutate_review_case(change, root, text, payload):
        pass
    elif change == "source_hash":
        payload["source_sha256"] = "0" * 64
    elif change == "extra_key":
        payload["unknown"] = 1
    elif change == "note_missing":
        payload["notes"] = [9]
    elif change == "note_bool":
        payload["notes"] = [True]
    elif change == "note_duplicate":
        payload["notes"] = [0, 0]
    elif change == "unselected_collision":
        payload["notes"] = [0]
    elif change == "text":
        text.find("s").text = "changed"
    elif change == "size":
        text.find("s").set("size", "100")
    elif change == "position":
        text.set("p", "10 10")
    elif change == "rotation":
        text.set("RotationAngle", "65536")
    elif change == "wrap":
        text.set("LineStarts", "2")
    elif change == "duplicate_id":
        root.find("page").append(deepcopy(text))
    elif change == "too_wide":
        text.set("BoundingBox", "0 0 10000 30")
    elif change == "nan_box":
        text.set("BoundingBox", "NaN 0 20 30")
    consumer.write_bytes(ET.tostring(root))
    payload["consumer_sha256"] = _hash(consumer.read_bytes())
    if change == "consumer_hash":
        payload["consumer_sha256"] = "0" * 64
    sidecar.write_text(json.dumps(payload))
    output = tmp_path / "after.cdxml"
    source_bytes = source.read_bytes()
    with pytest.raises(SystemExit) as error:
        _render(source, output, sidecar)
    assert error.value.code == 2
    assert match in capsys.readouterr().err
    assert not output.exists()
    assert source.read_bytes() == source_bytes


def test_reference_rejects_other_formats_and_existing_destination(tmp_path, capsys):
    source, _, _, sidecar, _ = _fixture(tmp_path, capsys)
    output = tmp_path / "after.svg"
    with pytest.raises(SystemExit):
        _render(source, output, sidecar)
    assert "CDXML output only" in capsys.readouterr().err
    assert not output.exists()
    output = tmp_path / "after.cdxml"
    output.write_bytes(b"keep existing")
    with pytest.raises(SystemExit):
        _render(source, output, sidecar)
    assert "already exists" in capsys.readouterr().err
    assert output.read_bytes() == b"keep existing"


def test_post_collision_margin_refuses_even_when_box_is_inside_page(tmp_path, capsys):
    source, before, consumer, sidecar, payload = _fixture(tmp_path, capsys)
    first = tmp_path / "first.cdxml"
    assert _render(source, first, sidecar) == 0
    original = ET.fromstring(before.read_bytes()).findall("./page/t")
    corrected = ET.fromstring(first.read_bytes()).findall("./page/t")
    shift = float(corrected[2].get("p").split()[0]) - float(
        original[2].get("p").split()[0]
    )
    root = ET.fromstring(consumer.read_bytes())
    texts = root.findall("./page/t")
    first_box = list(map(float, texts[0].get("BoundingBox").split()))
    second_box = list(map(float, texts[2].get("BoundingBox").split()))
    width = payload["producer_frame"][2]
    # Increase the left caption so restoring its source gap would leave the
    # right caption only 0.01 pt inside the page. Both boxes fit before reflow.
    first_box[2] += width - 0.01 - (second_box[2] + shift)
    texts[0].set("BoundingBox", " ".join(map(str, first_box)))
    consumer.write_bytes(ET.tostring(root))
    payload["consumer_sha256"] = _hash(consumer.read_bytes())
    sidecar.write_text(json.dumps(payload))
    capsys.readouterr()
    output = tmp_path / "too-tight.cdxml"
    with pytest.raises(SystemExit):
        _render(source, output, sidecar)
    assert "cannot fit the fixed page" in capsys.readouterr().err
    assert not output.exists()


def test_explicit_substitution_is_reported_and_never_claimed_as_font_identity(
    tmp_path, capsys
):
    source, _, consumer, sidecar, payload = _fixture(tmp_path, capsys)
    root = ET.fromstring(consumer.read_bytes())
    for font in root.findall("./fonttable/font"):
        old = font.get("name")
        font.set("name", "Declared substitute")
        payload["font_mapping"][old] = "Declared substitute"
    consumer.write_bytes(ET.tostring(root))
    payload["consumer_sha256"] = _hash(consumer.read_bytes())
    sidecar.write_text(json.dumps(payload))
    assert _render(source, tmp_path / "after.cdxml", sidecar) == 0
    report = json.loads(capsys.readouterr().out)["cdxml_layout_reference"]
    assert report["experimental"] is True
    assert report["font_substitution_declared"] is True
    assert report["environment_runtime_verified"] is False


def test_color_table_keeps_eight_bit_channels_without_decimal_truncation():
    from chemvas.ui.export.export_cdxml import _ColorTable

    table = _ColorTable()
    for channel in range(256):
        table.index_for(f"#{channel:02x}{channel:02x}{channel:02x}")
    for channel, color in enumerate(table.to_element()):
        for component in ("r", "g", "b"):
            value = float(color.get(component))
            assert value == channel / 255.0
            assert round(value * 255) == channel


def test_native_dropped_atom_label_ids_preserve_each_label(tmp_path, capsys):
    source, _, consumer, sidecar, payload = _fixture(tmp_path, capsys)
    root = ET.fromstring(consumer.read_bytes())
    labels = root.findall(".//n/t")
    assert len(labels) == 2
    for label in labels:
        label.attrib.pop("id")
    consumer.write_bytes(ET.tostring(root))
    payload["consumer_sha256"] = _hash(consumer.read_bytes())
    sidecar.write_text(json.dumps(payload))
    assert _render(source, tmp_path / "accepted.cdxml", sidecar) == 0
    capsys.readouterr()
    labels[0].find("s").text = "N"
    consumer.write_bytes(ET.tostring(root))
    payload["consumer_sha256"] = _hash(consumer.read_bytes())
    sidecar.write_text(json.dumps(payload))
    output = tmp_path / "rejected.cdxml"
    with pytest.raises(SystemExit) as error:
        _render(source, output, sidecar)
    assert error.value.code == 2
    assert not output.exists()
    assert "changed caption text" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["caption", "label"])
@pytest.mark.parametrize("scope", ["root", "page", "text"])
def test_specific_justification_overrides_legacy_at_each_scope(
    tmp_path, capsys, kind, scope
):
    _, producer, _, _, _ = _fixture(tmp_path, capsys)
    original = ET.fromstring(producer.read_bytes())
    key = "CaptionJustification" if kind == "caption" else "LabelJustification"
    selector = "./page/t" if kind == "caption" else ".//n/t"
    for text in original.findall(selector):
        text.attrib.pop(key, None)
    reference = deepcopy(original)
    original.set(key, "Left")
    target = reference.find(selector)
    owner = {"root": reference, "page": reference.find("page"), "text": target}[scope]
    # Apply the same effective alignment to all text of this category.
    reference.set(key, "Left")
    owner.set(key, "Left")
    target.set("Justification", "Right")
    fonts = {f.get("name"): f.get("name") for f in original.findall("./fonttable/font")}
    validate_consumer_objects(original, reference, fonts)
    owner.set(key, "Right")
    with pytest.raises(ValueError, match="changed text justification"):
        validate_consumer_objects(original, reference, fonts)


def test_removed_explicit_hydrogen_count_is_rejected(tmp_path, capsys):
    _, producer, _, _, _ = _fixture(tmp_path, capsys)
    original = ET.fromstring(producer.read_bytes())
    original.find(".//n").set("NumHydrogens", "3")
    reference = deepcopy(original)
    reference.find(".//n").attrib.pop("NumHydrogens")
    fonts = {f.get("name"): f.get("name") for f in original.findall("./fonttable/font")}
    with pytest.raises(ValueError, match="changed hydrogen count"):
        validate_consumer_objects(original, reference, fonts)
