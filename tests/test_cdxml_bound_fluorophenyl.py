"""CDXML export regression tests for bound para-fluorophenyl (4-F-Ph).

Synthetic fixtures only; no consumer roundtrip claims.
"""

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
_COORD_TOLERANCE = 1e-6
_LENGTH_REL_TOLERANCE = 1e-9
_Z_LEAF_TAGS = ("n", "b", "t", "graphic", "arrow")
_Z_MAX = 32767


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


def _simple_state(*, atoms, bonds, atom_annotations=None):
    model = MoleculeModel(atoms=atoms, bonds=bonds)
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


def _bound_aryl_state(
    *,
    neighbor_xy: tuple[float, float],
    aryl_xy: tuple[float, float],
    reverse_bond: bool,
    neighbor_symbol: str = "O",
):
    atoms = {
        0: Atom(neighbor_symbol, neighbor_xy[0], neighbor_xy[1], explicit_label=True),
        1: Atom("Ar", aryl_xy[0], aryl_xy[1], explicit_label=True),
    }
    bond = Bond(1, 0) if reverse_bond else Bond(0, 1)
    return _simple_state(atoms=atoms, bonds=[bond])


def _export_bound(state, label_bindings):
    with offscreen_document_scene(state, command="test-cdxml-4fph") as context:
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
    nodes = inner.findall("n")
    bonds = inner.findall("b")
    return inner, nodes, bonds


def _assert_globally_unique_ids(root):
    ids = [
        element.get("id") for element in root.iter() if element.get("id") is not None
    ]
    assert len(ids) == len(set(ids))


def _assert_id_closure(nodes, bonds):
    node_ids = {n.get("id") for n in nodes}
    for bond in bonds:
        assert bond.get("B") in node_ids
        assert bond.get("E") in node_ids
        assert bond.get("B") != bond.get("E")


def _assert_cdxml_drawable_leaves_have_unique_z(root):
    """Every ``n``/``b``/``t``/``graphic`` leaf has one positive unique Z.

    Matches exporter ``_fragment_z_leaves`` / ``_assign_z``: each drawable leaf
    in the page fragment, including inner nickname chemical nodes, receives Z.
    """
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


def _carbon_nodes(nodes):
    return [n for n in nodes if n.get("NodeType") is None and n.get("Element") is None]


def _fluorine_node(nodes):
    found = [n for n in nodes if n.get("Element") == "9"]
    assert len(found) == 1
    return found[0]


def _connection_point(nodes):
    found = [n for n in nodes if n.get("NodeType") == "ExternalConnectionPoint"]
    assert len(found) == 1
    return found[0]


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


def _assert_ring_kekule_alternation(carbon_ids: set[str], ring_bonds):
    for carbon_id in carbon_ids:
        orders = []
        for bond in ring_bonds:
            if carbon_id in (bond.get("B"), bond.get("E")):
                orders.append(int(bond.get("Order", "1")))
        assert sorted(orders) == [1, 2]


def _assert_bound_para_fluorophenyl_graph(root, group, plan, state, reverse_bond: bool):
    assert group.get("NodeType") == "Nickname"
    assert _label_text(group) == "Ar"
    _, nodes, bonds = _inner_graph(group)
    assert len(nodes) == 8
    assert len(bonds) == 8
    _assert_globally_unique_ids(root)
    _assert_id_closure(nodes, bonds)

    carbons = _carbon_nodes(nodes)
    assert len(carbons) == 6
    assert sum(int(n.get("NumHydrogens")) for n in carbons) == 4

    fluorine = _fluorine_node(nodes)
    assert fluorine.get("NumHydrogens") == "0"

    connection = _connection_point(nodes)
    by_id = {n.get("id"): n for n in nodes}

    attachment = [b for b in bonds if connection.get("id") in (b.get("B"), b.get("E"))]
    assert len(attachment) == 1
    assert attachment[0].get("Order") is None
    ipso_id = attachment[0].get("B")
    assert attachment[0].get("E") == connection.get("id")
    ipso = by_id[ipso_id]
    assert _point(ipso) == pytest.approx(_point(group), abs=_COORD_TOLERANCE)

    atoms = deserialize_model_state(state["model"]).atoms
    neighbor = atoms[0]
    assert _point(connection) == pytest.approx(
        _expected_point(plan, neighbor), abs=_COORD_TOLERANCE
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
    _assert_ring_kekule_alternation(carbon_ids, ring_bonds)

    cf_bonds = [b for b in bonds if fluorine_id in (b.get("B"), b.get("E"))]
    assert len(cf_bonds) == 1
    assert cf_bonds[0].get("Order", "1") == "1"
    f_carbon_id = (
        cf_bonds[0].get("B")
        if cf_bonds[0].get("E") == fluorine_id
        else cf_bonds[0].get("E")
    )
    assert f_carbon_id in carbon_ids

    adjacency: dict[str, set[str]] = {cid: set() for cid in carbon_ids}
    for bond in ring_bonds:
        a, b = bond.get("B"), bond.get("E")
        adjacency[a].add(b)
        adjacency[b].add(a)
    assert _graph_distance(adjacency, ipso_id, f_carbon_id) == 3

    carbon_valence = {n.get("id"): int(n.get("NumHydrogens")) for n in carbons}
    for bond in bonds:
        order = int(bond.get("Order", "1"))
        for end in (bond.get("B"), bond.get("E")):
            if end in carbon_valence:
                carbon_valence[end] += order
    assert set(carbon_valence.values()) == {4}

    f_valence = int(fluorine.get("NumHydrogens", "0"))
    for bond in cf_bonds:
        f_valence += int(bond.get("Order", "1"))
    assert f_valence == 1

    outer_length = math.dist(_point(connection), _point(group))
    for bond in bonds:
        length = math.dist(_point(by_id[bond.get("B")]), _point(by_id[bond.get("E")]))
        assert math.isclose(
            length,
            outer_length,
            rel_tol=_LENGTH_REL_TOLERANCE,
            abs_tol=_COORD_TOLERANCE,
        )

    oxygen = next(n for n in _top_nodes(root) if n.get("Element") == "8")
    (outer,) = _top_bonds(root)
    first, second = (group, oxygen) if reverse_bond else (oxygen, group)
    assert (outer.get("B"), outer.get("E")) == (first.get("id"), second.get("id"))
    assert outer.get("Order") is None and outer.get("Display") is None


def _binding():
    return {1: CdxmlLabelBinding.aryl_fragment(_FRAGMENT)}


@pytest.mark.parametrize(
    ("neighbor_xy", "aryl_xy", "reverse_bond"),
    [
        ((0.0, 0.0), (25.0, 0.0), False),
        ((0.0, 0.0), (-30.0, 0.0), True),
        ((10.0, 5.0), (10.0, 30.0), False),
    ],
)
def test_bound_para_fluorophenyl_exports_nickname_graph(
    neighbor_xy, aryl_xy, reverse_bond
):
    state = _bound_aryl_state(
        neighbor_xy=neighbor_xy,
        aryl_xy=aryl_xy,
        reverse_bond=reverse_bond,
    )
    xml_bytes, plan = _export_bound(state, _binding())
    root = ET.fromstring(xml_bytes)
    group = _nickname_group(root)
    _assert_bound_para_fluorophenyl_graph(root, group, plan, state, reverse_bond)
    _assert_cdxml_drawable_leaves_have_unique_z(root)


def test_bound_para_fluorophenyl_export_is_deterministic():
    state = _bound_aryl_state(
        neighbor_xy=(0.0, 0.0), aryl_xy=(25.0, 0.0), reverse_bond=False
    )
    first, _ = _export_bound(state, _binding())
    second, _ = _export_bound(state, _binding())
    assert first == second


def test_bound_para_fluorophenyl_leaves_document_bytes_unchanged():
    state = _bound_aryl_state(
        neighbor_xy=(0.0, 0.0), aryl_xy=(25.0, 0.0), reverse_bond=False
    )
    before = json.dumps(copy.deepcopy(state), sort_keys=True)
    _export_bound(state, _binding())
    after = json.dumps(state, sort_keys=True)
    assert after == before


def test_raw_ar_without_binding_refuses_ambiguous_meaning():
    state = _bound_aryl_state(
        neighbor_xy=(0.0, 0.0), aryl_xy=(25.0, 0.0), reverse_bond=False
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
        _export_bound(state, {})


def test_unbound_literal_4_f_ph_label_refuses():
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("4-F-Ph", 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError):
        _export_bound(state, {})


@pytest.mark.parametrize(
    "fragment",
    ["2-F-Ph", "3-F-Ph", "MeOPh", "unknown-aryl"],
)
def test_bound_aryl_fragment_refuses_unverified_names(fragment):
    state = _bound_aryl_state(
        neighbor_xy=(0.0, 0.0), aryl_xy=(25.0, 0.0), reverse_bond=False
    )
    binding = {1: CdxmlLabelBinding.aryl_fragment(fragment)}
    with pytest.raises(CdxmlUnsupportedObjectError, match="no verified aryl"):
        _export_bound(state, binding)


def test_bound_para_fluorophenyl_refuses_non_ar_drawn_label():
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("N", 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="only to the label 'Ar'"):
        _export_bound(state, _binding())


@pytest.mark.parametrize(
    "annotation",
    [{"formal_charge": -1}, {"radical_electrons": 1}],
)
def test_bound_para_fluorophenyl_refuses_charge_or_radical(annotation):
    state = _bound_aryl_state(
        neighbor_xy=(0.0, 0.0), aryl_xy=(25.0, 0.0), reverse_bond=False
    )
    model = deserialize_model_state(state["model"])
    model.set_atom_annotation(1, annotation)
    state["model"] = serialize_model_state(model)
    with pytest.raises(CdxmlUnsupportedObjectError, match="charge or radical"):
        _export_bound(state, _binding())


def test_bound_para_fluorophenyl_refuses_missing_attachment():
    state = _simple_state(
        atoms={1: Atom("Ar", 25.0, 0.0, explicit_label=True)},
        bonds=[],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="found 0"):
        _export_bound(state, _binding())


def test_bound_para_fluorophenyl_refuses_multiple_attachments():
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 25.0, 0.0, explicit_label=True),
            2: Atom("C", 50.0, 0.0),
        },
        bonds=[Bond(0, 1), Bond(1, 2)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="found 2"):
        _export_bound(state, _binding())


def test_bound_para_fluorophenyl_refuses_zero_length_attachment():
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 0.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="drawable attachment"):
        _export_bound(state, _binding())


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_bound_para_fluorophenyl_exports_stereo_wide_end(style):
    atoms = {
        0: Atom("O", 0.0, 0.0, explicit_label=True),
        1: Atom("Ar", 25.0, 0.0, explicit_label=True),
    }
    state = _simple_state(atoms=atoms, bonds=[Bond(0, 1, style=style)])
    xml_bytes, _ = _export_bound(state, _binding())
    root = ET.fromstring(xml_bytes)
    (stereo,) = [b for b in _top_bonds(root) if b.get("Display") is not None]
    assert stereo.get("Order") is None
    assert stereo.get("Display") in {"WedgeBegin", "WedgedHashBegin"}


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_bound_para_fluorophenyl_refuses_stereo_at_narrow_ar_end(style):
    state = _simple_state(
        atoms={
            0: Atom("Ar", 0.0, 0.0, explicit_label=True),
            1: Atom("O", 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1, style=style)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="wide end"):
        _export_bound(state, {0: CdxmlLabelBinding.aryl_fragment(_FRAGMENT)})


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("order", "style", "match"),
    [
        (2, "double", "order 2"),
        (3, "triple", "order 3"),
    ],
)
def test_bound_para_fluorophenyl_refuses_non_single_attachment(
    reverse, order, style, match
):
    bond = (
        Bond(1, 0, order=order, style=style)
        if reverse
        else Bond(0, 1, order=order, style=style)
    )
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 25.0, 0.0, explicit_label=True),
        },
        bonds=[bond],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match=match):
        _export_bound(state, _binding())
