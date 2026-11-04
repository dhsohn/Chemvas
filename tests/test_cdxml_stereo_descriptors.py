"""Native CDXML saves keep stored CIP descriptors unless an edit can change them.

Synthetic fixture; descriptor values are not recomputed or checked for chemistry.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest

from chemvas.domain.document.cdxml_stereo_descriptors import (
    atom_edit_keeps_stereo,
    bond_edit_keeps_stereo,
)
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document

if TYPE_CHECKING:
    from collections.abc import Callable

# Fragment 2 has a stereocentre (10, wedge 20) whose substituent chain ends in a
# double bond (24). Fragment 3 is a separate structure with its own labels.
NATIVE = b"""<?xml version="1.0"?><CDXML BondLength="20"><page id="1" Width="400" Height="300">
<fragment id="2">
<n id="10" p="100 100" AS="R" CIP="R" Geometry="Tetrahedral" BondOrdering="20 21 22 0"/>
<n id="11" p="117 110" Element="8"><t><s>O</s></t></n>
<n id="12" p="100 80" Geometry="Tetrahedral" BondOrdering="21 23 0 0"/>
<n id="13" p="83 110" Element="7"><t><s>N</s></t></n>
<n id="14" p="117 70"/>
<n id="15" p="117 50"/>
<n id="16" p="134 80"/>
<b id="20" B="10" E="11" Display="WedgeBegin" BS="N" CIP="N"/>
<b id="21" B="10" E="12"/>
<b id="22" B="10" E="13"/>
<b id="23" B="12" E="14"/>
<b id="24" B="14" E="15" Order="2" BS="E" CIP="E"/>
<b id="25" B="14" E="16"/>
</fragment>
<fragment id="3"><n id="30" p="200 100" AS="S" CIP="S"/><n id="31" p="220 100"/>
<b id="32" B="30" E="31" BS="N"/></fragment>
</page></CDXML>"""

DESCRIPTORS = {
    "10": {"AS": "R", "CIP": "R"},
    "20": {"BS": "N", "CIP": "N"},
    "24": {"BS": "E", "CIP": "E"},
}
OTHER_FRAGMENT = {"30": {"AS": "S", "CIP": "S"}, "32": {"BS": "N"}}

# Bond 31 attaches to N (port 21), while bond 30 attaches to C (port 22).
# The outer order deliberately differs from both bond ID and XML order.
# Fragment 102 has an unrelated copy whose mapping and descriptors must survive.
ATTACHMENTS = b"""<CDXML BondLength="20"><page id="1" Width="400" Height="300">
<fragment id="2">
<n id="3" p="60 100" Element="17" Geometry="Linear" BondOrdering="30 0" AS="R" CIP="R"><t><s>Cl</s></t></n>
<n id="4" p="140 100" Element="9"><t><s>F</s></t></n>
<n id="5" p="100 100" NodeType="Fragment" BondOrdering="31 30" Geometry="Linear">
<fragment id="6" ConnectionOrder="21 22">
<n id="7" p="90 100" Element="7" AS="R" CIP="R"/>
<n id="8" p="110 100" Element="6"/>
<n id="21" p="80 100" NodeType="ExternalConnectionPoint"/>
<n id="22" p="120 100" NodeType="ExternalConnectionPoint"/>
<b id="23" B="21" E="7"/><b id="24" B="22" E="8"/>
<b id="25" B="7" E="8"/>
</fragment><t><s>NHCH2</s></t></n>
<b id="30" B="3" E="5" EndAttach="2" BS="N" CIP="N"/>
<b id="31" B="5" E="4"/>
</fragment>
<fragment id="102">
<n id="103" p="240 100" Element="17"><t><s>Cl</s></t></n>
<n id="104" p="320 100" Element="9"><t><s>F</s></t></n>
<n id="105" p="280 100" NodeType="Fragment" BondOrdering="131 130">
<fragment id="106" ConnectionOrder="121 122">
<n id="107" p="270 100" Element="7" AS="S" CIP="S"/>
<n id="108" p="290 100" Element="6"/>
<n id="121" p="260 100" NodeType="ExternalConnectionPoint"/>
<n id="122" p="300 100" NodeType="ExternalConnectionPoint"/>
<b id="123" B="121" E="107"/><b id="124" B="122" E="108"/>
<b id="125" B="107" E="108"/>
</fragment><t><s>NHCH2</s></t></n>
<b id="130" B="103" E="105" EndAttach="2" BS="N" CIP="N"/>
<b id="131" B="105" E="104"/>
</fragment>
</page></CDXML>"""


def _state() -> dict[str, Any]:
    return deepcopy(parse_cdxml_document(NATIVE).state)


def _atom(state: dict[str, Any], native: str) -> dict[str, Any]:
    keys = {v: k for k, v in state["cdxml_source"]["atoms"].items()}
    atoms = state["model"]["atoms"]
    key = keys[native]
    return atoms[key] if key in atoms else atoms[int(key)]


def _bond(state: dict[str, Any], native: str) -> dict[str, Any]:
    pair = {v: k for k, v in state["cdxml_source"]["bonds"].items()}[native]
    a, b = (int(part) for part in pair.split(":"))
    return next(
        bond for bond in state["model"]["bonds"] if {bond["a"], bond["b"]} == {a, b}
    )


def _save(state: dict[str, Any]) -> dict[str, ET.Element]:
    root = ET.fromstring(update_native_document(state))
    return {e.attrib["id"]: e for e in root.iter() if e.get("id")}


def _descriptors(saved: dict[str, ET.Element], expected: dict[str, dict[str, str]]):
    return {
        identity: {key: saved[identity].get(key) for key in attrs}
        for identity, attrs in expected.items()
    }


def _cleared(expected: dict[str, dict[str, str]]):
    return {identity: dict.fromkeys(attrs) for identity, attrs in expected.items()}


def test_colour_only_bond_edit_keeps_descriptors_and_writes_only_colour() -> None:
    state = _state()
    _bond(state, "20")["color"] = "#ff0000"
    _bond(state, "24")["color"] = "#ff0000"
    saved = _save(state)
    assert _descriptors(saved, DESCRIPTORS) == DESCRIPTORS
    original = {e.attrib["id"]: e for e in ET.fromstring(NATIVE).iter() if e.get("id")}
    for identity in ("20", "24"):
        attrs = dict(saved[identity].attrib)
        assert attrs.pop("color") != original[identity].get("color")
        assert attrs == original[identity].attrib
    assert saved["10"].get("BondOrdering") == "20 21 22 0"
    assert saved["10"].get("Geometry") == "Tetrahedral"


def test_colour_only_atom_edit_keeps_descriptors() -> None:
    state = _state()
    _atom(state, "10")["color"] = "#0000ff"
    _atom(state, "10")["explicit_label"] = True
    assert _descriptors(_save(state), DESCRIPTORS) == DESCRIPTORS


def test_double_bond_line_position_keeps_descriptors() -> None:
    state = _state()
    _bond(state, "24")["style"] = "double_center"
    saved = _save(state)
    assert saved["24"].get("DoublePosition") == "Center"
    assert _descriptors(saved, DESCRIPTORS) == DESCRIPTORS


def _order(state: dict[str, Any]) -> None:
    _bond(state, "21")["order"] = 2
    _bond(state, "21")["style"] = "double"


def _wedge_to_hash(state: dict[str, Any]) -> None:
    _bond(state, "20")["style"] = "hash"


def _wedge_direction(state: dict[str, Any]) -> None:
    bond = _bond(state, "20")
    bond["a"], bond["b"] = bond["b"], bond["a"]


def _move_neighbour(state: dict[str, Any]) -> None:
    _atom(state, "11")["x"] += 5


def _move_far_atom(state: dict[str, Any]) -> None:
    _atom(state, "15")["y"] -= 5


def _distant_element(state: dict[str, Any]) -> None:
    _atom(state, "16")["element"] = "Cl"


def _delete_substituent(state: dict[str, Any]) -> None:
    keys = {v: k for k, v in state["cdxml_source"]["atoms"].items()}
    atoms = state["model"]["atoms"]
    key = keys["16"] if keys["16"] in atoms else int(keys["16"])
    del atoms[key]
    state["model"]["bonds"].remove(_bond(state, "25"))


@pytest.mark.parametrize(
    "edit",
    [
        _order,
        _wedge_to_hash,
        _wedge_direction,
        _move_neighbour,
        _move_far_atom,
        _distant_element,
        _delete_substituent,
    ],
)
def test_structure_or_configuration_edit_drops_descriptors_in_its_fragment(
    edit: Callable[[dict[str, Any]], None],
) -> None:
    state = _state()
    edit(state)
    saved = _save(state)
    assert _descriptors(saved, DESCRIPTORS) == _cleared(DESCRIPTORS)
    assert _descriptors(saved, OTHER_FRAGMENT) == OTHER_FRAGMENT


def test_bond_order_change_resets_endpoint_coordination() -> None:
    state = _state()
    _order(state)
    saved = _save(state)
    for identity in ("10", "12"):
        assert saved[identity].get("BondOrdering") is None
        assert saved[identity].get("Geometry") is None


def test_atom_move_keeps_coordination() -> None:
    state = _state()
    _move_neighbour(state)
    _atom(state, "10")["x"] += 1
    saved = _save(state)
    assert saved["10"].get("BondOrdering") == "20 21 22 0"
    assert saved["10"].get("Geometry") == "Tetrahedral"


def test_edit_in_other_fragment_keeps_descriptors_here() -> None:
    state = _state()
    _atom(state, "31")["x"] += 5
    saved = _save(state)
    assert _descriptors(saved, DESCRIPTORS) == DESCRIPTORS
    assert _descriptors(saved, OTHER_FRAGMENT) == _cleared(OTHER_FRAGMENT)


def test_unclassified_record_fields_invalidate() -> None:
    atom = {"element": "C", "x": 0, "y": 0, "color": "#000000"}
    bond = {"a": 0, "b": 1, "order": 2, "style": "double", "color": "#000000"}
    assert not atom_edit_keeps_stereo(atom, {**atom, "isotope": 13})
    assert not bond_edit_keeps_stereo(bond, {**bond, "order": 1, "style": "single"})
    assert not bond_edit_keeps_stereo(bond, {**bond, "style": "double_either"})
    assert bond_edit_keeps_stereo(bond, {**bond, "style": "double_outer"})


def _attachment_state(
    display: str = "Solid", order: str = "1", begin_attach: str | None = None
) -> dict[str, Any]:
    root = ET.fromstring(ATTACHMENTS)
    bond = root.find('.//b[@id="30"]')
    assert bond is not None
    bond.set("Display", display)
    bond.set("Order", order)
    if begin_attach is not None:
        bond.set("BeginAttach", begin_attach)
    return parse_cdxml_document(ET.tostring(root)).state


def _assert_attachment_mapping(saved: dict[str, ET.Element]) -> None:
    assert saved["5"].get("BondOrdering") == "31 30"
    assert saved["6"].get("ConnectionOrder") == "21 22"
    # Check the chemical attachment targets, not just the visible label.
    assert saved["21"].get("NodeType") == "ExternalConnectionPoint"
    assert saved["22"].get("NodeType") == "ExternalConnectionPoint"
    assert (saved["23"].get("B"), saved["23"].get("E")) == ("21", "7")
    assert (saved["24"].get("B"), saved["24"].get("E")) == ("22", "8")
    assert saved["7"].get("Element") == "7"
    assert saved["8"].get("Element") == "6"
    assert {saved["30"].get("B"), saved["30"].get("E")} == {"3", "5"}
    assert {saved["31"].get("B"), saved["31"].get("E")} == {"5", "4"}


def _endpoint_offsets(bond: ET.Element) -> dict[str, str | None]:
    return {
        bond.attrib["B"]: bond.get("BeginAttach"),
        bond.attrib["E"]: bond.get("EndAttach"),
    }


@pytest.mark.parametrize(
    ("display", "old_order", "style", "order", "reverse"),
    [
        ("Solid", "1", "bold_in", 1, False),
        ("Solid", "1", "wedge", 1, False),
        ("Solid", "1", "hash", 1, True),
        ("Solid", "1", "dotted", 1, False),
        ("Solid", "1", "wavy", 1, False),
        ("Solid", "1", "double", 2, False),
        ("Solid", "1", "triple", 3, False),
        ("Solid", "1", "single", 2, False),  # Order alone.
        ("Solid", "2", "wedge", 1, True),  # Style, order and direction.
        ("WedgeBegin", "1", "wedge", 1, True),  # Direction alone.
        ("WedgedHashBegin", "1", "wedge", 1, True),
        ("WedgeEnd", "1", "bold_in", 1, False),  # Import normalizes a/b.
        ("WedgedHashEnd", "1", "wedge", 1, False),
    ],
)
@pytest.mark.parametrize("begin_attach", [None, "0", "1"])
def test_existing_bond_edit_keeps_native_attachment_mapping(
    display: str,
    old_order: str,
    style: str,
    order: int,
    reverse: bool,
    begin_attach: str | None,
) -> None:
    state = _attachment_state(display, old_order, begin_attach)
    original = _save(state)
    bond = _bond(state, "30")
    bond.update(style=style, order=order)
    if reverse:
        bond["a"], bond["b"] = bond["b"], bond["a"]
    expected_ends = tuple(
        state["cdxml_source"]["atoms"][str(bond[key])] for key in ("a", "b")
    )
    raw = update_native_document(state)
    assert b"ChemvasDocument:" not in raw
    reopened = parse_cdxml_document(raw).state  # Native XML, no snapshot fallback.
    saved_versions = (
        {e.attrib["id"]: e for e in ET.fromstring(raw).iter() if e.get("id")},
        _save(reopened),
    )
    for saved in saved_versions:
        _assert_attachment_mapping(saved)
        assert (saved["30"].get("B"), saved["30"].get("E")) == expected_ends
        assert _endpoint_offsets(saved["30"]) == {"3": begin_attach, "5": "2"}
        assert saved["30"].get("Order") == str(order)
        assert ET.tostring(saved["31"]) == ET.tostring(original["31"])
        assert ET.tostring(saved["102"]) == ET.tostring(original["102"])
        for identity in ("3", "7", "30"):
            for prop in ("AS", "BS", "CIP"):
                assert saved[identity].get(prop) is None
        assert saved["3"].get("BondOrdering") is None
        assert saved["3"].get("Geometry") is None
        assert saved["5"].get("Geometry") is None
    assert _bond(reopened, "30")["order"] == order
    assert _bond(reopened, "30")["style"] == (
        "double" if style == "single" and order == 2 else style
    )


def test_style_edit_keeps_multiport_nickname_attachment_mapping() -> None:
    root = ET.fromstring(ATTACHMENTS)
    node = root.find('.//n[@id="5"]')
    assert node is not None
    node.set("NodeType", "Nickname")
    label = node.find("t/s")
    assert label is not None
    label.text = "L"  # One symbol for the existing two-port definition.
    bond = root.find('.//b[@id="30"]')
    assert bond is not None
    bond.set("EndAttach", "1")
    state = parse_cdxml_document(ET.tostring(root)).state
    _bond(state, "30")["style"] = "bold_in"
    raw = update_native_document(state)
    assert b"ChemvasDocument:" not in raw
    reopened = parse_cdxml_document(raw).state
    saved = _save(reopened)
    _assert_attachment_mapping(saved)
    assert saved["5"].get("NodeType") == "Nickname"
    assert saved["5"].findtext("t/s") == "L"
    assert _endpoint_offsets(saved["30"]) == {"3": None, "5": "1"}
    assert saved["5"].get("Geometry") is None
    assert saved["3"].get("BondOrdering") is None
    assert saved["3"].get("Geometry") is None
    assert _bond(reopened, "30")["style"] == "bold_in"


@pytest.mark.parametrize("edit", ["colour", "double_position"])
def test_presentation_edit_keeps_native_attachment_metadata(edit: str) -> None:
    state = _attachment_state("Solid", "2")
    original = _save(state)
    if edit == "colour":
        _bond(state, "30")["color"] = "#ff0000"
    else:
        _bond(state, "30")["style"] = "double_center"
    saved = _save(parse_cdxml_document(update_native_document(state)).state)
    _assert_attachment_mapping(saved)
    assert _endpoint_offsets(saved["30"]) == {"3": None, "5": "2"}
    for identity in ("3", "5", "102"):
        assert ET.tostring(saved[identity]) == ET.tostring(original[identity])
    assert saved["30"].get("BS") == "N"
    assert saved["30"].get("CIP") == "N"


def test_multiple_style_edits_at_moved_fragment_keep_attachment_mapping() -> None:
    state = _attachment_state()
    _bond(state, "30")["style"] = "bold_in"
    bond = _bond(state, "31")
    bond.update(style="double", order=2)
    bond["a"], bond["b"] = bond["b"], bond["a"]
    _atom(state, "5")["x"] += 5
    _atom(state, "5")["color"] = "#ff0000"
    saved = _save(parse_cdxml_document(update_native_document(state)).state)
    _assert_attachment_mapping(saved)
    assert _endpoint_offsets(saved["30"]) == {"3": None, "5": "2"}
    assert _endpoint_offsets(saved["31"]) == {"4": None, "5": None}
    assert saved["5"].get("p") == "105 100"
    assert saved["7"].get("p") == "95 100"


def test_style_edit_does_not_restore_attachments_of_replaced_fragment_label() -> None:
    state = _attachment_state(begin_attach="1")
    _atom(state, "5")["element"] = "C"
    _bond(state, "30")["style"] = "bold_in"
    saved = _save(parse_cdxml_document(update_native_document(state)).state)
    assert saved["5"].get("BondOrdering") is None
    assert saved["5"].get("Geometry") is None
    assert saved["5"].find("fragment") is None
    assert saved["30"].get("EndAttach") is None
