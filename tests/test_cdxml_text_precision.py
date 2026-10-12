"""Native text precision and shared trailing-glyph placement."""

import xml.etree.ElementTree as ET

import pytest

from chemvas.ui.export.export_cdxml import CdxmlUnsupportedObjectError, _font_size_attr
from tests.test_cdxml_export import _export_cdxml, _simple_state


@pytest.mark.parametrize(
    "size,expected",
    [
        (8.2437732235, "8.25"),
        (10.011, "10"),
        (10.026, "10.05"),
        (0.025, "0.05"),
        (9.999, "10"),
        (12.075, "12.1"),
    ],
)
def test_native_font_size_uses_nearest_twentieth(size, expected):
    assert _font_size_attr(size) == expected
    assert abs(float(expected) - size) <= 0.02500001


@pytest.mark.parametrize("size", [0, -1, float("nan"), float("inf"), 0.001, 4000])
def test_unrepresentable_font_size_is_refused(size):
    with pytest.raises(CdxmlUnsupportedObjectError):
        _font_size_attr(size)


@pytest.mark.usefixtures("qt_application")
def test_real_scaled_labels_and_captions_have_native_representable_size():
    state = _simple_state(notes=[{"x": 50.0, "y": 60.0, "text": "Caption"}])
    data, _ = _export_cdxml(state, target_width_mm=84.0)
    runs = ET.fromstring(data).findall(".//s")
    assert len(runs) >= 2
    assert all(
        abs(float(run.get("size")) * 20 - round(float(run.get("size")) * 20)) < 1e-8
        for run in runs
    )
