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
