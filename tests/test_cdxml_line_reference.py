"""Native no-head line aliases preserve paint, not arbitrary extra objects."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.features.export.cdxml_consumer_validation import validate_consumer_objects


def _pair():
    a = ET.fromstring(
        '<CDXML LineWidth="0.71"><page id="1"><group id="2">'
        '<arrow id="10" Head3D="80 35 0" Tail3D="10 20 0" '
        'LineWidth="0.65950185788" FillType="None" ArrowheadType="Solid"/>'
        "</group></page></CDXML>"
    )
    b = ET.fromstring(
        '<CDXML LineWidth="0.71"><page id="1"><group id="2">'
        '<graphic id="10" SupersededBy="20" GraphicType="Line" '
        'BoundingBox="80 35 10 20" LineWidth="0.66"/>'
        '<arrow id="20" Head3D="80 35 0" Tail3D="10 20 0" '
        'LineWidth="0.66" FillType="None" ArrowheadType="Solid"/>'
        "</group></page></CDXML>"
    )
    return a, b


def test_narrow_alias_preserves_effective_width_endpoints_and_owner():
    a, b = _pair()
    original = ET.tostring(a), ET.tostring(b)
    validate_consumer_objects(a, b, {})
    assert original == (ET.tostring(a), ET.tostring(b))
    c = deepcopy(b)
    c.find(".//graphic").set("id", "20")
    c.find(".//graphic").set("SupersededBy", "30")
    c.find(".//arrow").set("id", "30")
    validate_consumer_objects(b, c, {})


@pytest.mark.parametrize(
    "mutation",
    [
        "width",
        "head",
        "tail",
        "line_type",
        "head_style",
        "tail_style",
        "fill",
        "angular",
        "color",
        "owner",
        "orphan",
        "wrong_target",
        "cycle",
        "duplicate_alias",
        "extra_arrow",
        "missing_arrow",
        "alias_geometry",
        "alias_width",
        "alias_type",
        "identity",
        "unsupported_paint",
    ],
)
def test_line_alias_never_hides_changed_actual_paint_or_inventory(mutation):
    a, b = _pair()
    arrow, alias = b.find(".//arrow"), b.find(".//graphic")
    fields = {
        "width": ("LineWidth", "1.1"),
        "head": ("Head3D", "81 35 0"),
        "tail": ("Tail3D", "11 20 0"),
        "line_type": ("LineType", "Dashed"),
        "head_style": ("ArrowheadHead", "Full"),
        "tail_style": ("ArrowheadTail", "HalfLeft"),
        "fill": ("FillType", "Solid"),
        "angular": ("AngularSize", "90"),
        "color": ("color", "1"),
        "unsupported_paint": ("ShaftSpacing", "10"),
    }
    if mutation in fields:
        arrow.set(*fields[mutation])
    elif mutation == "owner":
        b.find(".//group").remove(arrow)
        b.find("page").append(arrow)
    elif mutation == "orphan":
        b.find(".//group").remove(alias)
    elif mutation == "wrong_target":
        alias.set("SupersededBy", "99")
    elif mutation == "cycle":
        alias.set("SupersededBy", "10")
    elif mutation == "duplicate_alias":
        other = deepcopy(alias)
        other.set("id", "99")
        b.find(".//group").append(other)
    elif mutation == "extra_arrow":
        other = deepcopy(arrow)
        other.set("id", "99")
        b.find(".//group").append(other)
    elif mutation == "missing_arrow":
        b.find(".//group").remove(arrow)
    elif mutation == "alias_geometry":
        alias.set("BoundingBox", "80 35 10 21")
    elif mutation == "alias_width":
        alias.set("LineWidth", "1.1")
    elif mutation == "alias_type":
        alias.set("GraphicType", "Rectangle")
    elif mutation == "identity":
        alias.set("id", "99")
    with pytest.raises(ValueError):
        validate_consumer_objects(a, b, {})


def test_effective_line_width_cannot_be_changed_by_parent_override():
    a, b = _pair()
    for root in (a, b):
        for item in root.iter():
            item.attrib.pop("LineWidth", None)
    a.find(".//group").set("LineWidth", "0.66")
    b.find(".//group").set("LineWidth", "0.9")
    with pytest.raises(ValueError, match="arrow stroke"):
        validate_consumer_objects(a, b, {})
