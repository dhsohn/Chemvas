"""Malformed reference RGB must fail at input validation, before quantization."""

import xml.etree.ElementTree as ET

import pytest

from chemvas.features.export import (
    inspect_cdxml_roundtrip,
    recover_native_cdxml_palette,
)
from tests.test_cdxml_roundtrip_workflow import _cli, document


def invalid_native(channel, value):
    root = ET.fromstring(document(native=True))
    root.findall("colortable/color")[2].set(channel, value)
    return ET.tostring(root)


@pytest.mark.parametrize("channel", list("rgb"))
@pytest.mark.parametrize(
    "value", ["1e308", "-1e308", "1.0001", "-0.0001", "NaN", "Infinity"]
)
@pytest.mark.parametrize(
    "operation", [inspect_cdxml_roundtrip, recover_native_cdxml_palette]
)
def test_native_channels_are_validated_before_color_comparison(
    channel, value, operation
):
    with pytest.raises(ValueError, match="within 0..1|finite"):
        operation(document(), invalid_native(channel, value))


@pytest.mark.parametrize("value", ["1e308", "-1e308", "1.0001"])
@pytest.mark.parametrize("destination", ["new", "existing", "source", "native"])
def test_cli_invalid_reference_is_clear_and_preserves_every_file(
    tmp_path, value, destination
):
    source, native, output = [
        tmp_path / n for n in ("source.cdxml", "native.cdxml", "out.cdxml")
    ]
    source_bytes, native_bytes = document(), invalid_native("r", value)
    source.write_bytes(source_bytes)
    native.write_bytes(native_bytes)
    if destination == "existing":
        output.write_bytes(b"existing output")
    target = {"source": source, "native": native}.get(destination, output)
    before = {p: p.read_bytes() for p in tmp_path.glob("*.cdxml")}
    result = _cli(tmp_path, source, "--native", native, "--recover-palette", target)
    assert result.returncode == 2
    assert "chemvas: error:" in result.stderr and "within 0..1" in result.stderr
    assert "Traceback" not in result.stderr and result.stdout == ""
    assert {p: p.read_bytes() for p in tmp_path.glob("*.cdxml")} == before
    if destination != "existing":
        assert not output.exists()
    assert source.read_bytes() == source_bytes and native.read_bytes() == native_bytes


def test_cli_inspection_rejects_oversized_native_channel_without_traceback(tmp_path):
    source, native = tmp_path / "source.cdxml", tmp_path / "native.cdxml"
    source.write_bytes(document())
    native.write_bytes(invalid_native("b", "1e308"))
    before = native.read_bytes()
    result = _cli(tmp_path, source, "--native", native)
    assert result.returncode == 2 and "within 0..1" in result.stderr
    assert "Traceback" not in result.stderr and result.stdout == ""
    assert native.read_bytes() == before
