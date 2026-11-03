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
