"""Native CDXML saves keep stored CIP descriptors unless an edit can change them.

Synthetic fixture; descriptor values are not recomputed or checked for chemistry.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest

from chemvas.domain.document.cdxml_stereo_descriptors import (
    atom_edit_keeps_stereo,
    bond_edit_keeps_stereo,
)
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from PyQt6.QtWidgets import QApplication

# Fragment 2 has a stereocentre (10, wedge 20) whose substituent chain ends in a
# double bond (24). Fragment 3 is a separate structure with its own labels.
NATIVE = b"""<?xml version="1.0"?><CDXML BondLength="20"><page id="1" Width="400" Height="300">
<fragment id="2">
<n id="10" p="100 100" AS="R" CIP="R" Geometry="Tetrahedral" BondOrdering="20 21 22 0"/>
<n id="11" p="117 110" Element="8"><t><s>O</s></t></n>
<n id="12" p="100 80" NodeType="Element" Geometry="Tetrahedral" BondOrdering="21 23 0 0"/>
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
COORDINATION = {
    "10": {"BondOrdering": "20 21 22 0", "Geometry": "Tetrahedral"},
    "12": {"BondOrdering": "21 23 0 0", "Geometry": "Tetrahedral"},
}

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


def _delete_native(
    state: dict[str, Any], bonds: tuple[str, ...], atoms: tuple[str, ...] = ()
) -> None:
    for native in bonds:
        state["model"]["bonds"].remove(_bond(state, native))
    keys = {v: k for k, v in state["cdxml_source"]["atoms"].items()}
    for native in atoms:
        records = state["model"]["atoms"]
        key = keys[native] if keys[native] in records else int(keys[native])
        del records[key]


@pytest.mark.parametrize(
    "bonds,atoms,reset",
    [
        pytest.param(("20",), (), {"10"}, id="wedge"),
        pytest.param(("21",), (), {"10", "12"}, id="both-ends"),
        pytest.param(("23",), (), {"12"}, id="other-end"),
        pytest.param(("20", "21"), (), {"10", "12"}, id="several-bonds"),
        pytest.param(("20", "21", "22"), (), {"10", "12"}, id="isolated-centre"),
        pytest.param(("20",), ("11",), {"10"}, id="deleted-neighbour"),
        pytest.param(("21", "23"), ("12",), {"10"}, id="deleted-ordered-neighbour"),
        pytest.param(("20", "21", "22"), ("10",), {"12"}, id="deleted-centre"),
        pytest.param(
            ("20", "21", "22", "23"), ("10", "12"), set(), id="deleted-both-ends"
        ),
        pytest.param(("25",), ("16",), set(), id="untouched-coordination"),
    ],
)
def test_deletion_resets_only_surviving_elemental_endpoint_coordination(
    bonds: tuple[str, ...], atoms: tuple[str, ...], reset: set[str]
) -> None:
    state = _state()
    original = _save(state)
    _delete_native(state, bonds, atoms)
    edited = deepcopy(state)
    raw = update_native_document(state)
    saved = {e.attrib["id"]: e for e in ET.fromstring(raw).iter() if e.get("id")}
    assert state == edited
    assert not (set(bonds) | set(atoms)).intersection(saved)
    for identity, attrs in COORDINATION.items():
        if identity not in atoms:
            expected = dict.fromkeys(attrs) if identity in reset else attrs
            assert {key: saved[identity].get(key) for key in attrs} == expected
    surviving = {key: attrs for key, attrs in DESCRIPTORS.items() if key in saved}
    assert _descriptors(saved, surviving) == _cleared(surviving)
    assert ET.tostring(saved["3"]) == ET.tostring(original["3"])
    # Surviving bond directions, wedges, orders and other native attributes stay.
    for identity in set(state["cdxml_source"]["bonds"].values()) - set(bonds):
        attrs = dict(original[identity].attrib)
        if identity != "32":
            attrs.pop("BS", None)
            attrs.pop("CIP", None)
        assert saved[identity].attrib == attrs

    # Reopen the native XML itself, without an embedded Chemvas snapshot.
    assert b"ChemvasDocument:" not in raw
    reopened = parse_cdxml_document(raw).state
    for collection, removed in (("atoms", atoms), ("bonds", bonds)):
        assert set(reopened["cdxml_source"][collection].values()) == set(
            state["cdxml_source"][collection].values()
        ) - set(removed)
    for identity in reopened["cdxml_source"]["atoms"].values():
        assert _atom(reopened, identity) == _atom(state, identity)
    assert update_native_document(reopened) == raw


@pytest.mark.parametrize("save_deleted", [False, True])
def test_deletion_undo_preserves_native_source_and_no_net_edit_bytes(
    save_deleted: bool,
) -> None:
    state = _state()
    before = deepcopy(state)
    original = update_native_document(state)
    assert ET.canonicalize(original.decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )
    restored_bonds = [deepcopy(_bond(state, identity)) for identity in ("20", "21")]
    _delete_native(state, ("20", "21"), ("11",))
    if save_deleted:
        update_native_document(state)
    # Undo can reinsert records at the end; source identity still owns the XML.
    state["model"]["atoms"].update(before["model"]["atoms"])
    state["model"]["bonds"].extend(restored_bonds)
    assert state["cdxml_source"] == before["cdxml_source"]
    assert update_native_document(state) == original


@pytest.mark.parametrize(
    "node_type,nested",
    [
        ("Fragment", True),
        ("Nickname", True),
        (None, True),
        ("Element", True),
        ("GenericNickname", False),
        ("Unspecified", False),
    ],
)
@pytest.mark.parametrize("edit_remaining_bond", [False, True])
def test_deletion_keeps_special_node_attachment_references_fail_closed(
    node_type: str | None, nested: bool, edit_remaining_bond: bool
) -> None:
    root = ET.fromstring(NATIVE)
    node = root.find('.//n[@id="12"]')
    assert node is not None
    node.attrib.pop("NodeType")
    if node_type is not None:
        node.set("NodeType", node_type)
    node.set("BondOrdering", "21 23")
    if nested:
        # Two outer bonds genuinely map to two external connection points.
        node.append(
            ET.fromstring("""<fragment id="40" ConnectionOrder="42 43">
            <n id="41" p="100 80" Element="8"/>
            <n id="42" p="100 100" NodeType="ExternalConnectionPoint"/>
            <n id="43" p="117 70" NodeType="ExternalConnectionPoint"/>
            <b id="44" B="42" E="41"/><b id="45" B="41" E="43"/>
            </fragment>""")
        )
    if node_type == "GenericNickname":
        node.set("GenericNickname", "R")
    ET.SubElement(ET.SubElement(node, "t"), "s").text = (
        "R" if node_type == "GenericNickname" else "O"
    )
    state = parse_cdxml_document(ET.tostring(root)).state
    assert "12" in state["cdxml_source"]["atoms"].values()
    assert _save(state)["12"].get("BondOrdering") == "21 23"
    # A deletion elsewhere must preserve the complete attachment definition.
    elsewhere = deepcopy(state)
    _delete_native(elsewhere, ("20",))
    assert ET.tostring(_save(elsewhere)["12"]) == ET.tostring(_save(state)["12"])
    _delete_native(state, ("21",))
    if edit_remaining_bond:
        # This also puts the special node in changed_nodes. Its blanket cleanup
        # must still run AFTER reference validation, so it cannot hide the loss.
        _bond(state, "23").update(order=2, style="double")
    before = deepcopy(state)
    with pytest.raises(ValueError, match=r"native n\.BondOrdering references"):
        update_native_document(state)
    assert state == before


@pytest.mark.parametrize(
    "reference", ["BondOrdering", "BondCircularOrdering", "BracketedObjectIDs"]
)
def test_deletion_does_not_clear_unrelated_native_references(reference: str) -> None:
    root = ET.fromstring(NATIVE)
    if reference == "BondOrdering":
        node = root.find('.//n[@id="12"]')
        assert node is not None
        # Not an endpoint of bond 20: do not repair a foreign reference.
        node.set(reference, "20 21 23 0")
    elif reference == "BondCircularOrdering":
        node = root.find('.//b[@id="21"]')
        assert node is not None
        node.set(reference, "20 22 23")
    else:
        page = root.find("page")
        assert page is not None
        ET.SubElement(page, "bracketedgroup", id="40", BracketedObjectIDs="20 21")
    state = parse_cdxml_document(ET.tostring(root)).state
    _delete_native(state, ("20",))
    with pytest.raises(ValueError, match=rf"\.{reference} references"):
        update_native_document(state)


def test_deletion_preserves_unaffected_native_references() -> None:
    raw = NATIVE.replace(
        b"</page>",
        b'<bracketedgroup id="40" BracketedObjectIDs="10 12 24"/></page>',
    )
    state = parse_cdxml_document(raw).state
    _delete_native(state, ("20",))
    saved = _save(state)
    assert saved["40"].get("BracketedObjectIDs") == "10 12 24"
    assert _descriptors(saved, {"12": COORDINATION["12"]}) == {"12": COORDINATION["12"]}


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


def _defined_attachment_state(
    node_type: str, mapping: str = "explicit"
) -> dict[str, Any]:
    root = ET.fromstring(ATTACHMENTS)
    node = root.find('.//n[@id="5"]')
    definition = root.find('.//fragment[@id="6"]')
    assert node is not None and definition is not None
    node.set("NodeType", node_type)
    if node_type == "Nickname":
        label = node.find("t/s")
        bond = root.find('.//b[@id="30"]')
        assert label is not None and bond is not None
        label.text = "L"
        bond.set("EndAttach", "0")  # Label offset, not the selected chemical port.
    if mapping in {"no_bond_ordering", "implicit", "one_port"}:
        node.attrib.pop("BondOrdering")
    if mapping in {"no_connection_order", "implicit", "one_port"}:
        definition.attrib.pop("ConnectionOrder")
    if mapping == "one_port":
        # SDK ConnectionOrder is omitted with fewer than two attachment points.
        # The sole port is already occupied by bond 30.
        for identity in ("22", "24"):
            definition.remove(next(e for e in definition if e.get("id") == identity))
        fragment = root.find('.//fragment[@id="2"]')
        bond = root.find('.//b[@id="31"]')
        assert fragment is not None and bond is not None
        fragment.remove(bond)
    return parse_cdxml_document(ET.tostring(root)).state


def _add_bond_at(
    state: dict[str, Any], native: str = "5", *, reverse: bool = False
) -> int:
    model = state["model"]
    anchor = int(
        next(k for k, v in state["cdxml_source"]["atoms"].items() if v == native)
    )
    new_id = model["next_atom_id"]
    model["next_atom_id"] += 1
    atom = _atom(state, native)
    model["atoms"][new_id] = dict(
        element="C",
        x=atom["x"],
        y=atom["y"] - 20,
        color="#000000",
        explicit_label=False,
    )
    begin, end = (new_id, anchor) if reverse else (anchor, new_id)
    model["bonds"].append(
        dict(a=begin, b=end, order=1, style="single", color="#000000")
    )
    return new_id


@pytest.mark.parametrize("node_type", ["Fragment", "Nickname"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "mapping",
    ["explicit", "no_connection_order", "no_bond_ordering", "implicit", "one_port"],
)
def test_new_bond_at_defined_structure_refuses_without_mutating_state(
    node_type: str, reverse: bool, mapping: str
) -> None:
    state = _defined_attachment_state(node_type, mapping)
    _add_bond_at(state, reverse=reverse)
    before = deepcopy(state)
    with pytest.raises(ValueError, match="attachment.*undo the new bond"):
        update_native_document(state)
    assert state == before


@pytest.mark.parametrize(
    "node_type", [b"", b' NodeType="Element"'], ids=["absent", "element"]
)
def test_new_bond_at_retained_definition_refuses_without_fragment_node_type(
    node_type: bytes,
) -> None:
    source = ATTACHMENTS.replace(
        b' NodeType="Fragment" BondOrdering="31 30"',
        node_type + b' BondOrdering="31 30"',
        1,
    )
    state = parse_cdxml_document(source).state
    _assert_attachment_mapping(_save(state))
    _add_bond_at(state)
    before = deepcopy(state)
    with pytest.raises(ValueError, match="attachment.*undo the new bond"):
        update_native_document(state)
    assert state == before


@pytest.mark.parametrize("node_type", ["Fragment", "Nickname"])
@pytest.mark.parametrize("new_bond_first", [False, True])
def test_style_edit_does_not_mask_unsafe_new_attachment(
    node_type: str, new_bond_first: bool
) -> None:
    state = _defined_attachment_state(node_type)
    _bond(state, "30")["style"] = "bold_in"
    expected = update_native_document(state)
    new_id = _add_bond_at(state)
    added = state["model"]["bonds"].pop()
    state["model"]["bonds"].insert(
        0 if new_bond_first else len(state["model"]["bonds"]), added
    )
    with pytest.raises(ValueError, match="attachment.*undo the new bond"):
        update_native_document(state)
    state["model"]["bonds"].remove(added)
    del state["model"]["atoms"][new_id]
    assert update_native_document(state) == expected
    _assert_attachment_mapping(_save(state))


@pytest.mark.parametrize("reverse", [False, True])
def test_new_connection_between_existing_atoms_cannot_reuse_a_removed_port(
    reverse: bool,
) -> None:
    state = _defined_attachment_state("Fragment")
    # Replace 5--4 with 5--9 in the same outer fragment. Equal degree does not
    # specify that the new bond should inherit the deleted bond's internal N.
    root = ET.fromstring(state["cdxml_source"]["xml"])
    fragment = root.find('.//fragment[@id="2"]')
    assert fragment is not None
    ET.SubElement(fragment, "n", id="9", p="100 70", Element="8")
    state = parse_cdxml_document(ET.tostring(root)).state
    bond = _bond(state, "31")
    atom_ids = {v: int(k) for k, v in state["cdxml_source"]["atoms"].items()}
    bond["a"], bond["b"] = (
        (atom_ids["9"], atom_ids["5"]) if reverse else (atom_ids["5"], atom_ids["9"])
    )
    with pytest.raises(ValueError, match="attachment.*undo the new bond"):
        update_native_document(state)


@pytest.mark.parametrize("reverse", [False, True])
def test_ordinary_atom_addition_preserves_neighbouring_attachment_mapping(
    reverse: bool,
) -> None:
    state = _attachment_state()
    original = _save(state)
    _add_bond_at(state, "3", reverse=reverse)
    saved = _save(parse_cdxml_document(update_native_document(state)).state)
    _assert_attachment_mapping(saved)
    outer_bonds = saved["2"].findall("b")
    assert len(outer_bonds) == 3
    added = next(b for b in outer_bonds if b.get("id") not in {"30", "31"})
    assert added.get("E" if reverse else "B") == "3"
    new_id = added.attrib["B" if reverse else "E"]
    assert saved[new_id].get("Element") == "6"
    assert saved["3"].get("BondOrdering") is None
    assert saved["3"].get("Geometry") is None
    assert saved["5"].get("Geometry") == "Linear"
    assert ET.tostring(saved["102"]) == ET.tostring(original["102"])


@pytest.mark.parametrize("node_type", ["Fragment", "Nickname"])
@pytest.mark.parametrize("symbol", ["C", "N", "R1"])
def test_new_bond_after_genuine_retyping_uses_existing_label_replacement_contract(
    node_type: str, symbol: str
) -> None:
    state = _defined_attachment_state(node_type)
    _atom(state, "5")["element"] = symbol
    _bond(state, "30")["style"] = "bold_in"
    _add_bond_at(state)
    raw = update_native_document(state)
    assert b"ChemvasDocument:" not in raw
    saved = _save(parse_cdxml_document(raw).state)
    assert saved["5"].find("fragment") is None
    assert saved["5"].get("BondOrdering") is None
    assert saved["5"].get("NodeType", "Element") == (
        "GenericNickname" if symbol == "R1" else "Element"
    )
    assert saved["5"].get("Element") == {"C": "6", "N": "7", "R1": None}[symbol]
    assert len(saved["2"].findall("b")) == 3
    assert saved["30"].get("EndAttach") is None


@pytest.mark.parametrize("node_type", ["Fragment", "Nickname"])
def test_retyping_back_to_original_label_does_not_bypass_attachment_guard(
    node_type: str,
) -> None:
    state = _defined_attachment_state(node_type)
    atom = _atom(state, "5")
    original = atom["element"]
    atom["element"] = "C"
    _add_bond_at(state)
    atom["element"] = original
    with pytest.raises(ValueError, match="attachment.*undo the new bond"):
        update_native_document(state)


@pytest.mark.parametrize("reverse", [False, True])
def test_failed_attachment_save_preserves_file_and_undo_restores_save(
    tmp_path: Path, qt_application: QApplication, reverse: bool
) -> None:
    from PyQt6.QtCore import QPointF

    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.ui.window.main_window_ports import active_canvas_for_window

    path = tmp_path / "attachments.cdxml"
    path.write_bytes(ATTACHMENTS)
    original_stat = path.stat()
    box = Mock()
    window = build_main_window()
    actions = window.services.document_action_service
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    history = canvas.services.history_service
    try:
        assert actions.load_canvas_from_path(window, str(path), message_box=box)
        before = session.snapshot_state()
        expected = update_native_document(before)
        digest = canvas.runtime_state.document_metadata_state.source_sha256
        anchor = int(
            next(k for k, v in before["cdxml_source"]["atoms"].items() if v == "5")
        )
        atom = canvas.model.atoms[anchor]
        start, end = QPointF(atom.x, atom.y), QPointF(atom.x, atom.y - 20)
        if reverse:
            start, end = end, start
        assert (
            canvas.services.structure_build_service.add_bond_between_points(
                start, end, "single", 1
            )
            is not None
        )
        edited = session.snapshot_state()
        assert len(edited["model"]["bonds"]) == len(before["model"]["bonds"]) + 1
        history_before = history.capture_stack_snapshot()
        assert not actions.save_canvas_to_path(window, str(path), message_box=box)
        message = box.warning.call_args.args[-1]
        assert "attachment" in message and "undo the new bond" in message
        assert "file was not replaced" in message
        assert path.read_bytes() == ATTACHMENTS
        assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
        assert path.stat().st_ino == original_stat.st_ino
        assert not list(tmp_path.glob(".chemvas-*.tmp"))
        assert session.snapshot_state() == edited
        history.verify_stack_snapshot(history_before)
        assert canvas.runtime_state.document_metadata_state.source_sha256 == digest
        assert window.services.canvas_document_service.is_dirty(canvas)

        history.undo()
        assert update_native_document(session.snapshot_state()) == expected
        history.redo()
        with pytest.raises(ValueError, match="attachment.*undo the new bond"):
            update_native_document(session.snapshot_state())
        history.undo()
        assert actions.save_canvas_to_path(window, str(path), message_box=box)
        assert not window.services.canvas_document_service.is_dirty(canvas)
        # Ignore the snapshot so retained metadata cannot conceal native loss.
        native = ET.tostring(ET.fromstring(path.read_bytes()))
        saved = _save(parse_cdxml_document(native).state)
        _assert_attachment_mapping(saved)
        assert len(saved["2"].findall("b")) == 2
    finally:
        window.services.canvas_document_service.mark_clean(canvas)
        window.close()
        qt_application.processEvents()
