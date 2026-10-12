"""The seven witnessed TS counts do not authorize equal-valence alternatives."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.features.export.cdxml_consumer_validation import validate_consumer_objects


def _exception_scene(kind):
    root = ET.Element("CDXML")
    table = ET.SubElement(root, "fonttable")
    ET.SubElement(table, "font", id="1", name="Arial")
    page = ET.SubElement(root, "page", id="2")
    outer = ET.SubElement(page, "fragment", id="3")
    element, charge, degree = {
        "H": ("1", "0", 2),
        "P+": ("15", "1", 5),
        "O-": ("8", "-1", 2),
    }[kind]
    owner = ET.SubElement(outer, "n", id="10", p="0 0")
    fragment = outer
    atom = owner
    if kind != "H":
        owner.set("NodeType", "Fragment")
        owner.set("BondOrdering", " ".join(str(200 + i) for i in range(degree)))
        fragment = ET.SubElement(
            owner,
            "fragment",
            id="90",
            ConnectionOrder=" ".join(str(150 + i) for i in range(degree)),
        )
        atom = ET.SubElement(fragment, "n", id="100", p="0 0")
    atom.set("Element", element)
    atom.set("Charge", charge)
    text = ET.SubElement(atom, "t", id="500", p="0 0", InterpretChemically="yes")
    ET.SubElement(text, "s", font="1", size="10").text = kind
    for index in range(degree):
        target = str(20 + index)
        ET.SubElement(outer, "n", id=target, p=f"{10 + index} 20")
        bond = ET.SubElement(outer, "b", id=str(200 + index), B="10", E=target)
        if kind == "H":
            bond.set("Display", "Dash")
        else:
            display = (
                ["Solid", "Solid", "WedgedHashBegin", "WedgeBegin", "Dash"]
                if kind == "P+"
                else ["Solid", "Dash"]
            )[index]
            bond.set("Display", display)
            if kind == "O-" and display == "Dash":
                bond.set("B", target)
                bond.set("E", "10")
            port = str(150 + index)
            ET.SubElement(
                fragment,
                "n",
                id=port,
                NodeType="ExternalConnectionPoint",
                p=f"{10 + index} 20",
            )
            ET.SubElement(fragment, "b", id=str(300 + index), B="100", E=port)
    return root, atom


def _pair(root, atom, reverse):
    other = deepcopy(root)
    other.find(f'.//n[@id="{atom.get("id")}"]').set("NumHydrogens", "0")
    return (other, root) if reverse else (root, other)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("kind", ["H", "P+", "O-"])
def test_exact_exception_compositions_are_read_only(kind, reverse):
    root, atom = _exception_scene(kind)
    a, b = _pair(root, atom, reverse)
    before = ET.tostring(a), ET.tostring(b)
    validate_consumer_objects(a, b, {"Arial": "Arial"})
    assert before == (ET.tostring(a), ET.tostring(b))


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("kind", ["H", "P+", "O-"])
def test_same_valence_unwitnessed_double_bonds_rejected(kind, reverse):
    root, atom = _exception_scene(kind)
    fragment = next(f for f in root.iter("fragment") if atom in list(f))
    bonds = [
        b for b in fragment.findall("b") if atom.get("id") in (b.get("B"), b.get("E"))
    ]
    orders = ["2", "2", "1"] if kind == "P+" else ["2"]
    for bond in bonds[len(orders) :]:
        fragment.remove(bond)
    for bond, order in zip(bonds[: len(orders)], orders, strict=True):
        bond.set("Order", order)
        bond.set("Display", "Solid")
    with pytest.raises(ValueError, match="hydrogen count"):
        validate_consumer_objects(*_pair(root, atom, reverse), {"Arial": "Arial"})


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "kind,mutation",
    [
        ("H", "solid"),
        ("H", "display2"),
        ("H", "nested"),
        *[
            (kind, mutation)
            for kind in ["P+", "O-"]
            for mutation in [
                "inner_display",
                "inner_direction",
                "port_kind",
                "port_order_missing",
                "outer_order_missing",
                "outer_display",
                "outer_direction",
                "outer_double",
                "extra_inner_bond",
                "extra_inner_atom",
                "plain_owner",
            ]
        ],
    ],
)
def test_unwitnessed_display_and_definition_context_rejected(kind, mutation, reverse):
    root, atom = _exception_scene(kind)
    outer = root.find("./page/fragment")
    owner = outer.find("n")
    inner = owner.find("fragment")
    if mutation == "solid":
        outer.find("b").set("Display", "Solid")
    elif mutation == "display2":
        outer.find("b").set("Display2", "Dash")
    elif mutation == "nested":
        page = root.find("page")
        page.remove(outer)
        ET.SubElement(page, "group", id="999").append(outer)
    elif mutation == "inner_display":
        inner.find("b").set("Display", "Dash")
    elif mutation == "inner_direction":
        bond = inner.find("b")
        bond.set("B", "150")
        bond.set("E", "100")
    elif mutation == "port_kind":
        inner.find('n[@id="150"]').set("NodeType", "Element")
    elif mutation == "port_order_missing":
        inner.attrib.pop("ConnectionOrder")
    elif mutation == "outer_order_missing":
        owner.attrib.pop("BondOrdering")
    elif mutation == "outer_display":
        outer.find("b").set("Display", "Bold")
    elif mutation == "outer_direction":
        bond = outer.find("b")
        bond.set("B", "20")
        bond.set("E", "10")
    elif mutation == "outer_double":
        outer.find("b").set("Order", "2")
    elif mutation == "extra_inner_bond":
        ET.SubElement(inner, "b", id="999", B="150", E="151")
    elif mutation == "extra_inner_atom":
        ET.SubElement(inner, "n", id="999", p="20 20")
    else:
        owner.set("NodeType", "Nickname")
    with pytest.raises(ValueError, match="hydrogen count"):
        validate_consumer_objects(*_pair(root, atom, reverse), {"Arial": "Arial"})
