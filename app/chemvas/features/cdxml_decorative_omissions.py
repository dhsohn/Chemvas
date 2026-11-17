"""Classify standalone, headless native arcs for a partial desktop open."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.features.cdxml_graphics import native_stroke_width

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from chemvas.features.cdxml_preservation import PreservingImporter


# Arc attributes with no role beyond drawing or identifying the object.
_ARC_ATTRIBUTES = frozenset(
    {
        "id",
        "GraphicType",
        "BoundingBox",
        "AngularSize",
        "ArrowType",
        "LineType",
        "LineWidth",
        "BoldWidth",
        "color",
        "bgcolor",
        "Visible",
        "Z",
    }
)
_LINE_TYPES = frozenset({"Solid", "Dashed", "Bold", "Wavy"})
# These known scalar/geometry fields cannot hold references. For other
# attributes, a token matching an arc ID is enough reason to keep that arc.
_NON_REFERENCE_ATTRIBUTES = _ARC_ATTRIBUTES | {
    "p",
    "Head3D",
    "Tail3D",
    "Center3D",
    "MajorAxisEnd3D",
    "MinorAxisEnd3D",
    "CurvePoints",
    "Width",
    "Height",
    "BondLength",
    "Element",
    "Order",
    "Display",
    "LabelFace",
    "ResidueWrapCount",
    "PrintMargins",
    "RxnAutonumberStart",
    "HeaderPosition",
    "FooterPosition",
    "HeightPages",
    "WidthPages",
    "r",
    "g",
    "b",
    "LineHeight",
    "CaptionLineHeight",
    "BondSpacing",
    "ChainAngle",
    "font",
    "size",
    "face",
    "CaptionFont",
    "CaptionSize",
    "LabelFont",
    "LabelSize",
}


def omit_decorative_arcs(reader: PreservingImporter) -> int:
    candidates = [
        element
        for element in reader.page.iter("graphic")
        if _standalone_headless_arc(reader, element)
    ]
    if not candidates:
        return 0
    ids = {element.attrib["id"] for element in candidates}
    referenced = {
        token
        for element in reader.root.iter()
        for key, value in element.attrib.items()
        if key not in _NON_REFERENCE_ATTRIBUTES
        for token in value.split()
        if token in ids
    }
    for element in candidates:
        if element.attrib["id"] in referenced:
            reader.unsupported(element, "referenced arc cannot be omitted safely")
        coordinates = [
            reader.number(value, element)
            for value in element.get("BoundingBox", "").split()
        ]
        if len(coordinates) != 4 or coordinates[:2] == coordinates[2:]:
            reader.unsupported(element, "graphic bounds")
        reader.number(element.get("AngularSize", "0"), element)
        reader.number(element.get("Z", "0"), element)
        reader.color(element)
        if "bgcolor" in element.attrib:
            reader.color(element, "bgcolor")
        width = reader.number(reader.inherited(element, "LineWidth", "0.6"), element)
        if not 0 < width <= 100:
            reader.unsupported(element, "line width")
        native_stroke_width(reader, element, width)
    for element in candidates:
        reader.parents.pop(element).remove(element)
    return len(candidates)


def _standalone_headless_arc(reader: PreservingImporter, element: ET.Element) -> bool:
    if (
        element.get("GraphicType") != "Arc"
        or element.get("ArrowType", "NoHead") != "NoHead"
        or not set(element.attrib) <= _ARC_ATTRIBUTES
        or len(element)
        or (element.text and element.text.strip())
        or not element.get("id")
        or not set(element.get("LineType", "Solid").split()) <= _LINE_TYPES
        or element.get("Visible", "yes") not in {"yes", "no"}
    ):
        return False
    parent = reader.parents.get(element)
    while parent is not None and parent.tag == "group":
        parent = reader.parents.get(parent)
    return parent is reader.page
