from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from chemvas.features.export import (
    inspect_cdxml_roundtrip,
    recover_native_cdxml_palette,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/native_cdxml_roundtrip.json").read_text()
)
APP = Path(__file__).parents[1] / "app"


def document(*, native=False, gray=(37, 41, 48)):
    table = '<color r="1" g="1" b="1"/><color r="0" g="0" b="0"/>'
    fmt = ".4f" if native else ".17g"
    table += (
        "<color "
        + " ".join(
            f'{key}="{format(n / 255, fmt)}"'
            for key, n in zip("rgb", gray, strict=True)
        )
        + "/>"
    )
    return (
        '<?xml version="1.0"?><CDXML CreationProgram="ChemDraw 25.0.2.14">'
        '<fonttable><font id="0" name="Arial"/></fonttable>'
        f"<colortable>{table}</colortable>"
        '<page id="1"><graphic id="2" color="4" GraphicType="Rectangle"/>'
        '<t id="3" p="0 0"><s font="0" size="12" color="4">Caption</s></t>'
        "</page><!-- preserve this byte-for-byte --></CDXML>"
    ).encode()


@pytest.mark.parametrize("case", FIXTURE["grayscale"])
def test_profile_predicts_actual_native_reopened_grayscale(case):
    n = case["channel"]
    report = inspect_cdxml_roundtrip(document(gray=(n, n, n)))
    row = report["palette"][2]
    assert row["modeled_native_reopen_rgb8"] == case["actual_reopened_rgb"]
    assert report["nearest_stable_colors_applied"] is False
    assert report["full_fidelity_accepted"] is False


@pytest.mark.parametrize("case", FIXTURE["font_encodings"])
def test_native_encoding_fixture_keeps_font_changes_visible(case):
    report = inspect_cdxml_roundtrip(
        case["producer_xml"].encode(), case["native_xml"].encode()
    )
    fonts = report["fonts"]
    assert fonts["physical_face_identity_verified"] is False
    assert not fonts["missing_text_paths"] and not fonts["extra_text_paths"]
    if case["family"] == "Arial":
        assert fonts["changed_text_objects"] == []
    else:
        [change] = fonts["changed_text_objects"]
        assert change["font_pairs"] == [[case["family"], "Arial"]]
        assert change["changed_font_characters"] == len("FPh / OMe")
        assert change["changed_face_characters"] == 0


def test_recovery_preserves_non_palette_bytes_and_exact_authored_rgb():
    source, native = document(), document(native=True)
    output, report = recover_native_cdxml_palette(source, native)
    before_start, before_end = native.split(b"<colortable>")
    after_start, after_end = output.split(b"<colortable>")
    assert before_start == after_start
    assert before_end.split(b"</colortable>")[1] == after_end.split(b"</colortable>")[1]
    color = ET.fromstring(output).findall("colortable/color")[2]
    assert [round(float(color.get(k)) * 255) for k in "rgb"] == [37, 41, 48]
    assert color.get("b") == format(48 / 255, ".17g")
    assert report["recovery"]["paired_logical_paint_colors_match_producer"] is True
    assert report["recovery"]["required_after_each_native_save"] is True
    assert report["full_fidelity_accepted"] is False


def test_palette_reindexing_is_allowed_only_with_matching_object_colors():
    source = document().replace(
        b"</colortable>", b'<color r="1" g="0" b="0"/></colortable>'
    )
    native = document(native=True)
    gray = b'<color r="0.1451" g="0.1608" b="0.1882"/>'
    native = native.replace(gray, b'<color r="1" g="0" b="0"/>' + gray)
    with pytest.raises(ValueError, match="changed object color"):
        recover_native_cdxml_palette(source, native)
    native = native.replace(b'color="4"', b'color="5"')
    output, _ = recover_native_cdxml_palette(source, native)
    assert ET.fromstring(output).find(".//graphic").get("color") == "5"
    assert ET.fromstring(output).findall("colortable/color")[2].get("r") == "1"


@pytest.mark.parametrize(
    "before,after,error",
    [
        (b'color="4" GraphicType', b'color="0" GraphicType', "changed object color"),
        (b'color="4">Caption', b'color="1">Caption', "changed text color"),
        (b">Caption<", b">Changed<", "changed text content"),
        (b'id="2"', b'id="8"', "changed object inventory"),
        (b'r="0.1451"', b'r="0.1452"', "exact measured native serialization"),
        (b"25.0.2.14", b"26.0.0.0", "measured ChemDraw"),
    ],
)
def test_recovery_refuses_real_changes_or_unmeasured_writer(before, after, error):
    native = document(native=True).replace(before, after)
    with pytest.raises(ValueError, match=error):
        recover_native_cdxml_palette(document(), native)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-0.1", "1.1", "no"])
def test_non_numeric_or_out_of_range_palette_is_rejected(value):
    source = document().replace(b'r="1"', f'r="{value}"'.encode(), 1)
    with pytest.raises(ValueError, match="palette"):
        inspect_cdxml_roundtrip(source)


def test_repeated_native_color_loss_is_not_hidden_by_palette_membership():
    source = document().replace(
        b"</colortable>",
        (
            '<color r="0.14509803921568629" g="0.16078431372549021" '
            f'b="{47 / 255:.17g}"/></colortable>'
        ).encode(),
    )
    degraded = document(native=True).replace(b'b="0.1882"', b'b="0.1843"')
    with pytest.raises(ValueError, match="changed object color"):
        recover_native_cdxml_palette(source, degraded)


def test_noncanonical_producer_requires_actual_original_values():
    with pytest.raises(ValueError, match="canonical eight-bit"):
        inspect_cdxml_roundtrip(document(native=True))


def _cli(tmp_path, *args):
    poison = tmp_path / "PyQt6"
    poison.mkdir(exist_ok=True)
    (poison / "__init__.py").write_text("raise AssertionError('loaded Qt')\n")
    return subprocess.run(
        [sys.executable, "-m", "chemvas", "review-cdxml", *map(str, args)],
        env=os.environ | {"PYTHONPATH": os.pathsep.join([str(tmp_path), str(APP)])},
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_product_cli_repairs_without_qt_and_never_overwrites_inputs(tmp_path):
    source, native, output = [
        tmp_path / n for n in ["정본.cdxml", "native.cdxml", "out.cdxml"]
    ]
    source.write_bytes(document())
    native.write_bytes(document(native=True))
    result = _cli(tmp_path, source, "--native", native, "--recover-palette", output)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["recovery"]["output_format"] == "CDXML"
    assert (
        output.read_bytes()
        == recover_native_cdxml_palette(document(), document(native=True))[0]
    )
    for occupied in [output, source, native]:
        before = occupied.read_bytes()
        refused = _cli(
            tmp_path, source, "--native", native, "--recover-palette", occupied
        )
        assert refused.returncode == 2 and "already exists" in refused.stderr
        assert occupied.read_bytes() == before
    assert source.read_bytes() == document()
    assert native.read_bytes() == document(native=True)


def test_product_cli_reports_font_change_without_accepting_it(tmp_path):
    case = FIXTURE["font_encodings"][0]
    source, native = tmp_path / "source.cdxml", tmp_path / "native.cdxml"
    source.write_text(case["producer_xml"])
    native.write_text(case["native_xml"])
    result = _cli(tmp_path, source, "--native", native)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["fonts"]["changed_text_objects"]
    assert report["full_fidelity_accepted"] is False


def test_product_cli_refuses_missing_native_without_creating_output(tmp_path):
    source, output = tmp_path / "source.cdxml", tmp_path / "out.cdxml"
    source.write_bytes(document())
    result = _cli(tmp_path, source, "--recover-palette", output)
    assert result.returncode == 2 and "requires --native" in result.stderr
    assert not output.exists()
