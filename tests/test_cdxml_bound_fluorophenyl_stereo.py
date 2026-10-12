"""CDXML export: bound 4-F-Ph on stereo bond wide ends (synthetic only)."""

from __future__ import annotations

import copy
import json
import math
import os
import xml.etree.ElementTree as ET
from collections import deque

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    deserialize_model_state,
    serialize_model_state,
    serialize_settings,
)
from chemvas.ui.export.export_cdxml import (
    CdxmlLabelBinding,
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService

pytestmark = pytest.mark.usefixtures("qt_application")

_FRAGMENT = "4-F-Ph"
_NARROW_ATOM = 6
_WIDE_ATOM = 11
_BOND_ID = 11
_ELEMENT_Z = {"C": None, "O": "8", "P": "15"}
_COORD_TOLERANCE = 1e-6
_LENGTH_REL_TOLERANCE = 1e-9
_Z_LEAF_TAGS = ("n", "b", "t", "graphic", "arrow")
_Z_MAX = 32767
_H_A = "H\u1d43"


def _settings(**overrides):
    defaults = dict(
        bond_length_px=20.0,
        arrow_line_width=1.5,
        arrow_head_scale=0.4,
        orbital_phase_enabled=True,
        text_font_size=12,
        text_font_weight=400,
        text_italic=False,
        sheet_size="A4",
        sheet_orientation="portrait",
    )
    defaults.update(overrides)
    return serialize_settings(**defaults)


def _state_from_model(model: MoleculeModel, atom_annotations=None):
    if atom_annotations:
        for aid, ann in atom_annotations.items():
            model.set_atom_annotation(aid, ann)
    return {
        "model": serialize_model_state(model),
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }


def _stereo_state(
    style: str,
    *,
    narrow_atom: int = _NARROW_ATOM,
    wide_atom: int = _WIDE_ATOM,
    bond_id: int = 0,
    narrow_xy: tuple[float, float] = (0.0, 0.0),
    wide_xy: tuple[float, float] = (25.0, 0.0),
    center_symbol: str = "C",
    reverse_bond: bool = False,
):
    model = MoleculeModel(
        atoms={
            narrow_atom: Atom(
                center_symbol,
                narrow_xy[0],
                narrow_xy[1],
                explicit_label=True,
            ),
            wide_atom: Atom("Ar", wide_xy[0], wide_xy[1], explicit_label=True),
        },
        bonds=[],
    )
    if reverse_bond:
        bond = Bond(wide_atom, narrow_atom, style=style)
    else:
        bond = Bond(narrow_atom, wide_atom, style=style)
    model.set_bond(bond_id, bond)
    return _state_from_model(model)


def _real_atom11_bond11_state(style: str):
    atoms: dict[int, Atom] = {
        _NARROW_ATOM: Atom("P", 0.0, 0.0, explicit_label=True),
        _WIDE_ATOM: Atom("Ar", 25.0, 0.0, explicit_label=True),
    }
    for index in range(12):
        atoms[100 + index] = Atom("C", 250.0 + 20.0 * index, 150.0)
    model = MoleculeModel(atoms=atoms, bonds=[])
    for bond_slot in range(11):
        model.set_bond(bond_slot, Bond(100 + bond_slot, 101 + bond_slot))
    model.set_bond(_BOND_ID, Bond(_NARROW_ATOM, _WIDE_ATOM, style=style))
    return _state_from_model(model)


def _plain_single_state(
    *,
    narrow_xy: tuple[float, float] = (0.0, 0.0),
    wide_xy: tuple[float, float] = (25.0, 0.0),
):
    return _stereo_state(
        "single",
        narrow_xy=narrow_xy,
        wide_xy=wide_xy,
        bond_id=0,
    )


def _binding(atom_id: int = _WIDE_ATOM):
    return {atom_id: CdxmlLabelBinding.aryl_fragment(_FRAGMENT)}


def _export_bound(state, label_bindings):
    with offscreen_document_scene(state, command="test-cdxml-4fph-stereo") as context:
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        preflight_cdxml(context, items, plan, label_bindings=label_bindings)
        xml_bytes = serialize_cdxml(context, items, plan, label_bindings=label_bindings)
        return xml_bytes, plan


def _page_fragments(root):
    return root.find("page").findall("fragment")


def _top_nodes(root):
    return [n for frag in _page_fragments(root) for n in frag.findall("n")]


def _top_bonds(root):
    return [b for frag in _page_fragments(root) for b in frag.findall("b")]


def _point(node):
    return tuple(float(value) for value in node.get("p").split())


def _label_text(node):
    (t,) = node.findall("t")
    return "".join(s.text or "" for s in t.findall("s"))


def _expected_point(plan, atom):
    s = plan.out_w_pt / plan.source_w
    return ((atom.x - plan.source_x) * s, (atom.y - plan.source_y) * s)


def _nickname_group(root):
    groups = [n for n in _top_nodes(root) if n.get("NodeType") == "Nickname"]
    assert len(groups) == 1
    return groups[0]


def _inner_graph(group):
    (inner,) = group.findall("fragment")
    return inner.findall("n"), inner.findall("b")


def _node_ids_by_atom(root, plan, atoms, atom_ids):
    s = plan.out_w_pt / plan.source_w
    expected = {
        atom_id: (
            (atoms[atom_id].x - plan.source_x) * s,
            (atoms[atom_id].y - plan.source_y) * s,
        )
        for atom_id in atom_ids
    }
    found = {}
    for node in _top_nodes(root):
        x, y = (float(value) for value in node.get("p").split())
        for atom_id, (ex, ey) in expected.items():
            if math.dist((x, y), (ex, ey)) < _COORD_TOLERANCE:
                found[atom_id] = node.get("id")
    assert set(found) == set(atom_ids)
    return found


def _assert_globally_unique_ids(root):
    ids = [el.get("id") for el in root.iter() if el.get("id") is not None]
    assert len(ids) == len(set(ids))


def _assert_no_isotope(root):
    for node in root.iter("n"):
        assert node.get("Isotope") is None


def _assert_cdxml_drawable_leaves_have_unique_z(root):
    values: list[int] = []
    for element in root.iter():
        if element.tag not in _Z_LEAF_TAGS:
            continue
        z_attr = element.get("Z")
        assert z_attr is not None, f"drawable leaf <{element.tag}> is missing Z"
        z = int(z_attr)
        values.append(z)
    assert values
    assert all(0 < z <= _Z_MAX for z in values)
    assert len(values) == len(set(values))


def _graph_distance(adjacency: dict[str, set[str]], start: str, goal: str) -> int:
    if start == goal:
        return 0
    seen = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        for neighbor in adjacency.get(node, ()):
            if neighbor in seen:
                continue
            if neighbor == goal:
                return depth + 1
            seen.add(neighbor)
            queue.append((neighbor, depth + 1))
    raise AssertionError(f"no path from {start} to {goal}")


def _assert_stereo_wide_graph(
    root,
    group,
    plan,
    state,
    *,
    narrow_atom: int,
    wide_atom: int,
    display: str,
    center_symbol: str | None = None,
):
    assert group.get("NodeType") == "Nickname"
    assert _label_text(group) == "Ar"
    nodes, bonds = _inner_graph(group)
    assert len(nodes) == 8
    assert len(bonds) == 8
    _assert_globally_unique_ids(root)
    _assert_no_isotope(root)

    carbons = [
        n for n in nodes if n.get("NodeType") is None and n.get("Element") is None
    ]
    assert len(carbons) == 6
    assert sum(int(n.get("NumHydrogens")) for n in carbons) == 4
    (fluorine,) = [n for n in nodes if n.get("Element") == "9"]
    assert fluorine.get("NumHydrogens") == "0"
    (connection,) = [n for n in nodes if n.get("NodeType") == "ExternalConnectionPoint"]

    by_id = {n.get("id"): n for n in nodes}
    attachment = [b for b in bonds if connection.get("id") in (b.get("B"), b.get("E"))]
    assert len(attachment) == 1
    assert attachment[0].get("Order") is None
    ipso_id = attachment[0].get("B")
    assert attachment[0].get("E") == connection.get("id")
    assert _point(by_id[ipso_id]) == pytest.approx(_point(group), abs=_COORD_TOLERANCE)

    atoms = deserialize_model_state(state["model"]).atoms
    assert _point(connection) == pytest.approx(
        _expected_point(plan, atoms[narrow_atom]), abs=_COORD_TOLERANCE
    )

    carbon_ids = {n.get("id") for n in carbons}
    fluorine_id = fluorine.get("id")
    ring_bonds = [
        b
        for b in bonds
        if b.get("B") in carbon_ids
        and b.get("E") in carbon_ids
        and b is not attachment[0]
    ]
    assert len(ring_bonds) == 6
    for carbon_id in carbon_ids:
        orders = [
            int(b.get("Order", "1"))
            for b in ring_bonds
            if carbon_id in (b.get("B"), b.get("E"))
        ]
        assert sorted(orders) == [1, 2]

    (cf_bond,) = [b for b in bonds if fluorine_id in (b.get("B"), b.get("E"))]
    assert cf_bond.get("Order", "1") == "1"
    f_carbon_id = (
        cf_bond.get("B") if cf_bond.get("E") == fluorine_id else cf_bond.get("E")
    )
    adjacency = {cid: set() for cid in carbon_ids}
    for bond in ring_bonds:
        a, b = bond.get("B"), bond.get("E")
        adjacency[a].add(b)
        adjacency[b].add(a)
    assert _graph_distance(adjacency, ipso_id, f_carbon_id) == 3

    nodes_by_atom = _node_ids_by_atom(root, plan, atoms, {narrow_atom, wide_atom})
    (stereo,) = [b for b in _top_bonds(root) if b.get("Display") is not None]
    assert stereo.get("Display") == display
    assert stereo.get("Order") is None
    assert stereo.get("B") == nodes_by_atom[narrow_atom]
    assert stereo.get("E") == nodes_by_atom[wide_atom]

    assert (stereo.get("B"), stereo.get("E")) == (
        nodes_by_atom[narrow_atom],
        nodes_by_atom[wide_atom],
    )

    if center_symbol is not None:
        expected_z = _ELEMENT_Z[center_symbol]
        narrow_node = next(
            n for n in _top_nodes(root) if n.get("id") == nodes_by_atom[narrow_atom]
        )
        if expected_z is None:
            assert narrow_node.get("Element") is None
        else:
            assert narrow_node.get("Element") == expected_z

    outer_length = math.dist(_point(connection), _point(group))
    for bond in bonds:
        length = math.dist(_point(by_id[bond.get("B")]), _point(by_id[bond.get("E")]))
        assert math.isclose(
            length,
            outer_length,
            rel_tol=_LENGTH_REL_TOLERANCE,
            abs_tol=_COORD_TOLERANCE,
        )


def test_real_atom11_bond11_wide_hash():
    """Synthetic regression for atom 6 (P) / atom 11 / bond slot 11 (hash)."""
    state = _real_atom11_bond11_state("hash")
    model = deserialize_model_state(state["model"])
    stereo_bond = model.bonds[_BOND_ID]
    assert stereo_bond is not None
    assert stereo_bond.a == _NARROW_ATOM and stereo_bond.b == _WIDE_ATOM
    assert stereo_bond.style == "hash" and stereo_bond.order == 1
    xml_bytes, plan = _export_bound(state, _binding())
    root = ET.fromstring(xml_bytes)
    group = _nickname_group(root)
    _assert_stereo_wide_graph(
        root,
        group,
        plan,
        state,
        narrow_atom=_NARROW_ATOM,
        wide_atom=_WIDE_ATOM,
        display="WedgedHashBegin",
        center_symbol="P",
    )
    _assert_cdxml_drawable_leaves_have_unique_z(root)


@pytest.mark.parametrize(
    ("style", "display"),
    [("hash", "WedgedHashBegin"), ("wedge", "WedgeBegin")],
)
@pytest.mark.parametrize("center_symbol", ["C", "O", "P"])
@pytest.mark.parametrize(
    ("narrow_xy", "wide_xy"),
    [
        ((0.0, 0.0), (25.0, 0.0)),
        ((0.0, 0.0), (-30.0, 0.0)),
        ((10.0, 5.0), (10.0, 30.0)),
    ],
)
def test_bound_para_fluorophenyl_stereo_wide_end_exports_graph(
    style, display, center_symbol, narrow_xy, wide_xy
):
    state = _stereo_state(
        style,
        narrow_xy=narrow_xy,
        wide_xy=wide_xy,
        center_symbol=center_symbol,
    )
    xml_bytes, plan = _export_bound(state, _binding())
    root = ET.fromstring(xml_bytes)
    group = _nickname_group(root)
    _assert_stereo_wide_graph(
        root,
        group,
        plan,
        state,
        narrow_atom=_NARROW_ATOM,
        wide_atom=_WIDE_ATOM,
        display=display,
        center_symbol=center_symbol,
    )
    _assert_cdxml_drawable_leaves_have_unique_z(root)


def test_bound_para_fluorophenyl_stereo_plain_single_still_exports():
    state = _plain_single_state()
    xml_bytes, plan = _export_bound(state, _binding())
    root = ET.fromstring(xml_bytes)
    group = _nickname_group(root)
    nodes, bonds = _inner_graph(group)
    assert len(nodes) == 8 and len(bonds) == 8
    (outer,) = _top_bonds(root)
    assert outer.get("Display") is None and outer.get("Order") is None
    _assert_cdxml_drawable_leaves_have_unique_z(root)


def test_bound_para_fluorophenyl_stereo_export_is_deterministic():
    state = _stereo_state("hash")
    first, _ = _export_bound(state, _binding())
    second, _ = _export_bound(state, _binding())
    assert first == second


def test_bound_para_fluorophenyl_stereo_leaves_document_unchanged():
    state = _stereo_state("hash")
    before = json.dumps(copy.deepcopy(state), sort_keys=True)
    _export_bound(state, _binding())
    assert json.dumps(state, sort_keys=True) == before


@pytest.mark.parametrize("style", ["hash", "wedge"])
def test_refuse_bound_4f_aryl_at_narrow_stereo_end(style):
    state = _stereo_state(style, reverse_bond=True)
    with pytest.raises(CdxmlUnsupportedObjectError, match="wide end"):
        _export_bound(state, _binding())


def test_raw_ar_without_binding_refuses_ambiguous_meaning():
    state = _stereo_state("hash")
    with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
        _export_bound(state, {})


@pytest.mark.parametrize(
    "binding",
    [
        CdxmlLabelBinding.generic_aryl(),
        CdxmlLabelBinding.aryl_fragment("Ph"),
    ],
)
def test_bound_generic_and_fixed_phenyl_stereo_contracts(binding):
    state = _stereo_state("hash")
    if binding.meaning == "generic_aryl":
        xml_bytes, _ = _export_bound(state, {_WIDE_ATOM: binding})
        root = ET.fromstring(xml_bytes)
        node = root.find('.//n[@NodeType="Nickname"]')
        assert node.find('./fragment/n[@GenericNickname="ARY"]') is not None
        bond = root.find("./page/fragment/b")
        assert bond.get("E") == node.get("id")
        assert bond.get("Display") == "WedgedHashBegin"
    else:
        with pytest.raises(CdxmlUnsupportedObjectError, match="wedge or hash"):
            _export_bound(state, {_WIDE_ATOM: binding})


@pytest.mark.parametrize("fragment", ["2-F-Ph", "3-F-Ph", "MeOPh"])
def test_refuse_unknown_bound_aryl_on_stereo_wide_end(fragment):
    state = _stereo_state("hash")
    with pytest.raises(CdxmlUnsupportedObjectError, match="no verified aryl"):
        _export_bound(state, {_WIDE_ATOM: CdxmlLabelBinding.aryl_fragment(fragment)})


def test_refuse_stereo_wide_end_with_non_ar_drawn_alias_label():
    model = MoleculeModel(
        atoms={
            _NARROW_ATOM: Atom("C", 0.0, 0.0),
            _WIDE_ATOM: Atom("Me", 25.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(_NARROW_ATOM, _WIDE_ATOM, style="hash"))
    state = _state_from_model(model)
    with pytest.raises(CdxmlUnsupportedObjectError, match="alias registry"):
        _export_bound(state, {_WIDE_ATOM: CdxmlLabelBinding.aryl_fragment(_FRAGMENT)})


def test_refuse_stereo_wide_end_binding_only_applies_to_ar_drawn_label():
    state = _state_from_model(
        MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("N", 25.0, 0.0, explicit_label=True),
            },
            bonds=[Bond(0, 1, style="hash")],
        )
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="only to the label 'Ar'"):
        _export_bound(state, {1: CdxmlLabelBinding.aryl_fragment(_FRAGMENT)})


@pytest.mark.parametrize(
    ("center_label", "binding"),
    [
        ("C", CdxmlLabelBinding.element_identity("C")),
        ("P", CdxmlLabelBinding.element_identity("P")),
        (_H_A, CdxmlLabelBinding.element_identity("H")),
        ("Ar", CdxmlLabelBinding.element_identity("Ar")),
    ],
)
def test_refuse_stereo_center_with_bound_element_identity(center_label, binding):
    state = _stereo_state("hash", center_symbol=center_label)
    bindings = {
        _NARROW_ATOM: binding,
        _WIDE_ATOM: CdxmlLabelBinding.aryl_fragment(_FRAGMENT),
    }
    with pytest.raises(CdxmlUnsupportedObjectError, match="typed label binding"):
        _export_bound(state, bindings)


def test_refuse_stereo_center_unbound_identifier_hydrogen():
    state = _stereo_state("hash", center_symbol=_H_A)
    with pytest.raises(CdxmlUnsupportedObjectError):
        _export_bound(state, _binding())


def test_refuse_stereo_center_unbound_raw_ar_label():
    model = MoleculeModel(
        atoms={
            _NARROW_ATOM: Atom("Ar", 0.0, 0.0, explicit_label=True),
            _WIDE_ATOM: Atom("Ar", 25.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(_NARROW_ATOM, _WIDE_ATOM, style="hash"))
    state = _state_from_model(model)
    with pytest.raises(CdxmlUnsupportedObjectError):
        _export_bound(state, _binding())


@pytest.mark.parametrize(
    "annotation",
    [{"formal_charge": -1}, {"radical_electrons": 1}],
)
def test_refuse_bound_4f_stereo_wide_end_charge_or_radical(annotation):
    state = _stereo_state("hash")
    model = deserialize_model_state(state["model"])
    model.set_atom_annotation(_WIDE_ATOM, annotation)
    state["model"] = serialize_model_state(model)
    with pytest.raises(CdxmlUnsupportedObjectError, match="charge or radical"):
        _export_bound(state, _binding())


def test_refuse_bound_4f_stereo_missing_attachment():
    state = _state_from_model(
        MoleculeModel(
            atoms={_WIDE_ATOM: Atom("Ar", 25.0, 0.0, explicit_label=True)}, bonds=[]
        )
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="found 0"):
        _export_bound(state, _binding())


def test_refuse_bound_4f_stereo_multiple_attachments():
    model = MoleculeModel(
        atoms={
            _NARROW_ATOM: Atom("C", 0.0, 0.0),
            _WIDE_ATOM: Atom("Ar", 25.0, 0.0, explicit_label=True),
            12: Atom("N", 50.0, 0.0),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(_NARROW_ATOM, _WIDE_ATOM, style="hash"))
    model.set_bond(1, Bond(_WIDE_ATOM, 12))
    state = _state_from_model(model)
    with pytest.raises(CdxmlUnsupportedObjectError, match="found 2"):
        _export_bound(state, _binding())


def test_refuse_bound_4f_stereo_zero_length_attachment():
    state = _stereo_state("hash", wide_xy=(0.0, 0.0))
    with pytest.raises(CdxmlUnsupportedObjectError, match="drawable attachment"):
        _export_bound(state, _binding())


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("order", "style", "match"),
    [
        (2, "double", "order 2"),
        (3, "triple", "order 3"),
    ],
)
def test_refuse_bound_4f_stereo_non_order_one(reverse, order, style, match):
    bond = (
        Bond(_WIDE_ATOM, _NARROW_ATOM, order=order, style=style)
        if reverse
        else Bond(_NARROW_ATOM, _WIDE_ATOM, order=order, style=style)
    )
    model = MoleculeModel(
        atoms={
            _NARROW_ATOM: Atom("C", 0.0, 0.0),
            _WIDE_ATOM: Atom("Ar", 25.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, bond)
    with pytest.raises(CdxmlUnsupportedObjectError, match=match):
        _export_bound(_state_from_model(model), _binding())
