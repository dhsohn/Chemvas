"""CDXML export regression tests for unbound Ph on stereo bond wide ends.

Synthetic fixtures only; no consumer roundtrip claims.
"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from copy import deepcopy

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

_PH_FORMULA = (6, 5)


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


def _ph_stereo_state(
    style: str,
    *,
    narrow_atom: int = 0,
    wide_atom: int = 1,
    center_symbol: str = "O",
):
    atoms = {
        narrow_atom: Atom(center_symbol, 0.0, 0.0, explicit_label=True),
        wide_atom: Atom("Ph", 25.0, 0.0, explicit_label=True),
    }
    return _simple_state(
        atoms=atoms,
        bonds=[Bond(narrow_atom, wide_atom, style=style)],
    )


def _export_cdxml(state, *, label_bindings=None):
    with offscreen_document_scene(state, command="test-cdxml-ph") as context:
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


def _node_ids_by_atom(root, plan, atoms):
    s = plan.out_w_pt / plan.source_w
    expected = {
        atom_id: ((atom.x - plan.source_x) * s, (atom.y - plan.source_y) * s)
        for atom_id, atom in atoms.items()
    }
    found = {}
    for node in _top_nodes(root):
        x, y = (float(value) for value in node.get("p").split())
        for atom_id, (ex, ey) in expected.items():
            if math.dist((x, y), (ex, ey)) < 1e-6:
                found[atom_id] = node.get("id")
    assert len(found) == len(atoms), "every exported atom must map to one node"
    return found


def _point(node):
    return tuple(float(value) for value in node.get("p").split())


def _assert_ph_inner_topology(group):
    (inner,) = group.findall("fragment")
    inner_nodes = inner.findall("n")
    (connection,) = [n for n in inner_nodes if n.get("NodeType") is not None]
    assert connection.get("NodeType") == "ExternalConnectionPoint"
    carbons = [n for n in inner_nodes if n.get("NodeType") is None]
    assert all(n.get("Element") is None for n in carbons)
    expected_carbons, expected_hydrogens = _PH_FORMULA
    assert len(carbons) == expected_carbons
    assert sum(int(n.get("NumHydrogens")) for n in carbons) == expected_hydrogens
    inner_bonds = inner.findall("b")
    valence = {n.get("id"): int(n.get("NumHydrogens")) for n in carbons}
    for bond in inner_bonds:
        for end in (bond.get("B"), bond.get("E")):
            if end in valence:
                valence[end] += int(bond.get("Order", "1"))
    assert set(valence.values()) == {4}
    (attachment,) = [
        b for b in inner_bonds if connection.get("id") in (b.get("B"), b.get("E"))
    ]
    assert attachment.get("Order") is None
    ring = [b.get("Order", "1") for b in inner_bonds if b is not attachment]
    assert sorted(ring) == ["1", "1", "1", "2", "2", "2"]


@pytest.mark.parametrize(
    ("style", "display"), [("wedge", "WedgeBegin"), ("hash", "WedgedHashBegin")]
)
def test_wide_end_ph_stereo_exports_native_display_and_b_e(style, display):
    state = _ph_stereo_state(style)
    xml_bytes, plan = _export_cdxml(state)
    root = ET.fromstring(xml_bytes)
    atoms = deserialize_model_state(state["model"]).atoms
    nodes = _node_ids_by_atom(root, plan, atoms)
    (stereo,) = _top_bonds(root)
    assert stereo.get("Display") == display
    assert stereo.get("Order") is None
    assert stereo.get("DoublePosition") is None
    assert stereo.get("B") == nodes[0]
    assert stereo.get("E") == nodes[1]
    center = next(n for n in _top_nodes(root) if n.get("id") == nodes[0])
    group = next(n for n in _top_nodes(root) if n.get("id") == nodes[1])
    assert center.get("Element") == "8"
    assert group.get("NodeType") == "Nickname"
    _assert_ph_inner_topology(group)


def test_wide_end_ph_hash_nested_fragment_formula_and_topology():
    state = _ph_stereo_state("hash")
    xml_bytes, _plan = _export_cdxml(state)
    root = ET.fromstring(xml_bytes)
    (group,) = [n for n in _top_nodes(root) if n.get("NodeType") == "Nickname"]
    _assert_ph_inner_topology(group)


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_refuse_ph_at_narrow_end_of_stereo_bond(style):
    state = _simple_state(
        atoms={
            0: Atom("Ph", 0.0, 0.0, explicit_label=True),
            1: Atom("O", 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1, style=style)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="wide end"):
        _export_cdxml(state)


@pytest.mark.parametrize("label", ["Me", "tBu"])
@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_refuse_other_group_labels_on_stereo_wide_end(label, style):
    atoms = {
        0: Atom("C", 0.0, 0.0),
        1: Atom(label, 25.0, 0.0, explicit_label=True),
    }
    state = _simple_state(atoms=atoms, bonds=[Bond(0, 1, style=style)])
    with pytest.raises(CdxmlUnsupportedObjectError, match="wedge or hash"):
        _export_cdxml(state)


@pytest.mark.parametrize(
    "center_label",
    ["Ar", "Me", "Et"],
)
def test_refuse_wide_end_ph_to_non_element_neighbor(center_label):
    state = _simple_state(
        atoms={
            0: Atom(center_label, 0.0, 0.0, explicit_label=True),
            1: Atom("Ph", 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1, style="wedge")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError):
        _export_cdxml(state)


def test_refuse_wide_end_ph_when_stereo_center_has_bound_argon():
    state = _ph_stereo_state("wedge", center_symbol="Ar")
    binding = {0: CdxmlLabelBinding.element_identity("Ar")}
    with pytest.raises(CdxmlUnsupportedObjectError, match="typed label binding"):
        _export_cdxml(state, label_bindings=binding)


_H_A = "H\u1d43"


def test_refuse_wide_end_ph_when_stereo_center_is_unbound_identifier_hydrogen():
    state = _ph_stereo_state("hash", center_symbol=_H_A)
    with pytest.raises(CdxmlUnsupportedObjectError):
        _export_cdxml(state)


def test_refuse_wide_end_ph_when_stereo_center_has_bound_identifier_hydrogen():
    state = _ph_stereo_state("hash", center_symbol=_H_A)
    binding = {0: CdxmlLabelBinding.element_identity("H")}
    with pytest.raises(CdxmlUnsupportedObjectError, match="typed label binding"):
        _export_cdxml(state, label_bindings=binding)


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_refuse_concrete_bound_phenyl_on_stereo_wide_end(style):
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1, style=style)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="wedge or hash"):
        _export_cdxml(state, label_bindings={1: CdxmlLabelBinding.aryl_fragment("Ph")})


@pytest.mark.parametrize(
    "style,display", [("wedge", "WedgeBegin"), ("hash", "WedgedHashBegin")]
)
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("symbol,element", [("O", "8"), ("P", "15")])
def test_generic_aryl_stereo_keeps_query_and_stored_narrow_to_wide_direction(
    style, display, mirror, symbol, element
):
    state = _simple_state(
        atoms={
            0: Atom(symbol, 25.0 if mirror else 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 0.0 if mirror else 25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1, style=style)],
    )
    before = deepcopy(state)
    raw, _ = _export_cdxml(state, label_bindings={1: CdxmlLabelBinding.generic_aryl()})
    assert state == before
    root = ET.fromstring(raw)
    fragment = root.find("./page/fragment")
    nodes = fragment.findall("n")
    assert len(nodes) == 2
    start = next(n for n in nodes if n.get("Element") == element)
    aryl = next(n for n in nodes if n.get("NodeType") == "Nickname")
    assert "".join(aryl.find("t").itertext()).strip() == "Ar"
    assert not root.findall('.//n[@Element="18"]')
    assert not root.findall(".//graphic")
    definition = aryl.find("fragment")
    query = definition.find('./n[@GenericNickname="ARY"]')
    port = definition.find('./n[@NodeType="ExternalConnectionPoint"]')
    assert len(definition.findall("n")) == 2
    assert query.get("NodeType") == "GenericNickname"
    assert query.get("Element") is None
    assert query.get("p") == aryl.get("p")
    assert port.get("p") == start.get("p")
    assert "".join(query.find("t").itertext()).strip() == "ARY"
    internal = definition.findall("b")
    assert len(internal) == 1
    assert (internal[0].get("B"), internal[0].get("E")) == (
        query.get("id"),
        port.get("id"),
    )
    assert internal[0].get("Order", "1") == "1"
    assert internal[0].get("Display", "Solid") == "Solid"
    outer = fragment.findall("b")
    assert len(outer) == 1
    assert (outer[0].get("B"), outer[0].get("E")) == (start.get("id"), aryl.get("id"))
    assert outer[0].get("Order", "1") == "1"
    assert outer[0].get("Display") == display
    with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
        _export_cdxml(state)


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_generic_aryl_stereo_refuses_reversed_painted_narrow_end(style):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF

    state = _simple_state(
        atoms={
            0: Atom("O", 0, 0, explicit_label=True),
            1: Atom("Ar", 25, 0, explicit_label=True),
        },
        bonds=[Bond(0, 1, style=style)],
    )
    with offscreen_document_scene(
        state, command="generic-aryl-stereo-direction"
    ) as context:
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170,
        )
        for item in context.state.bond_graphics_state.bond_items[0]:
            if style == "wedge":
                item.setPolygon(
                    QPolygonF([QPointF(25 - p.x(), -p.y()) for p in item.polygon()])
                )
            else:
                line = item.line()
                item.setLine(25 - line.x1(), -line.y1(), 25 - line.x2(), -line.y2())
        with pytest.raises(CdxmlUnsupportedObjectError, match="narrow"):
            preflight_cdxml(
                context,
                items,
                plan,
                label_bindings={1: CdxmlLabelBinding.generic_aryl()},
            )


@pytest.mark.parametrize("style", ["wedge", "hash"])
def test_refuse_wide_end_ph_with_charge_or_radical(style):
    for key, value in (("formal_charge", -1), ("radical_electrons", 1)):
        model = deserialize_model_state(_ph_stereo_state(style)["model"])
        model.set_atom_annotation(1, {key: value})
        state = _ph_stereo_state(style)
        state["model"] = serialize_model_state(model)
        with pytest.raises(CdxmlUnsupportedObjectError, match="charge or radical"):
            _export_cdxml(state)


def test_refuse_wide_end_ph_with_zero_length_attachment():
    atoms = {
        0: Atom("O", 0.0, 0.0, explicit_label=True),
        1: Atom("Ph", 0.0, 0.0, explicit_label=True),
    }
    state = _simple_state(atoms=atoms, bonds=[Bond(0, 1, style="wedge")])
    with pytest.raises(CdxmlUnsupportedObjectError, match="drawable attachment"):
        _export_cdxml(state)


def test_refuse_wide_end_ph_with_multiple_attachments():
    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ph", 25.0, 0.0, explicit_label=True),
            2: Atom("C", 50.0, 0.0),
        },
        bonds=[Bond(0, 1, style="wedge"), Bond(1, 2)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="found 2"):
        _export_cdxml(state)


def test_refuse_wide_end_ph_when_drawn_narrow_end_disagrees():
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF

    state = _ph_stereo_state("wedge")
    with offscreen_document_scene(state, command="test-cdxml-ph") as context:
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        (wedge,) = context.state.bond_graphics_state.bond_items[0]
        wedge.setPolygon(
            QPolygonF([QPointF(25.0, 0.0), QPointF(2.0, -1.5), QPointF(2.0, 1.5)])
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="narrow"):
            preflight_cdxml(context, items, plan)
