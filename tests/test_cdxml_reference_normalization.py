"""Native representation changes cannot authorize a changed source graph."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.features.export.cdxml_consumer_validation import validate_consumer_objects


def _scene(element="8", charge="0", degree=2, label="O", hydrogens=None):
    root = ET.Element("CDXML")
    table = ET.SubElement(root, "fonttable")
    ET.SubElement(table, "font", id="1", name="Arial")
    page = ET.SubElement(root, "page", id="2")
    fragment = ET.SubElement(page, "fragment", id="3")
    atom = ET.SubElement(fragment, "n", id="10", Element=element, p="0 0")
    if charge != "0":
        atom.set("Charge", charge)
    if hydrogens is not None:
        atom.set("NumHydrogens", hydrogens)
    if label is not None:
        text = ET.SubElement(atom, "t", id="500", p="0 0", InterpretChemically="yes")
        ET.SubElement(text, "s", font="1", size="10").text = label
    for index in range(degree):
        target = str(20 + index)
        ET.SubElement(fragment, "n", id=target, p=f"{10 + index} 20")
        ET.SubElement(fragment, "b", id=str(100 + index), B="10", E=target)
    return root, atom


def _validate(a, b):
    fonts = {"Arial": "Arial"} if a.find(".//t") is not None else {}
    validate_consumer_objects(a, b, fonts)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "element,charge,degree,label,count",
    [
        ("6", "0", 1, None, "3"),
        ("6", "0", 4, None, "0"),
        ("8", "0", 2, "O", "0"),
        ("15", "0", 5, "P", "0"),
        ("1", "0", 1, "H", "0"),
        ("15", "1", 4, "P+", "0"),
        ("8", "-1", 1, "O-", "0"),
    ],
)
def test_witnessed_hydrogen_forms_preserve_graph(
    element, charge, degree, label, count, reverse
):
    a, _ = _scene(element, charge, degree, label)
    b = deepcopy(a)
    b.find(".//n").set("NumHydrogens", count)
    before = ET.tostring(a), ET.tostring(b)
    _validate(*((b, a) if reverse else (a, b)))
    assert before == (ET.tostring(a), ET.tostring(b))


def test_ary_zero_is_non_element_bookkeeping_only():
    a, node = _scene(label="ARY", degree=1)
    node.attrib.pop("Element")
    node.set("NodeType", "GenericNickname")
    node.set("GenericNickname", "ARY")
    b = deepcopy(a)
    b.find(".//n").set("NumHydrogens", "0")
    _validate(a, b)
    _validate(b, a)
    b.find(".//n").set("NumHydrogens", "1")
    with pytest.raises(ValueError, match="hydrogen count"):
        _validate(a, b)


@pytest.mark.parametrize(
    "element,charge,degree,label,count",
    [
        ("6", "0", 1, None, "0"),
        ("6", "0", 5, None, "0"),
        ("8", "0", 1, "O", "0"),
        ("8", "0", 2, None, "0"),
        ("8", "0", 2, "O", "9"),
        ("15", "0", 3, "P", "0"),
        ("1", "0", 2, "H\u1d43", "0"),
        ("7", "0", 3, "N", "0"),
    ],
)
def test_unproven_hydrogen_forms_fail_closed(element, charge, degree, label, count):
    a, _ = _scene(element, charge, degree, label)
    b = deepcopy(a)
    b.find(".//n").set("NumHydrogens", count)
    with pytest.raises(ValueError, match="hydrogen count"):
        _validate(a, b)
    with pytest.raises(ValueError, match="hydrogen count"):
        _validate(b, a)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Radical", "1"),
        ("Isotope", "18"),
        ("ImplicitHydrogens", "yes"),
        ("ElementList", "8 16"),
    ],
)
def test_query_isotope_and_radical_context_is_not_normalized(field, value):
    a, node = _scene()
    node.set(field, value)
    b = deepcopy(a)
    b.find(".//n").set("NumHydrogens", "0")
    with pytest.raises(ValueError, match="hydrogen count"):
        _validate(a, b)


def test_explicit_to_explicit_count_change_still_rejected():
    a, _ = _scene(hydrogens="0")
    b = deepcopy(a)
    b.find(".//n").set("NumHydrogens", "1")
    with pytest.raises(ValueError, match="hydrogen count"):
        _validate(a, b)


@pytest.mark.parametrize(
    "mutation", ["charge", "endpoint", "order", "fractional", "interpretation"]
)
def test_hydrogen_normalization_does_not_hide_other_chemistry_changes(mutation):
    a, _ = _scene()
    b = deepcopy(a)
    b.find(".//n").set("NumHydrogens", "0")
    if mutation == "charge":
        b.find(".//n").set("Charge", "1")
    elif mutation == "endpoint":
        b.find(".//b").set("E", "21")
    elif mutation in {"order", "fractional"}:
        b.find(".//b").set("Order", "2" if mutation == "order" else "1.5")
    else:
        b.find(".//t").set("InterpretChemically", "no")
    with pytest.raises(ValueError):
        _validate(a, b)


def _definitions():
    a, _ = _scene(element="6", degree=1, label=None)
    for owner in a.findall("./page/fragment/n"):
        owner_id = owner.get("id")
        owner.set("NodeType", "Fragment")
        owner.set("BondOrdering", "100")
        inner = ET.SubElement(
            owner, "fragment", id=f"{owner_id}0", ConnectionOrder=f"{owner_id}2"
        )
        ET.SubElement(inner, "n", id=f"{owner_id}1", p="0 0")
        ET.SubElement(
            inner, "n", id=f"{owner_id}2", NodeType="ExternalConnectionPoint", p="10 20"
        )
        ET.SubElement(inner, "b", id=f"{owner_id}3", B=f"{owner_id}1", E=f"{owner_id}2")
    # Keep IDs globally unique, including the outer bond 100.
    a.find(".//n/fragment").set("id", "900")
    return a


def test_definition_fragment_id_can_change_with_identical_owner_membership():
    a = _definitions()
    b = deepcopy(a)
    for index, fragment in enumerate(b.findall(".//n/fragment")):
        fragment.set("id", str(950 + index))
    _validate(a, b)
    _validate(b, a)


@pytest.mark.parametrize(
    "mutation",
    [
        "moved_definition",
        "moved_member",
        "bond_order",
        "bond_endpoint",
        "port_order",
        "bond_ordering",
        "duplicate_fragment",
        "id_collision",
        "top_fragment_id",
    ],
)
def test_renumbering_does_not_hide_changed_ownership_or_attachment(mutation):
    a = _definitions()
    b = deepcopy(a)
    owners = b.findall("./page/fragment/n")
    inner = owners[0].find("fragment")
    inner.set("id", "950")
    if mutation == "moved_definition":
        other = owners[1].find("fragment")
        owners[0].remove(inner)
        owners[1].remove(other)
        owners[0].append(other)
        owners[1].append(inner)
    elif mutation == "moved_member":
        atom = inner.find("n")
        inner.remove(atom)
        owners[1].find("fragment").append(atom)
    elif mutation == "bond_order":
        inner.find("b").set("Order", "2")
    elif mutation == "bond_endpoint":
        inner.find("b").set("E", "201")
    elif mutation == "port_order":
        inner.set("ConnectionOrder", "201")
    elif mutation == "bond_ordering":
        owners[0].set("BondOrdering", "103")
    elif mutation == "duplicate_fragment":
        ET.SubElement(owners[0], "fragment", id="999")
    elif mutation == "id_collision":
        inner.set("id", "10")
    else:
        b.find("./page/fragment").set("id", "999")
    with pytest.raises(ValueError):
        _validate(a, b)


@pytest.mark.parametrize("owner", ["b", "fragment", "page"])
@pytest.mark.parametrize("value", ["41.625", "31.635", "nan", "inf", "-1", "bad"])
def test_effective_bond_spacing_changes_fail_closed(owner, value):
    a, _ = _scene(label=None)
    a.set("BondSpacing", "15")
    a.find(".//b").set("Order", "2")
    a.find(".//" + owner).set("BondSpacing", "31.625")
    b = deepcopy(a)
    b.find(".//" + owner).set("BondSpacing", value)
    with pytest.raises(ValueError, match="bond spacing"):
        _validate(a, b)


def test_explicit_bond_spacing_can_use_identical_inherited_value():
    a, _ = _scene(label=None)
    a.set("BondSpacing", "31.625")
    a.find(".//b").set("BondSpacing", "31.625")
    b = deepcopy(a)
    b.find(".//b").attrib.pop("BondSpacing")
    _validate(a, b)
    _validate(b, a)


@pytest.mark.parametrize(
    "key,value", [("BondSpacing", "41.625"), ("BondSpacingAbs", "9")]
)
def test_new_bond_spacing_override_is_not_ignored(key, value):
    a, _ = _scene(label=None)
    a.set("BondSpacing", "31.625")
    b = deepcopy(a)
    b.find(".//b").set(key, value)
    with pytest.raises(ValueError, match="bond spacing"):
        _validate(a, b)
    with pytest.raises(ValueError, match="bond spacing"):
        _validate(b, a)
