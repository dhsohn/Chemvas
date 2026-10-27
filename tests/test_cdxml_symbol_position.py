"""Native CDXML symbol coordinate semantics."""

import xml.etree.ElementTree as ET

import pytest

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document

PAGE_OFFSET = (300, 350)
FIRST = (130, 240)
SECOND = (131, 241)


def native_symbol(symbol: str) -> bytes:
    return f"""<CDXML>
    <page id="1" BoundingBox="100 200 500 500" Width="400" Height="300">
      <graphic id="2" GraphicType="Symbol" SymbolType="{symbol}"
       BoundingBox="{FIRST[0]} {FIRST[1]} {SECOND[0]} {SECOND[1]}"/>
    </page>
    </CDXML>""".encode()


@pytest.mark.parametrize("symbol", ["CirclePlus", "CircleMinus", "Plus", "Minus"])
def test_symbol_image_center_uses_first_bounding_box_point(symbol):
    state = parse_cdxml_document(native_symbol(symbol), preserve_source=True).state
    image = state["images"][0]

    assert image["x"] + image["width"] / 2 == FIRST[0] - PAGE_OFFSET[0]
    assert image["y"] + image["height"] / 2 == FIRST[1] - PAGE_OFFSET[1]


def test_symbol_save_preserves_original_bounding_box():
    state = parse_cdxml_document(native_symbol("Plus"), preserve_source=True).state

    root = ET.fromstring(update_native_document(state))

    assert root.find(".//graphic").get("BoundingBox") == "130 240 131 241"


def test_symbol_translation_shifts_bounding_box_and_reimported_center():
    state = parse_cdxml_document(
        native_symbol("CirclePlus"), preserve_source=True
    ).state
    image = state["images"][0]
    image["x"] += 19
    image["y"] -= 7

    root = ET.fromstring(update_native_document(state))
    assert root.find(".//graphic").get("BoundingBox") == "149 233 150 234"

    moved = parse_cdxml_document(ET.tostring(root), preserve_source=True).state
    moved_image = moved["images"][0]
    assert moved_image["x"] + moved_image["width"] / 2 == (
        FIRST[0] + 19 - PAGE_OFFSET[0]
    )
    assert moved_image["y"] + moved_image["height"] / 2 == (
        FIRST[1] - 7 - PAGE_OFFSET[1]
    )
