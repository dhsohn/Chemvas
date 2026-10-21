from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chemvas.features.export import recover_native_cdxml_palette
from tests.document_file_helpers import read_payload

ROOT = Path(__file__).parents[1]
FIXTURE = read_payload(
    (ROOT / "tests/fixtures/native_cdxml_palette_writer.json").read_text()
)
NATIVE = FIXTURE["native_xml"].encode()
PRODUCER = FIXTURE["producer_xml"].encode()


@pytest.mark.parametrize(
    "red", ["0.14505", "0.14509", "0.145099", "0.14511", "0.14512", "0.14514"]
)
def test_recovery_requires_exact_measured_writer_value(red):
    assert b'r="0.1451"' in NATIVE
    edited = NATIVE.replace(b'r="0.1451"', f'r="{red}"'.encode())
    with pytest.raises(ValueError, match="exact measured native serialization"):
        recover_native_cdxml_palette(PRODUCER, edited)


def test_original_native_first_save_still_recovers_exact_rgb():
    output, report = recover_native_cdxml_palette(PRODUCER, NATIVE)
    assert b'r="0.14509803921568629"' in output
    assert report["recovery"]["provenance_runtime_verified"] is False
    assert report["full_fidelity_accepted"] is False


def test_cli_refuses_review_counterexample_before_creating_output(tmp_path):
    source, native, output = [
        tmp_path / n for n in ("producer.cdxml", "edited.cdxml", "result.cdxml")
    ]
    source.write_bytes(PRODUCER)
    native.write_bytes(NATIVE.replace(b'r="0.1451"', b'r="0.14505"'))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "review-cdxml",
            str(source),
            "--native",
            str(native),
            "--recover-palette",
            str(output),
        ],
        env=os.environ
        | {"PYTHONPATH": os.environ.get("CHEMVAS_REVIEW_APP", str(ROOT / "app"))},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (
        result.returncode == 2
        and "exact measured native serialization" in result.stderr
    )
    assert not output.exists()
    assert source.read_bytes() == PRODUCER
    assert native.read_bytes() == NATIVE.replace(b'r="0.1451"', b'r="0.14505"')
    assert not list(tmp_path.glob(".chemvas-create-*"))


def test_comment_decoy_cannot_capture_actual_color_table():
    decoy = b'<!-- <color r="1" g="1" b="1"/><color r="0" g="0" b="0"/><color r="0.1451" g="0.1608" b="0.1882"/></colortable> -->'
    native = NATIVE.replace(b"<colortable>", b"<colortable>" + decoy, 1)
    output, report = recover_native_cdxml_palette(PRODUCER, native)
    assert decoy in output
    import xml.etree.ElementTree as ET

    colors = ET.fromstring(output).findall("colortable/color")
    assert colors[2].get("r") == format(37 / 255, ".17g")
    assert colors[2].get("b") == format(48 / 255, ".17g")
    assert report["recovery"]["colors"][2]["rgb8"] == [37, 41, 48]


@pytest.mark.parametrize("case", FIXTURE["grayscale_first_save"])
def test_exact_native_first_save_channels_remain_accepted(case):
    import xml.etree.ElementTree as ET

    source, native = ET.fromstring(PRODUCER), ET.fromstring(NATIVE)
    n = case["channel"]
    source.findall("colortable/color")[2].attrib.update(
        {k: format(n / 255, ".17g") for k in "rgb"}
    )
    native.findall("colortable/color")[2].attrib.update(case["native_rgb"])
    output, report = recover_native_cdxml_palette(
        ET.tostring(source), ET.tostring(native)
    )
    actual = ET.fromstring(output).findall("colortable/color")[2]
    assert [actual.get(k) for k in "rgb"] == [format(n / 255, ".17g")] * 3
    assert report["recovery"]["output_palette_verified"] is True
    assert report["recovery"]["exact_native_serialization_verified"] is True


def test_quoted_attribute_decoys_are_preserved():
    note = b' data-note=\'r="0.5" g="0.7" b="0.8" >\''
    native = NATIVE.replace(b'<color r="0.1451"', b"<color" + note + b' r="0.1451"')
    output, report = recover_native_cdxml_palette(PRODUCER, native)
    assert note in output
    assert report["recovery"]["output_palette_verified"] is True


def test_utf8_bom_and_multibyte_comment_preserve_byte_positions():
    comment = "<!-- 한글 주석: <color r='0.9'/> -->".encode()
    native = b"\xef\xbb\xbf" + NATIVE.replace(
        b"<colortable>", comment + b"<colortable>", 1
    )
    output, report = recover_native_cdxml_palette(PRODUCER, native)
    assert output.startswith(b"\xef\xbb\xbf") and comment in output
    assert report["recovery"]["output_palette_verified"] is True


def test_conflicting_encoding_is_a_clean_refusal():
    native = NATIVE.replace(b'encoding="UTF-8"', b'encoding="UTF-16"')
    assert native != NATIVE
    with pytest.raises(ValueError, match="Native CDXML byte parsing failed"):
        recover_native_cdxml_palette(PRODUCER, native)


def test_comment_decoy_cli_changes_actual_palette_and_preserves_comment(tmp_path):
    import xml.etree.ElementTree as ET

    decoy = b'<!-- <color r="1" g="1" b="1"/><color r="0" g="0" b="0"/><color r="0.1451" g="0.1608" b="0.1882"/></colortable> -->'
    changed = NATIVE.replace(b"<colortable>", b"<colortable>" + decoy, 1)
    source, native, output = [
        tmp_path / n for n in ("producer.cdxml", "comment.cdxml", "result.cdxml")
    ]
    source.write_bytes(PRODUCER)
    native.write_bytes(changed)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "review-cdxml",
            str(source),
            "--native",
            str(native),
            "--recover-palette",
            str(output),
        ],
        env=os.environ
        | {"PYTHONPATH": os.environ.get("CHEMVAS_REVIEW_APP", str(ROOT / "app"))},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    actual = ET.fromstring(output.read_bytes()).findall("colortable/color")[2]
    assert [actual.get(k) for k in "rgb"] == [
        format(n / 255, ".17g") for n in (37, 41, 48)
    ]
    assert decoy in output.read_bytes()
    assert source.read_bytes() == PRODUCER and native.read_bytes() == changed
    assert json.loads(result.stdout)["recovery"]["output_palette_verified"] is True


@pytest.mark.parametrize("kind", ["symlink", "dangling_symlink", "hardlink"])
def test_cli_never_replaces_existing_output_aliases(tmp_path, kind):
    source, native, output = [
        tmp_path / n for n in ("producer.cdxml", "first.cdxml", "result.cdxml")
    ]
    source.write_bytes(PRODUCER)
    native.write_bytes(NATIVE)
    if kind == "hardlink":
        os.link(source, output)
    else:
        output.symlink_to(source if kind == "symlink" else tmp_path / "missing.cdxml")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "review-cdxml",
            str(source),
            "--native",
            str(native),
            "--recover-palette",
            str(output),
        ],
        env=os.environ
        | {"PYTHONPATH": os.environ.get("CHEMVAS_REVIEW_APP", str(ROOT / "app"))},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2 and "already exists" in result.stderr
    assert source.read_bytes() == PRODUCER and native.read_bytes() == NATIVE
    assert not list(tmp_path.glob(".chemvas-create-*"))
    if kind != "hardlink":
        assert output.is_symlink()
    assert not (tmp_path / "missing.cdxml").exists()
