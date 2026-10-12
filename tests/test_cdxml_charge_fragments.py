"""Charge definitions must preserve the drawn label and the contracted graph."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from chemvas.domain.document import Atom, Bond
from chemvas.ui.export.export_cdxml import CdxmlLabelBinding
from tests.test_cdxml_bound_fluorophenyl import (
    _assert_cdxml_drawable_leaves_have_unique_z,
)
from tests.test_cdxml_export import (
    _assert_label_vocabulary_and_ids,
    _chemical_atom,
    _expected_point,
    _export_bound,
    _simple_state,
    _top_bonds,
    _top_nodes,
)

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.mark.parametrize(
    "symbol,charge,degree,order",
    [
        ("P", 1, 4, 1),
        ("P", 1, 5, 1),
        ("O", -1, 1, 1),
        ("O", -1, 2, 1),
        ("N", 1, 3, 2),
        ("N", -1, 2, 1),
        ("S", 2, 2, 1),
        ("Mg", 2, 0, 1),
        ("C", -1, 3, 1),
        ("H\u1d43", 1, 1, 1),
    ],
)
def test_charge_definition_retains_atom_bonds_label_and_each_port(
    symbol, charge, degree, order
):
    atoms = {0: Atom(symbol, 0.0, 0.0, explicit_label=True)}
    for index in range(degree):
        angle = 2 * math.pi * index / degree
        atoms[index + 1] = Atom("C", 30 * math.cos(angle), 30 * math.sin(angle))
    styles = ["double" if order == 2 else "single", "hash", "wedge", "single", "dotted"]
    bonds = [
        Bond(0, index + 1, order=order if index == 0 else 1, style=styles[index])
        for index in range(degree)
    ]
    state = _simple_state(
        atoms=atoms, bonds=bonds, atom_annotations={0: {"formal_charge": charge}}
    )
    bindings = (
        {0: CdxmlLabelBinding.element_identity("H")}
        if symbol != "H" and symbol.startswith("H")
        else {}
    )
    raw, plan = _export_bound(state, bindings)
    root = ET.fromstring(raw)
    _assert_label_vocabulary_and_ids(root)
    _assert_cdxml_drawable_leaves_have_unique_z(root)
    outer = next(n for n in _top_nodes(root) if n.get("NodeType") == "Fragment")
    atom = _chemical_atom(outer)
    assert int(atom.get("Charge")) == charge
    assert atom.get("NodeType") is None
    assert "Charge" not in outer.attrib
    assert "Element" not in outer.attrib
    assert tuple(map(float, outer.get("p").split())) == pytest.approx(
        _expected_point(plan, atoms[0])
    )
    assert atom.get("p") == outer.get("p")
    assert "".join(s.text or "" for s in outer.findall("./t/s")) == symbol
    canonical_symbol = "H" if bindings else symbol
    sign = (str(abs(charge)) if abs(charge) != 1 else "") + ("+" if charge > 0 else "-")
    assert (
        "".join(s.text or "" for s in atom.findall("./t/s")) == canonical_symbol + sign
    )
    assert int(atom.findall("./t/s")[-1].get("face")) & 64
    assert len(_top_nodes(root)) == len(atoms)
    actual_bonds = _top_bonds(root)
    assert len(actual_bonds) == len(bonds)
    inner = outer.find("fragment")
    ports = inner.findall('./n[@NodeType="ExternalConnectionPoint"]')
    assert len(ports) == degree
    if degree > 1:
        assert outer.get("BondOrdering").split() == [b.get("id") for b in actual_bonds]
        assert inner.get("ConnectionOrder").split() == [p.get("id") for p in ports]
    else:
        assert outer.get("BondOrdering") is None
        assert inner.get("ConnectionOrder") is None
    all_top = {n.get("id"): n for n in _top_nodes(root)}
    for index, (bond, port, link) in enumerate(
        zip(actual_bonds, ports, inner.findall("b"), strict=True)
    ):
        assert bond.get("B") == outer.get("id")
        assert port.get("p") == all_top[bond.get("E")].get("p")
        assert link.get("B") == atom.get("id") and link.get("E") == port.get("id")
        assert (
            link.get("Order", "1") == bond.get("Order", "1") == str(bonds[index].order)
        )
        assert bond.get("Display") == {
            "hash": "WedgedHashBegin",
            "wedge": "WedgeBegin",
            "dotted": "Dash",
        }.get(bonds[index].style)
