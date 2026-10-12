"""Occluding line/fill order is semantic even if native Z numbers change."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.features.export.cdxml_consumer_validation import validate_consumer_objects


def _scene(tail="0 5 0", head="20 5 0"):
    root = ET.fromstring(
        '<CDXML LineWidth="1"><page id="1">'
        '<graphic id="2" GraphicType="Rectangle" RectangleType="Filled" '
        'BoundingBox="15 10 5 0" Z="1"/>'
        '<arrow id="3" Head3D="20 5 0" Tail3D="0 5 0" Z="104" '
        'LineWidth="1" FillType="None" ArrowheadType="Solid"/>'
        "</page></CDXML>"
    )
    root.find(".//arrow").set("Tail3D", tail)
    root.find(".//arrow").set("Head3D", head)
    return root


@pytest.mark.parametrize("z", ["0", "1", "-1"])
def test_overlapping_line_cannot_move_below_fill_or_tie(z):
    a = _scene()
    b = deepcopy(a)
    b.find(".//arrow").set("Z", z)
    with pytest.raises(ValueError, match="paint order"):
        validate_consumer_objects(a, b, {})


def test_native_z_renumbering_preserves_relative_order():
    a = _scene()
    b = deepcopy(a)
    b.find(".//graphic").set("Z", "200")
    b.find(".//arrow").set("Z", "201")
    validate_consumer_objects(a, b, {})


@pytest.mark.parametrize("tail,head", [("0 20 0", "20 20 0"), ("0 0 0", "5 20 0")])
def test_disjoint_ink_order_is_not_constrained_by_bounding_boxes(tail, head):
    a = _scene(tail, head)
    b = deepcopy(a)
    b.find(".//arrow").set("Z", "0")
    validate_consumer_objects(a, b, {})


def test_line_below_fill_cannot_be_brought_to_front():
    a = _scene()
    a.find(".//arrow").set("Z", "0")
    b = deepcopy(a)
    b.find(".//arrow").set("Z", "100")
    with pytest.raises(ValueError, match="paint order"):
        validate_consumer_objects(a, b, {})


@pytest.mark.parametrize("changed", ["line", "fill", "width"])
@pytest.mark.parametrize("reverse", [True, False])
@pytest.mark.parametrize("overlap_scene", ["producer", "consumer"])
def test_one_sided_overlap_after_allowed_geometry_rounding_preserves_order(
    changed, reverse, overlap_scene
):
    a = _scene("0 -0.5025 0", "20 -0.5025 0")
    b = deepcopy(a)
    line = b.find(".//arrow")
    if changed == "line":
        line.set("Tail3D", "0 -0.4925 0")
        line.set("Head3D", "20 -0.4925 0")
    elif changed == "fill":
        b.find(".//graphic").set("BoundingBox", "15 9.99 5 -0.01")
    else:
        line.set("LineWidth", "1.01")
    if overlap_scene == "producer":
        a, b = b, a
    line = b.find(".//arrow")
    line.set("Z", "0" if reverse else "105")
    if reverse:
        with pytest.raises(ValueError, match="paint order"):
            validate_consumer_objects(a, b, {})
    else:
        validate_consumer_objects(a, b, {})
