"""Tests for CDXML export.

Synthetic in-test documents only. The vendor DTD is not committed; vocabulary
closure is verified structurally.
"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    deserialize_model_state,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.export import points_for_mm
from chemvas.ui.export.export_cdxml import (
    CdxmlLabelBinding,
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService

pytestmark = pytest.mark.usefixtures("qt_application")


# ── Helpers ────────────────────────────────────────────────────────────


def _line_endpoints(line):
    assert line.tag == "arrow"
    assert line.get("ArrowheadHead", "None") == "None"
    assert line.get("ArrowheadTail", "None") == "None"
    tail, head = line.get("Tail3D").split(), line.get("Head3D").split()
    assert tail[2] == head[2] == "0"
    return " ".join((*tail[:2], *head[:2]))


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


def _simple_state(
    atoms=None,
    bonds=None,
    notes=None,
    arrows=None,
    shapes=None,
    atom_annotations=None,
    settings_overrides=None,
    marks=None,
    groups=None,
    ring_fills=None,
):
    if atoms is None:
        atoms = {0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)}
    if bonds is None:
        bonds = [Bond(0, 1)]
    model = MoleculeModel(atoms=atoms, bonds=bonds)
    if atom_annotations:
        for aid, ann in atom_annotations.items():
            model.set_atom_annotation(aid, ann)
    result = {
        "model": serialize_model_state(model),
        "ring_fills": ring_fills or [],
        "notes": notes or [],
        "marks": marks or [],
        "arrows": arrows or [],
        "ts_brackets": [],
        "shapes": shapes or [],
        "orbitals": [],
        "settings": _settings(**(settings_overrides or {})),
        "last_smiles_input": None,
    }
    if groups is not None:
        result["groups"] = groups
    return result


def _export_cdxml(state, *, target_width_mm=170.0, scope="sheet", groups=None):
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context, groups=groups)
        items, plan = service._resolve_figure_export(
            scope=scope,
            selection=None,
            sizing="custom",
            target_width_mm=target_width_mm,
        )
        preflight_cdxml(context, items, plan, groups=groups)
        return serialize_cdxml(context, items, plan, groups=groups), plan


def _parse_cdxml(xml_bytes):
    return ET.fromstring(xml_bytes)


# ── Closed vocabulary ──────────────────────────────────────────────────

_ALLOWED_ELEMENTS = frozenset(
    {
        "CDXML",
        "colortable",
        "color",
        "fonttable",
        "font",
        "page",
        "fragment",
        "n",
        "b",
        "t",
        "s",
        "graphic",
        "arrow",
        "group",
    }
)

_ALLOWED_ATTRS_BY_ELEMENT = {
    "CDXML": {
        "BondLength",
        "BoldWidth",
        "LineWidth",
        "HashSpacing",
        "BondSpacing",
        "InterpretChemically",
        "FractionalWidths",
        "CreationProgram",
        "bgcolor",
    },
    "colortable": set(),
    "color": {"r", "g", "b"},
    "fonttable": set(),
    "font": {"id", "charset", "name"},
    "page": {"id", "Width", "Height", "BoundingBox", "bgcolor"},
    "fragment": {"id"},
    "n": {"id", "p", "Z", "Element", "Charge", "color"},
    "b": {
        "id",
        "B",
        "E",
        "Z",
        "Order",
        "Display",
        "DoublePosition",
        "BondSpacing",
        "color",
    },
    "t": {
        "id",
        "p",
        "Z",
        "Justification",
        "LabelJustification",
        "InterpretChemically",
        "CaptionLineHeight",
    },
    "s": {"font", "size", "color", "face"},
    "graphic": {
        "id",
        "Z",
        "GraphicType",
        "ArrowType",
        "LineType",
        "BoundingBox",
        "LineWidth",
        "color",
        "OvalType",
        "RectangleType",
        "Center3D",
        "MajorAxisEnd3D",
        "MinorAxisEnd3D",
    },
    "arrow": {
        "id",
        "Z",
        "FillType",
        "ArrowheadType",
        "LineType",
        "Head3D",
        "Tail3D",
        "LineWidth",
        "color",
    },
    "group": {"id"},
}

# ZOrder.htm lists Z for Node, Bond, Text and Graphic (not Group, Fragment or
# Page); every one of these elements carries its own explicit Z.
_Z_TAGS = ("n", "b", "t", "graphic", "arrow")


def test_vocabulary_closure():
    state = _simple_state()
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)

    for el in root.iter():
        tag = el.tag
        assert tag in _ALLOWED_ELEMENTS, f"unexpected element: {tag}"
        allowed = _ALLOWED_ATTRS_BY_ELEMENT.get(tag, set())
        for attr in el.attrib:
            assert attr in allowed, f"unexpected attribute {attr} on <{tag}>"


# ── Chemistry: connectivity, charge, element ───────────────────────────


def test_fragment_nodes_and_bonds():
    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)

    fragments = root.findall(".//fragment")
    assert len(fragments) == 1

    nodes = fragments[0].findall("n")
    assert len(nodes) == 2

    elements = {n.get("Element") for n in nodes}
    assert "7" in elements
    assert "8" in elements

    bonds = fragments[0].findall("b")
    assert len(bonds) == 1


def test_carbon_default_element():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    nodes = root.findall(".//n")
    for n in nodes:
        assert n.get("Element") is None


def test_formal_charge():
    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"formal_charge": 1}},
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    nodes = root.findall(".//n")
    charged = [n for n in nodes if n.get("Charge") is not None]
    assert len(charged) == 1
    assert charged[0].get("Charge") == "1"


def test_bond_orders():
    state = _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 20.0, 0.0),
            2: Atom("N", 40.0, 0.0),
        },
        bonds=[
            Bond(0, 1, order=2, style="double_center"),
            Bond(1, 2, order=3, style="triple"),
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    bonds = root.findall(".//b")
    orders = {b.get("Order") for b in bonds}
    assert "2" in orders
    assert "3" in orders


def test_double_center_position():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=2, style="double_center")],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    bond = root.find(".//b")
    assert bond is not None
    assert bond.get("DoublePosition") == "Center"


def test_multiple_components():
    state = _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 20.0, 0.0),
            2: Atom("N", 50.0, 0.0),
            3: Atom("S", 70.0, 0.0),
        },
        bonds=[Bond(0, 1), Bond(2, 3)],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    fragments = root.findall(".//fragment")
    assert len(fragments) == 2


# ── Geometry: 170 mm scaling ───────────────────────────────────────────


def test_170mm_page_width():
    state = _simple_state()
    xml_bytes, plan = _export_cdxml(state, target_width_mm=170.0)
    root = _parse_cdxml(xml_bytes)
    page = root.find("page")
    assert page is not None
    width = float(page.get("Width"))
    expected = points_for_mm(170.0)
    assert width == pytest.approx(expected, rel=1e-9)


def test_second_width_exact_ratio():
    state = _simple_state(
        arrows=[
            {
                "kind": "line",
                "start": [5.0, 100.0],
                "end": [25.0, 100.0],
                "control": None,
                "double": False,
            }
        ],
    )
    bytes_170, plan_170 = _export_cdxml(state, target_width_mm=170.0)
    bytes_84, plan_84 = _export_cdxml(state, target_width_mm=84.0)

    root_170 = _parse_cdxml(bytes_170)
    root_84 = _parse_cdxml(bytes_84)

    page_170 = root_170.find("page")
    page_84 = root_84.find("page")
    w170 = float(page_170.get("Width"))
    w84 = float(page_84.get("Width"))

    expected_ratio = points_for_mm(170.0) / points_for_mm(84.0)
    actual_ratio = w170 / w84
    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-9)

    nodes_170 = root_170.findall(".//n")
    nodes_84 = root_84.findall(".//n")

    assert len(nodes_170) >= 2, "expected at least 2 nodes at 170 mm"
    assert len(nodes_84) >= 2, "expected at least 2 nodes at 84 mm"

    def node_x(n):
        return float(n.get("p").split()[0])

    span_170 = abs(node_x(nodes_170[1]) - node_x(nodes_170[0]))
    span_84 = abs(node_x(nodes_84[1]) - node_x(nodes_84[0]))
    assert span_84 > 0, "84 mm span must be positive"
    coord_ratio = span_170 / span_84
    assert coord_ratio == pytest.approx(expected_ratio, rel=1e-9)

    bl_170 = float(root_170.get("BondLength"))
    bl_84 = float(root_84.get("BondLength"))
    assert bl_170 / bl_84 == pytest.approx(expected_ratio, rel=1e-9)

    lw_170 = float(root_170.get("LineWidth"))
    lw_84 = float(root_84.get("LineWidth"))
    assert lw_170 / lw_84 == pytest.approx(expected_ratio, rel=1e-9)

    def line_bbox_span(root):
        for g in root.findall(".//arrow"):
            if g.get("LineType") == "Solid":
                vals = [float(v) for v in _line_endpoints(g).split()]
                return abs(vals[2] - vals[0])
        return None

    line_span_170 = line_bbox_span(root_170)
    line_span_84 = line_bbox_span(root_84)
    assert line_span_170 is not None and line_span_84 is not None
    assert line_span_84 > 0
    assert line_span_170 / line_span_84 == pytest.approx(expected_ratio, rel=1e-9)

    def first_font_size(root):
        s_el = root.find(".//s")
        return float(s_el.get("size")) if s_el is not None else None

    size_170 = first_font_size(root_170)
    size_84 = first_font_size(root_84)
    assert size_170 is not None and size_84 is not None and size_84 > 0
    assert abs(size_170 - expected_ratio * size_84) <= 0.025 * (1 + expected_ratio)
    assert all(abs(v * 20 - round(v * 20)) < 1e-8 for v in (size_170, size_84))


def test_font_size_scales_with_width():
    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    bytes_170, _ = _export_cdxml(state, target_width_mm=170.0)
    bytes_84, _ = _export_cdxml(state, target_width_mm=84.0)

    def first_font_size(xml_bytes):
        root = _parse_cdxml(xml_bytes)
        s = root.find(".//s")
        return float(s.get("size")) if s is not None else None

    size_170 = first_font_size(bytes_170)
    size_84 = first_font_size(bytes_84)
    assert size_170 is not None, "expected font size at 170 mm"
    assert size_84 is not None and size_84 > 0, "expected positive font size at 84 mm"
    expected = points_for_mm(170.0) / points_for_mm(84.0)
    assert abs(size_170 - expected * size_84) <= 0.025 * (1 + expected)
    assert all(abs(v * 20 - round(v * 20)) < 1e-8 for v in (size_170, size_84))


# ── Unicode and XML characters ─────────────────────────────────────────


def test_xml_special_characters_in_note():
    state = _simple_state(
        notes=[{"text": '<&"testé>', "x": 0.0, "y": 30.0}],
    )
    xml_bytes, _ = _export_cdxml(state)
    xml_text = xml_bytes.decode("utf-8")
    assert "&amp;" in xml_text, "expected &amp; encoding in raw XML"
    assert "&lt;" in xml_text, "expected &lt; encoding in raw XML"
    root = ET.fromstring(xml_bytes)
    page = root.find("page")
    assert page is not None
    note_ts = [t for t in page.findall("t") if t.get("InterpretChemically") == "no"]
    assert len(note_ts) >= 1, "expected at least one note <t>"
    s_elements = note_ts[0].findall("s")
    texts = [s.text for s in s_elements if s.text]
    full = "".join(texts)
    assert full == '<&"testé>', (
        f"parsed note text must equal exact source, got: {full!r}"
    )


def test_unicode_element_labels():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("N", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    xml_bytes, _ = _export_cdxml(state)
    ET.fromstring(xml_bytes)


# ── Unique IDs ─────────────────────────────────────────────────────────


def test_unique_ids():
    state = _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("N", 20.0, 0.0),
            2: Atom("O", 40.0, 0.0),
        },
        bonds=[Bond(0, 1), Bond(1, 2)],
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 30.0,
                "shape_kind": "rect",
                "stroke_style": "none",
                "fill": "#ff0000",
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    ids = []
    for el in root.iter():
        eid = el.get("id")
        if eid is not None:
            ids.append(eid)
    assert len(ids) == len(set(ids)), f"duplicate IDs: {ids}"


# ── Unsupported objects: atomic refusal ────────────────────────────────


def test_refuse_alias_label():
    state = _simple_state(
        atoms={0: Atom("CO2Me", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="pure element"):
        _export_cdxml(state)


@pytest.mark.parametrize("bond_length", [20.0, 35.0])
@pytest.mark.parametrize("target_width", [84.0, 170.0])
def test_native_bold_bond_keeps_connectivity_and_scaled_width(
    bond_length, target_width
):
    state = _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 40.0, 20.0),
            2: Atom("C", 80.0, 20.0),
        },
        bonds=[Bond(0, 1, style="bold_in", color="#cc2200"), Bond(1, 2)],
        settings_overrides={"bond_length_px": bond_length},
    )
    xml_bytes, plan = _export_cdxml(state, target_width_mm=target_width)
    root = ET.fromstring(xml_bytes)
    nodes = root.findall(".//fragment/n")
    bold, normal = root.findall(".//fragment/b")
    assert bold.get("B") == nodes[0].get("id")
    assert bold.get("E") == normal.get("B") == nodes[1].get("id")
    assert normal.get("E") == nodes[2].get("id")
    assert bold.get("Display") == "Bold" and bold.get("Order") == "1"
    assert normal.get("Display") is None and normal.get("BoldWidth") is None
    assert bold.get("color") is not None and normal.get("color") is None
    scale = plan.out_w_pt / plan.source_w
    assert float(bold.get("BoldWidth")) == pytest.approx(3.3 * bond_length / 20 * scale)
    assert float(root.get("LineWidth")) == pytest.approx(1.5 * bond_length / 20 * scale)
    for node, (x, y) in zip(nodes, [(0, 0), (40, 20), (80, 20)], strict=True):
        assert list(map(float, node.get("p").split())) == pytest.approx(
            [(x - plan.source_x) * scale, (y - plan.source_y) * scale]
        )
    assert root.findall(".//graphic") == []


@pytest.mark.parametrize("order", [True, 1.0, 0, 2, 3])
def test_bold_bond_refuses_non_exact_single_order_atomically(tmp_path, order):
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 40.0, 0.0)},
        bonds=[Bond(0, 1, style="bold_in")],
    )
    dest = tmp_path / "existing.cdxml"
    dest.write_bytes(b"preserve existing output")
    with offscreen_document_scene(state, command="test-cdxml") as context:
        context.model.bonds[0].order = order
        with pytest.raises(CdxmlUnsupportedObjectError, match="exact integer"):
            FigureExportService(context).export_figure(str(dest), fmt="cdxml")
    assert dest.read_bytes() == b"preserve existing output"


@pytest.mark.parametrize("style", ["bold_center"])
def test_other_bold_variants_remain_refused(style):
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, style=style)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


@pytest.mark.parametrize(
    "line_width,bold_width,expected",
    [(2.0, 5.0, 5.0), (4.0, 3.3, 4.0), (3.3, 3.3000005, 3.3)],
)
def test_bold_width_tracks_effective_qt_stroke(
    tmp_path, line_width, bold_width, expected
):
    from dataclasses import replace

    from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 50.0, 0.0)},
        bonds=[Bond(0, 1, style="bold_in")],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        context.renderer.style = replace(
            context.renderer.style,
            bond_line_width=line_width,
            bold_bond_width=bold_width,
        )
        context.bonds.redraw_bond(0)
        item = context.state.bond_graphics_state.bond_items[0][0]
        if isinstance(item, QGraphicsPolygonItem):
            drawn_width = item.polygon().boundingRect().height()
        else:
            assert isinstance(item, QGraphicsLineItem)
            drawn_width = item.pen().widthF()
        assert drawn_width == pytest.approx(expected)
        dest = tmp_path / "custom.cdxml"
        plan = FigureExportService(context).export_figure(str(dest), fmt="cdxml")
    root = ET.fromstring(dest.read_bytes())
    assert float(root.find(".//b").get("BoldWidth")) == pytest.approx(
        expected * plan.out_w_pt / plan.source_w
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_public_cli_bold_labelled_endpoints_and_source_preserved(tmp_path, reverse):
    from chemvas.bootstrap import document_render as cli

    state = _simple_state(
        atoms={0: Atom("O", 0.0, 0.0), 1: Atom("N", 70.0, 30.0)},
        bonds=[Bond(1, 0, style="bold_in") if reverse else Bond(0, 1, style="bold_in")],
    )
    source, dest = tmp_path / "bold.chemvas", tmp_path / "bold.cdxml"
    write_document(source, state, CANVAS_FILE_VERSION)
    before = source.read_bytes()
    cli._render_document(
        source, output=dest, background="white", dpi=300, width_mm=84.0
    )
    assert source.read_bytes() == before
    root = ET.fromstring(dest.read_bytes())
    nodes = {n.get("id"): n for n in root.findall(".//n")}
    bond = root.find(".//b")
    assert bond.get("Display") == "Bold"
    assert nodes[bond.get("B")].get("Element") == ("7" if reverse else "8")
    assert nodes[bond.get("E")].get("Element") == ("8" if reverse else "7")
    assert sorted(s.text for s in root.findall(".//s")) == ["N", "O"]


def test_existing_dotted_bond_exports_chemical_dash():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, style="dotted")],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = ET.fromstring(xml_bytes)
    bond = root.find(".//fragment/b")
    assert bond is not None
    assert bond.get("Order") == "1" and bond.get("Display") == "Dash"


def test_refuse_double_either_bond():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=2, style="double_either")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


def test_native_double_outer_retains_axis_and_exports_opposite_side():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=2, style="double_outer")],
    )
    raw, _ = _export_cdxml(state)
    bond = _parse_cdxml(raw).find(".//b")
    assert bond.get("DoublePosition") == "Right"
    assert float(bond.get("BondSpacing")) > 0


def test_refuse_radical():
    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"radical_electrons": 1}},
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="radical"):
        _export_cdxml(state)


def test_refuse_rounded_rect():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 0.0,
                "top": 0.0,
                "right": 20.0,
                "bottom": 20.0,
                "shape_kind": "rounded_rect",
                "stroke_style": "solid",
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="rounded_rect"):
        _export_cdxml(state)


def test_refuse_ellipse():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 0.0,
                "top": 0.0,
                "right": 20.0,
                "bottom": 20.0,
                "shape_kind": "ellipse",
                "stroke_style": "solid",
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="ellipse"):
        _export_cdxml(state)


def test_refuse_translucent_fill():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 0.0,
                "top": 0.0,
                "right": 20.0,
                "bottom": 20.0,
                "shape_kind": "rect",
                "stroke_style": "none",
                "fill": "#ff0000",
                "fill_alpha": 0.5,
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="translucent"):
        _export_cdxml(state)


def test_refuse_dashed_stroke():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 0.0,
                "top": 0.0,
                "right": 20.0,
                "bottom": 20.0,
                "shape_kind": "rect",
                "stroke_style": "dashed",
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="dashed"):
        _export_cdxml(state)


# ── Arrow / line ───────────────────────────────────────────────────────


def test_refuse_curved_arrow():
    state = _simple_state(
        arrows=[
            {
                "kind": "curved_single",
                "start": [0.0, 0.0],
                "end": [20.0, 0.0],
                "control": [10.0, -10.0],
                "double": False,
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="curved"):
        _export_cdxml(state)


def test_refuse_equilibrium():
    state = _simple_state(
        arrows=[
            {
                "kind": "equilibrium",
                "start": [0.0, 0.0],
                "end": [20.0, 0.0],
                "control": None,
                "double": False,
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


def test_line_exports_as_native_arrow():
    state = _simple_state(
        arrows=[
            {
                "kind": "line",
                "start": [5.0, 100.0],
                "end": [25.0, 100.0],
                "control": None,
                "double": False,
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    lines = root.findall(".//arrow")
    assert len(lines) == 1
    assert len(_line_endpoints(lines[0]).split()) == 4


def test_arrow_exports_as_grouped_lines():
    state = _simple_state(
        arrows=[
            {
                "kind": "arrow",
                "start": [5.0, 100.0],
                "end": [25.0, 100.0],
                "control": None,
                "double": False,
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    groups = root.findall(".//group")
    assert len(groups) >= 1
    graphics = groups[0].findall("arrow")
    assert len(graphics) == 3


# ── Shapes ─────────────────────────────────────────────────────────────


def test_filled_rect():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 25.0,
                "shape_kind": "rect",
                "stroke_style": "none",
                "fill": "#ff0000",
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    graphics = root.findall(".//graphic")
    rects = [g for g in graphics if g.get("GraphicType") == "Rectangle"]
    assert len(rects) == 1
    assert rects[0].get("RectangleType") == "Filled"
    assert rects[0].get("LineWidth") == "0"


def test_stroke_rect():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 25.0,
                "shape_kind": "rect",
                "stroke_style": "solid",
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    graphics = root.findall(".//graphic")
    rects = [g for g in graphics if g.get("GraphicType") == "Rectangle"]
    assert len(rects) == 1
    assert rects[0].get("RectangleType") == "Plain"
    lw = float(rects[0].get("LineWidth"))
    assert lw > 0


def test_filled_circle():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 30.0,
                "shape_kind": "circle",
                "stroke_style": "none",
                "fill": "#00ff00",
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    graphics = root.findall(".//graphic")
    ovals = [g for g in graphics if g.get("GraphicType") == "Oval"]
    assert len(ovals) == 1
    assert ovals[0].get("OvalType") == "Circle Filled"
    assert ovals[0].get("Center3D") is not None
    assert ovals[0].get("MajorAxisEnd3D") is not None
    assert ovals[0].get("MinorAxisEnd3D") is not None


def test_circle_axes_geometry():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 30.0,
                "shape_kind": "circle",
                "stroke_style": "none",
                "fill": "#0000ff",
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    oval = root.find(".//graphic[@GraphicType='Oval']")
    assert oval is not None

    cx, cy, *_ = [float(v) for v in oval.get("Center3D").split()]
    mx, my, *_ = [float(v) for v in oval.get("MajorAxisEnd3D").split()]
    nx, ny, *_ = [float(v) for v in oval.get("MinorAxisEnd3D").split()]

    r_major = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5
    r_minor = ((nx - cx) ** 2 + (ny - cy) ** 2) ** 0.5
    assert abs(r_major - r_minor) < 0.1


# ── Color table ────────────────────────────────────────────────────────


def test_color_table_indices():
    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0, color="#ff0000"), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)

    ct = root.find("colortable")
    assert ct is not None
    colors_in_table = ct.findall("color")
    assert len(colors_in_table) >= 2

    nodes = root.findall(".//n")
    colored = [n for n in nodes if n.get("color") is not None]
    assert len(colored) >= 1
    color_ref = int(colored[0].get("color"))
    assert color_ref >= 2


# ── Atomic write safety ───────────────────────────────────────────────


def test_no_file_on_unsupported_object(tmp_path):
    dest = tmp_path / "should_not_exist.cdxml"
    state = _simple_state(
        atoms={0: Atom("CO2Me", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        with pytest.raises(CdxmlUnsupportedObjectError):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert not dest.exists()


def test_existing_file_preserved_on_failure(tmp_path):
    dest = tmp_path / "existing.cdxml"
    original_content = b"original content"
    dest.write_bytes(original_content)
    state = _simple_state(
        atoms={0: Atom("CO2Me", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        with pytest.raises(CdxmlUnsupportedObjectError):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert dest.read_bytes() == original_content


# ── Headless CLI ───────────────────────────────────────────────────────


def test_cli_cdxml_output(tmp_path):
    from chemvas.bootstrap import document_render as cli

    source = tmp_path / "test.chemvas"
    state = _simple_state()
    write_document(source, state, CANVAS_FILE_VERSION)
    output = tmp_path / "test.cdxml"

    report = cli._render_document(
        source,
        output=output,
        background="white",
        dpi=300,
        width_mm=170.0,
    )
    assert output.exists()
    assert report["output_format"] == "cdxml"
    assert report["written"] is True

    xml_bytes = output.read_bytes()
    root = ET.fromstring(xml_bytes)
    assert root.tag == "CDXML"


def test_cli_cdxml_nonoverwrite(tmp_path):
    from chemvas.bootstrap import document_render as cli

    source = tmp_path / "test.chemvas"
    state = _simple_state()
    write_document(source, state, CANVAS_FILE_VERSION)
    output = tmp_path / "test.cdxml"
    existing_content = b"existing content must survive"
    output.write_bytes(existing_content)

    with pytest.raises(ValueError, match="already exists"):
        cli._render_document(
            source,
            output=output,
            background="white",
            dpi=300,
            width_mm=170.0,
        )
    assert output.read_bytes() == existing_content, (
        "existing file bytes must be preserved after failed overwrite"
    )


def test_cli_cdxml_min_font_rejected(tmp_path):
    from chemvas.bootstrap import document_render as cli

    source = tmp_path / "test.chemvas"
    state = _simple_state()
    write_document(source, state, CANVAS_FILE_VERSION)
    output = tmp_path / "test.cdxml"

    with pytest.raises(ValueError, match="min-font-pt"):
        cli._render_document(
            source,
            output=output,
            background="white",
            dpi=300,
            width_mm=170.0,
            min_font_pt=6.0,
        )


# ── GUI dialog format wiring ──────────────────────────────────────────


def test_gui_format_entry():
    from chemvas.features.export import (
        EXPORT_FORMATS,
        file_filter_for_format,
        suffix_for_format,
    )

    fmt_keys = {f[1] for f in EXPORT_FORMATS}
    assert "cdxml" in fmt_keys

    assert suffix_for_format("cdxml") == ".cdxml"
    assert "*.cdxml" in file_filter_for_format("cdxml")


def test_gui_canvas_export_figure_cdxml(tmp_path):
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas

    state = _simple_state()
    dest = tmp_path / "gui.cdxml"
    with offscreen_canvas(state, command="test-cdxml") as (canvas, service):
        service.export_figure(
            str(dest),
            fmt="cdxml",
            scope="sheet",
            sizing="custom",
            target_width_mm=170.0,
        )
    assert dest.exists()
    root = ET.fromstring(dest.read_bytes())
    assert root.tag == "CDXML"
    fragments = root.findall(".//fragment")
    assert len(fragments) >= 1


def test_gui_canvas_refuses_group_via_runtime_state(tmp_path):
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.ui.canvas.canvas_group_state import register_group_for

    state = _simple_state()
    dest = tmp_path / "gui_group.cdxml"
    with offscreen_canvas(state, command="test-cdxml") as (canvas, service):
        register_group_for(canvas, {0, 1}, [])
        with pytest.raises(CdxmlUnsupportedObjectError, match="group"):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert not dest.exists()


def test_normalize_path_retargets_suffix():
    from chemvas.features.export import normalize_export_path

    result = normalize_export_path("figure.svg", "cdxml")
    assert result is not None
    assert result.endswith(".cdxml")


# ── Source model unchanged ─────────────────────────────────────────────


def test_source_state_unchanged():
    import json

    state = _simple_state()
    before = json.dumps(state, sort_keys=True)
    _export_cdxml(state)
    after = json.dumps(state, sort_keys=True)
    assert before == after


# ── Well-formed XML ────────────────────────────────────────────────────


def test_valid_xml_declaration():
    state = _simple_state()
    xml_bytes, _ = _export_cdxml(state)
    assert xml_bytes.startswith(b"<?xml")
    ET.fromstring(xml_bytes)


# ── Groups: refusal through service and CLI paths ────────────────────


def test_refuse_group_with_atoms_via_service(tmp_path):
    from chemvas.domain.document.groups import SceneGroup

    state = _simple_state()
    groups = {1: SceneGroup(atom_ids={0, 1}, item_ids=[])}
    dest = tmp_path / "test.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context, groups=groups)
        with pytest.raises(CdxmlUnsupportedObjectError, match="group"):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert not dest.exists()


def test_refuse_group_with_item_ids_in_export():
    from chemvas.domain.document.groups import SceneGroup

    state = _simple_state(
        notes=[{"text": "grouped note", "x": 0.0, "y": 30.0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note_items = context.state.note_items()
        note_record_ids = []
        for ni in note_items:
            if ni is not None:
                rid = ni.data(3)
                if isinstance(rid, int):
                    note_record_ids.append(rid)
        assert len(note_record_ids) >= 1, "expected at least one note record id"
        real_id = note_record_ids[0]

        groups = {1: SceneGroup(atom_ids=set(), item_ids=[real_id])}
        service = FigureExportService(context, groups=groups)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="group"):
            preflight_cdxml(context, items, plan, groups=groups)


def test_refuse_group_via_cli(tmp_path):
    from chemvas.bootstrap import document_render as cli

    source = tmp_path / "grouped.chemvas"
    state = _simple_state(
        notes=[{"text": "grouped note", "x": 0.0, "y": 30.0}],
        groups=[{"atoms": [], "items": [["notes", 0]]}],
    )
    write_document(source, state, CANVAS_FILE_VERSION)
    output = tmp_path / "grouped.cdxml"
    with pytest.raises(CdxmlUnsupportedObjectError, match="item members"):
        cli._render_document(
            source,
            output=output,
            background="white",
            dpi=300,
            width_mm=170.0,
        )


# ── Shape stroke width at bond_length_px=40 ─────────────────────────


def test_shape_stroke_width_at_bond_length_40():
    from pytest import approx

    from chemvas.ui.annotations.shape_geometry import shape_stroke_width

    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 25.0,
                "shape_kind": "rect",
                "stroke_style": "solid",
            }
        ],
        settings_overrides={"bond_length_px": 40.0},
    )
    xml_bytes, plan = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    rects = [
        g for g in root.findall(".//graphic") if g.get("GraphicType") == "Rectangle"
    ]
    assert len(rects) == 1
    exported_lw = float(rects[0].get("LineWidth"))
    s = plan.out_w_pt / plan.source_w
    expected_lw = shape_stroke_width(1.5) * s
    assert exported_lw == approx(expected_lw, rel=1e-9), (
        f"exported stroke {exported_lw} should be "
        f"shape_stroke_width(1.5) * scale = {expected_lw}"
    )


# ── Note font properties: absolute family, size, default italic/weight ──


def test_refuse_note_default_italic():
    state = _simple_state(
        notes=[{"text": "test note", "x": 0.0, "y": 30.0}],
        settings_overrides={"text_italic": True},
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="italic"):
        _export_cdxml(state)


def test_refuse_note_weight_500():
    state = _simple_state(
        notes=[{"text": "test note", "x": 0.0, "y": 30.0}],
        settings_overrides={"text_font_weight": 500},
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="weight"):
        _export_cdxml(state)


def test_note_font_family_from_document():
    from PyQt6.QtGui import QFontInfo, QRawFont

    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        notes=[{"text": "test note", "x": 0.0, "y": 30.0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        doc_font = context.state.note_items()[0].document().defaultFont()
        resolved_family = QFontInfo(doc_font).family()
        raw = QRawFont.fromFont(doc_font)
        raw_pixel_size = raw.pixelSize()

    xml_bytes, plan = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    t_elements = root.findall(".//t")
    note_t = [t for t in t_elements if t.get("InterpretChemically") == "no"]
    note_with_text = [t for t in note_t if t.findall("s")]
    assert len(note_with_text) >= 1
    s_el = note_with_text[-1].find("s")
    assert s_el is not None
    font_id = int(s_el.get("font"))
    font_table = root.find("fonttable")
    assert font_table is not None
    fonts = font_table.findall("font")
    font_name = None
    for f in fonts:
        if int(f.get("id")) == font_id:
            font_name = f.get("name")
            break
    assert font_name == resolved_family, (
        f"font name in CDXML should be resolved '{resolved_family}', got '{font_name}'"
    )

    exported_size = float(s_el.get("size"))
    s = plan.out_w_pt / plan.source_w
    expected_size = raw_pixel_size * s
    assert exported_size == pytest.approx(expected_size, rel=0, abs=0.025), (
        f"font size {exported_size} should be raw pixel size {raw_pixel_size} "
        f"* scale {s} = {expected_size}"
    )

    assert s_el.get("face") is None, (
        "default weight 400 note should have no face attribute"
    )


# ── Atom label origin: baseline position from layout + sceneTransform ──


def test_atom_label_origin_matches_scene_layout():
    from PyQt6.QtWidgets import QGraphicsTextItem

    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0), 1: Atom("O", 40.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        atom_items = context.state.atom_graphics_state.atom_items
        label_origins: dict[int, tuple[float, float]] = {}
        for aid, item in atom_items.items():
            if not isinstance(item, QGraphicsTextItem) or not item.isVisible():
                continue
            doc = item.document()
            if doc is None:
                continue
            block = doc.begin()
            if not block.isValid():
                continue
            layout = block.layout()
            if layout is None or layout.lineCount() == 0:
                continue
            line = layout.lineAt(0)
            local_x = layout.position().x() + line.x()
            local_baseline_y = layout.position().y() + line.y() + line.ascent()
            transform = item.sceneTransform()
            scene_x = (
                transform.m11() * local_x
                + transform.m21() * local_baseline_y
                + transform.dx()
            )
            scene_y = (
                transform.m12() * local_x
                + transform.m22() * local_baseline_y
                + transform.dy()
            )
            label_origins[aid] = (scene_x, scene_y)

        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        preflight_cdxml(context, items, plan)
        xml_bytes = serialize_cdxml(context, items, plan)

    assert len(label_origins) >= 1, "expected at least one visible atom label"
    s = plan.out_w_pt / plan.source_w
    ox, oy = plan.source_x, plan.source_y

    root = _parse_cdxml(xml_bytes)
    label_ts = root.findall(".//n/t")
    assert len(label_ts) == len(label_origins), (
        f"expected {len(label_origins)} atom label <t>, got {len(label_ts)}"
    )

    actual_positions = []
    for t_el in label_ts:
        p = t_el.get("p")
        assert p is not None, "atom label <t> must have p attribute"
        parts = p.split()
        actual_positions.append((float(parts[0]), float(parts[1])))

    expected_positions = []
    for aid in sorted(label_origins):
        sx, sy = label_origins[aid]
        expected_positions.append(((sx - ox) * s, (sy - oy) * s))

    used = [False] * len(expected_positions)
    for ax, ay in actual_positions:
        best_i, best_d = -1, float("inf")
        for i, (ex, ey) in enumerate(expected_positions):
            if used[i]:
                continue
            d = (ax - ex) ** 2 + (ay - ey) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        assert best_i >= 0, f"no expected position matches actual ({ax}, {ay})"
        used[best_i] = True
        ex, ey = expected_positions[best_i]
        assert ax == pytest.approx(ex, rel=1e-9), (
            f"atom label x {ax} should match expected {ex}"
        )
        assert ay == pytest.approx(ey, rel=1e-9), (
            f"atom label y {ay} should match expected {ey}"
        )


# ── Note alignment ──────────────────────────────────────────────────


def test_refuse_note_center_alignment():
    state = _simple_state(
        notes=[{"text": "line 1\nline 2", "x": 0.0, "y": 30.0}],
        settings_overrides={"text_alignment": "center"},
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="alignment"):
        _export_cdxml(state)


# ── Note border-only box ─────────────────────────────────────────────


def test_refuse_note_border_only():
    state = _simple_state(
        notes=[{"text": "boxed", "x": 0.0, "y": 30.0}],
        settings_overrides={"note_border_enabled": True},
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="note box"):
        _export_cdxml(state)


# ── Oval BoundingBox endpoint order ──────────────────────────────────


def test_oval_bbox_axis_end_then_centre():
    state = _simple_state(
        shapes=[
            {
                "kind": "shape",
                "left": 10.0,
                "top": 10.0,
                "right": 30.0,
                "bottom": 30.0,
                "shape_kind": "circle",
                "stroke_style": "solid",
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    oval = root.find(".//graphic[@GraphicType='Oval']")
    assert oval is not None
    bbox = [float(v) for v in oval.get("BoundingBox").split()]
    cx, cy, _ = [float(v) for v in oval.get("Center3D").split()]
    mx, my, _ = [float(v) for v in oval.get("MajorAxisEnd3D").split()]
    assert abs(bbox[0] - mx) < 0.01, "BoundingBox x1 should be axis end, not centre"
    assert abs(bbox[2] - cx) < 0.01, "BoundingBox x3 should be centre"


# ── Negative-slope line BoundingBox ──────────────────────────────────


def test_negative_slope_line_preserves_endpoint_order():
    state = _simple_state(
        arrows=[
            {
                "kind": "line",
                "start": [5.0, 125.0],
                "end": [25.0, 105.0],
                "control": None,
                "double": False,
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    lines = root.findall(".//arrow")
    assert len(lines) >= 1
    bbox = [float(v) for v in _line_endpoints(lines[0]).split()]
    assert bbox[1] > bbox[3], (
        f"BoundingBox y1={bbox[1]} should be > y2={bbox[3]} for negative slope "
        "(endpoint order preserved, not min/max)"
    )


# ── Z-order: page children reflect scene ascending order ────────────
# Each page child takes one contiguous block of Z values on its own n, b, t
# and graphic elements; containers carry none.


def test_z_order_matches_scene_ascending_order():
    from PyQt6.QtCore import Qt as QtCore_Qt

    state = _simple_state(
        notes=[{"text": "z note", "x": 0.0, "y": 120.0}],
        arrows=[
            {
                "kind": "line",
                "start": [5.0, 120.0],
                "end": [25.0, 120.0],
                "control": None,
                "double": False,
            }
        ],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        scene_items_asc = list(context.scene.items(QtCore_Qt.SortOrder.AscendingOrder))
        scene_roles_ordered = []
        for item in scene_items_asc:
            role = item.data(0)
            if role in ("note", "line"):
                scene_roles_ordered.append(role)

        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        preflight_cdxml(context, items, plan)
        xml_bytes = serialize_cdxml(context, items, plan)

    assert len(scene_roles_ordered) >= 2, (
        "expected at least note + line in scene ascending order"
    )

    root = _parse_cdxml(xml_bytes)
    page = root.find("page")
    assert page is not None
    z_values = []
    cdxml_roles_ordered = []
    for child in page:
        leaves = [el for el in child.iter() if el.tag in _Z_TAGS]
        assert leaves, f"<{child.tag}> has no element that carries Z"
        for el in leaves:
            assert el.get("Z") is not None, f"<{el.tag}> missing Z attribute"
        if child.tag not in _Z_TAGS:
            assert child.get("Z") is None, f"<{child.tag}> must not carry Z"
        z_values.extend(sorted(int(el.get("Z")) for el in leaves))
        if child.tag == "t" and child.get("InterpretChemically") == "no":
            cdxml_roles_ordered.append("note")
        elif child.tag == "arrow":
            cdxml_roles_ordered.append("line")
    assert z_values == list(range(1, len(z_values) + 1)), (
        "Z values must be unique, positive and one block per page child"
    )
    assert len(z_values) >= 3, (
        "expected at least fragment + note + line as page children"
    )
    assert cdxml_roles_ordered == scene_roles_ordered, (
        f"CDXML page child order {cdxml_roles_ordered} must match "
        f"scene ascending order {scene_roles_ordered}"
    )


# ── Fragment interleaving negative regressions ─────────────────────


def test_refuse_note_over_bonded_fragment():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        notes=[{"text": "overlapping", "x": 10.0, "y": -8.0}],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="interleave"):
        _export_cdxml(state)


def test_refuse_line_over_bonded_fragment():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        arrows=[
            {
                "kind": "line",
                "start": [0.0, 0.0],
                "end": [20.0, 0.0],
                "control": None,
                "double": False,
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="interleave"):
        _export_cdxml(state)


def test_refuse_two_overlapping_bonded_fragments():
    state = _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 20.0, 0.0),
            2: Atom("N", 5.0, 0.0),
            3: Atom("S", 15.0, 0.0),
        },
        bonds=[Bond(0, 1), Bond(2, 3)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="interleave"):
        _export_cdxml(state)


# ── Arrow components: no Head3D/Tail3D ───────────────────────────────


def test_arrow_components_are_unheaded_native_line_primitives():
    state = _simple_state(
        arrows=[
            {
                "kind": "arrow",
                "start": [5.0, 100.0],
                "end": [25.0, 100.0],
                "control": None,
                "double": False,
            }
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    groups = root.findall(".//group")
    assert len(groups) >= 1
    lines = [line for group in groups for line in group.findall("arrow")]
    assert len(lines) == 3
    for line in lines:
        assert len(_line_endpoints(line).split()) == 4
        assert line.get("LineType") == "Solid"
        assert line.get("FillType") == "None"


# ── Ac/Ts alias refusal ─────────────────────────────────────────────


def test_refuse_ac_alias():
    state = _simple_state(
        atoms={0: Atom("Ac", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="alias"):
        _export_cdxml(state)


def test_refuse_ts_alias():
    state = _simple_state(
        atoms={0: Atom("Ts", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="alias"):
        _export_cdxml(state)


# ── Atom-attached drawing marks ──────────────────────────────────────


def _attached_mark_state(kind="plus", *, owner=0):
    return _simple_state(
        atoms={0: Atom("P", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"formal_charge": 1 if kind == "plus" else -1}},
        marks=[
            {"kind": kind, "atom_id": owner, "dx": 0.0, "dy": 35.0, "x": 0.0, "y": 35.0}
        ],
    )


@pytest.mark.parametrize(
    "kind,glyph,charge", [("plus", "+", "1"), ("minus", "-", "-1")]
)
def test_attached_mark_preserves_glyph_offset_and_original_charge(kind, glyph, charge):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QFontInfo

    with offscreen_document_scene(
        _attached_mark_state(kind), command="test-cdxml"
    ) as context:
        mark = next(i for i in context.scene.items() if i.data(0) == "mark")
        mark.boundingRect()
        document = mark.document()
        layout = document.begin().layout()
        line = layout.lineAt(0)
        baseline = mark.mapToScene(
            QPointF(
                layout.position().x() + line.position().x(),
                layout.position().y() + line.y() + line.ascent(),
            )
        )
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        preflight_cdxml(context, items, plan)
        root = _parse_cdxml(serialize_cdxml(context, items, plan))
        node = next(
            n for n in _top_nodes(root) if _chemical_atom(n).get("Element") == "15"
        )
        assert _chemical_atom(node).get("Charge") == charge
        tag = node.find('./objecttag[@Name="chemvasMark"]')
        assert tag is not None and tag.get("PositioningType") == "offset"
        assert tag.get("Tracking") is None
        text = tag.find("t")
        assert text is not None and text.get("InterpretChemically") == "no"
        assert "".join(text.itertext()) == glyph
        scale = plan.out_w_pt / plan.source_w
        expected = (
            (baseline.x() - plan.source_x) * scale,
            (baseline.y() - plan.source_y) * scale,
        )
        assert tuple(map(float, text.attrib["p"].split())) == pytest.approx(expected)
        node_p = tuple(map(float, node.attrib["p"].split()))
        assert tuple(
            map(float, tag.attrib["PositioningOffset"].split())
        ) == pytest.approx((expected[0] - node_p[0], expected[1] - node_p[1]))
        run = text.find("s")
        assert run is not None
        assert float(run.attrib["size"]) == pytest.approx(
            QFontInfo(mark.font()).pixelSize() * scale, rel=0, abs=0.025
        )
        assert len(_top_bonds(root)) == 1
        assert len(node.findall("./fragment/b")) == 1
        assert root.findall(".//graphic") == []


@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
@pytest.mark.parametrize(
    "case", ["standalone", "owner_not_exported", "radical", "wrong_text", "shear"]
)
def test_attached_mark_refuses_unsupported_relationship_or_paint(case, boundary):
    from PyQt6.QtGui import QTransform

    state = _attached_mark_state(
        "radical" if case == "radical" else "plus",
        owner=None if case == "standalone" else 0,
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        mark = next(i for i in context.scene.items() if i.data(0) == "mark")
        if case == "wrong_text":
            mark.setPlainText("different")
        if case == "shear":
            mark.setTransform(QTransform().shear(0.5, 0.0))
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        if case == "owner_not_exported":
            items = [mark]
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        with pytest.raises(CdxmlUnsupportedObjectError):
            operation(context, items, plan)


@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
@pytest.mark.parametrize("overlap", [False, True])
def test_attached_mark_ink_interleaving_keeps_geometry_guard(boundary, overlap):
    from PyQt6.QtCore import Qt

    with offscreen_document_scene(
        _attached_mark_state(), command="test-cdxml"
    ) as context:
        mark = next(i for i in context.scene.items() if i.data(0) == "mark")
        for item in context.state.bond_graphics_state.bond_items[0]:
            item.setZValue(0)
        mark.setZValue(1)
        for item in context.scene.items():
            if item.data(0) == "atom":
                item.setZValue(2)
        if overlap:
            mark.setPos(
                8.0, -mark.document().documentLayout().documentSize().height() / 2
            )
        order = context.scene.items(Qt.SortOrder.AscendingOrder)
        assert min(
            order.index(i) for i in context.state.bond_graphics_state.bond_items[0]
        ) < order.index(mark)
        assert order.index(mark) < min(
            order.index(i) for i in order if i.data(0) == "atom"
        )
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        if overlap:
            with pytest.raises(CdxmlUnsupportedObjectError, match="interleaves"):
                operation(context, items, plan)
        else:
            operation(context, items, plan)


@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
def test_attached_mark_overlap_above_fragment_still_refuses(boundary):
    from PyQt6.QtCore import Qt

    with offscreen_document_scene(
        _attached_mark_state(), command="test-cdxml"
    ) as context:
        mark = next(i for i in context.scene.items() if i.data(0) == "mark")
        mark.setZValue(100)
        mark.setPos(8.0, -mark.document().documentLayout().documentSize().height() / 2)
        order = context.scene.items(Qt.SortOrder.AscendingOrder)
        assert order.index(mark) > max(
            order.index(i) for i in order if i.data(0) in ("atom", "bond")
        )
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        with pytest.raises(CdxmlUnsupportedObjectError, match="child objecttag"):
            operation(context, items, plan)


def test_attached_mark_text_box_margin_does_not_count_as_ink_contact():
    from PyQt6.QtCore import Qt

    with offscreen_document_scene(
        _attached_mark_state(), command="test-cdxml"
    ) as context:
        mark = next(i for i in context.scene.items() if i.data(0) == "mark")
        mark.boundingRect()
        layout = mark.document().begin().layout()
        run = layout.lineAt(0).glyphRuns()[0]
        local_ink = run.rawFont().pathForGlyph(run.glyphIndexes()[0]).boundingRect()
        offset = layout.position() + run.positions()[0]
        mark.setPos(
            8.0 - local_ink.left() - offset.x(), 2.0 - local_ink.top() - offset.y()
        )
        mark.setZValue(1)
        for item in context.state.bond_graphics_state.bond_items[0]:
            item.setZValue(0)
            assert mark.sceneBoundingRect().intersects(item.sceneBoundingRect())
        for item in context.scene.items():
            if item.data(0) == "atom":
                item.setZValue(2)
        order = context.scene.items(Qt.SortOrder.AscendingOrder)
        assert order.index(mark) < min(
            order.index(i) for i in order if i.data(0) == "atom"
        )
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        preflight_cdxml(context, items, plan)
        assert b"chemvasMark" in serialize_cdxml(context, items, plan)


# ── Service: max_height_mm budget and overwrite+after_render ─────────


def test_service_max_height_mm_budget(tmp_path):
    from chemvas.features.export.errors import MaximumHeightError

    state = _simple_state()
    dest = tmp_path / "budget.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        with pytest.raises(MaximumHeightError):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
                max_height_mm=0.01,
            )
    assert not dest.exists()


def test_service_overwrite_with_after_render(tmp_path):
    state = _simple_state()
    dest = tmp_path / "export.cdxml"
    dest.write_bytes(b"old content")
    rendered_sizes: list[int] = []

    def after_render(tmp_path_arg):
        rendered_sizes.append(tmp_path_arg.stat().st_size)

    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        service.export_figure(
            str(dest),
            fmt="cdxml",
            scope="sheet",
            sizing="custom",
            target_width_mm=170.0,
            after_render=after_render,
        )
    assert dest.exists()
    assert dest.read_bytes() != b"old content"
    assert len(rendered_sizes) == 1
    assert rendered_sizes[0] > 0


# ── Source state unchanged: bytes, model, scene ──────────────────────


def test_source_bytes_and_model_unchanged(tmp_path):
    import json

    from chemvas.bootstrap import document_render as cli

    state = _simple_state()
    source_path = tmp_path / "source.chemvas"
    write_document(source_path, state, CANVAS_FILE_VERSION)
    before_bytes = source_path.read_bytes()
    before_json = json.dumps(state, sort_keys=True)

    output_path = tmp_path / "output.cdxml"
    cli._render_document(
        source_path,
        output=output_path,
        background="white",
        dpi=300,
        width_mm=170.0,
    )
    assert output_path.exists(), "CLI should have written the output file"

    after_bytes = source_path.read_bytes()
    after_json = json.dumps(state, sort_keys=True)

    assert before_bytes == after_bytes, ".chemvas bytes mutated during export"
    assert before_json == after_json, "state dict mutated during export"

    with offscreen_document_scene(state, command="test-cdxml") as context:
        model_before = json.dumps(serialize_model_state(context.model), sort_keys=True)
        items_before = [
            (item.data(0), item.isVisible(), item.pos().x(), item.pos().y())
            for item in context.scene.items()
        ]

        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        preflight_cdxml(context, items, plan)
        serialize_cdxml(context, items, plan)

        model_after = json.dumps(serialize_model_state(context.model), sort_keys=True)
        items_after = [
            (item.data(0), item.isVisible(), item.pos().x(), item.pos().y())
            for item in context.scene.items()
        ]

    assert model_before == model_after, "model mutated during export"
    assert items_before == items_after, "scene item positions/visibility changed"


# ── Vocabulary closure: non-vacuous with all element types ───────────


def test_vocabulary_closure_with_all_supported_types():
    state = _simple_state(
        atoms={
            0: Atom("N", 0.0, 0.0),
            1: Atom("O", 20.0, 0.0),
            2: Atom("C", 40.0, 0.0),
        },
        bonds=[Bond(0, 1), Bond(1, 2, order=2, style="double_center")],
        notes=[{"text": "mixed content", "x": 0.0, "y": 30.0}],
        arrows=[
            {
                "kind": "line",
                "start": [5.0, 50.0],
                "end": [25.0, 50.0],
                "control": None,
                "double": False,
            },
            {
                "kind": "arrow",
                "start": [5.0, 60.0],
                "end": [25.0, 60.0],
                "control": None,
                "double": False,
            },
        ],
        shapes=[
            {
                "kind": "shape",
                "left": 50.0,
                "top": 10.0,
                "right": 70.0,
                "bottom": 30.0,
                "shape_kind": "rect",
                "stroke_style": "solid",
            },
            {
                "kind": "shape",
                "left": 80.0,
                "top": 10.0,
                "right": 100.0,
                "bottom": 30.0,
                "shape_kind": "circle",
                "stroke_style": "none",
                "fill": "#0000ff",
            },
        ],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)

    found_tags = {el.tag for el in root.iter()}
    assert "fragment" in found_tags, "expected fragment element"
    assert "n" in found_tags, "expected node element"
    assert "b" in found_tags, "expected bond element"
    assert "t" in found_tags, "expected text element"
    assert "s" in found_tags, "expected styled run element"
    assert "graphic" in found_tags, "expected graphic element"
    assert "group" in found_tags, "expected group element for arrow"
    assert "fonttable" in found_tags, "expected fonttable"
    assert "colortable" in found_tags, "expected colortable"

    for el in root.iter():
        tag = el.tag
        assert tag in _ALLOWED_ELEMENTS, f"unexpected element: {tag}"
        allowed = _ALLOWED_ATTRS_BY_ELEMENT.get(tag, set())
        for attr in el.attrib:
            assert attr in allowed, f"unexpected attribute {attr} on <{tag}>"

    root_el = root
    assert root_el.get("FractionalWidths") == "yes"

    fragments = root.findall(".//fragment")
    assert len(fragments) >= 1
    nodes = root.findall(".//n")
    assert any(n.get("Element") == "7" for n in nodes), "expected nitrogen"
    assert any(n.get("Element") == "8" for n in nodes), "expected oxygen"
    bonds = root.findall(".//b")
    assert any(b.get("Order") == "2" for b in bonds), "expected double bond"


# ── FractionalWidths attribute ───────────────────────────────────────


def test_fractional_widths_present():
    state = _simple_state()
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    assert root.get("FractionalWidths") == "yes"


# ── ET.indent whitespace: no whitespace inside text runs ─────────────


def test_no_whitespace_inside_text_runs():
    state = _simple_state(
        notes=[{"text": " hello world ", "x": 0.0, "y": 30.0}],
    )
    xml_bytes, _ = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    page = root.find("page")
    assert page is not None
    note_ts = [t for t in page.findall("t") if t.get("InterpretChemically") == "no"]
    assert len(note_ts) >= 1, "expected at least one note <t> on page"
    found_text = False
    for t in note_ts:
        assert t.text is None, f"<t> text content should be None, got: {t.text!r}"
        s_elements = t.findall("s")
        texts = []
        for s in s_elements:
            assert s.tail is None, f"<s> tail should be None, got: {s.tail!r}"
            if s.text is not None:
                found_text = True
                assert not s.text.startswith("\n"), (
                    f"s text starts with newline (indent leak): {s.text!r}"
                )
                texts.append(s.text)
        full = "".join(texts)
        assert full == " hello world ", (
            f"concatenated note text must equal exact source, got: {full!r}"
        )
    assert found_text, "expected at least one <s> with text content"


# ── Note rotation ────────────────────────────────────────────────────


@pytest.mark.parametrize("angle", [-90.0, 45.0, 180.0])
def test_rotated_note_preserves_baseline_font_and_text(angle):
    from PyQt6.QtGui import QFontInfo, QTransform

    state = _simple_state(notes=[{"text": "rotated", "x": 1000.0, "y": 1000.0}])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item = context.state.note_items()[0]
        transform = QTransform().rotate(angle).scale(1.5, 1.5)
        item.setTransform(transform)
        item.boundingRect()
        document = item.document()
        layout = document.begin().layout()
        line = layout.lineAt(0)
        from PyQt6.QtCore import QPointF

        baseline = item.mapToScene(
            QPointF(
                layout.position().x() + line.position().x(),
                layout.position().y() + line.y() + line.ascent(),
            )
        )
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        preflight_cdxml(context, items, plan)
        root = _parse_cdxml(serialize_cdxml(context, items, plan))
        note = next(
            t for t in root.findall(".//page/t") if "".join(t.itertext()) == "rotated"
        )
        assert int(note.attrib["RotationAngle"]) == round(angle * 65536)
        expected = (
            (baseline.x() - plan.source_x) * (plan.out_w_pt / plan.source_w),
            (baseline.y() - plan.source_y) * (plan.out_w_pt / plan.source_w),
        )
        assert tuple(map(float, note.attrib["p"].split())) == pytest.approx(expected)
        run = note.find("s")
        assert run is not None
        assert float(run.attrib["size"]) == pytest.approx(
            QFontInfo(
                document.begin()
                .begin()
                .fragment()
                .charFormat()
                .font()
                .resolve(document.defaultFont())
            ).pixelSize()
            * 1.5
            * (plan.out_w_pt / plan.source_w),
            rel=0,
            abs=0.025,
        )
        assert note.attrib["InterpretChemically"] == "no"


@pytest.mark.parametrize(
    "transform_values",
    [
        (1.0, 0.0, 0.5, 1.0, 0.0, 0.0),
        (2.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        (1.0, 0.0, 0.01, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    ],
)
@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
def test_note_refuses_lossy_transform(transform_values, boundary):
    from PyQt6.QtGui import QTransform

    state = _simple_state(notes=[{"text": "guarded", "x": 0.0, "y": 30.0}])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        context.state.note_items()[0].setTransform(QTransform(*transform_values))
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        with pytest.raises(CdxmlUnsupportedObjectError, match="transform"):
            operation(context, items, plan)


# ── Bond-only selection refusal ──────────────────────────────────────


def test_refuse_bond_only_selection():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        bond_items = [item for item in context.scene.items() if item.data(0) == "bond"]
        assert len(bond_items) >= 1, "expected at least one bond item"
        service = FigureExportService(context)
        plan = service.plan_figure_export(
            scope="sheet",
            sizing="custom",
            target_width_mm=170.0,
        )
        with pytest.raises(CdxmlUnsupportedObjectError):
            preflight_cdxml(context, bond_items, plan)


# ── Mismatched bond style/order refusal ─────────────────────────────


def test_refuse_mismatched_bond_style_order():
    # Drawn as one line, but its style claims a triple bond.
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=1, style="triple")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="requires order"):
        _export_cdxml(state)


# ── Unrelated group does not block export ────────────────────────────


def test_unrelated_group_does_not_block_export():
    from chemvas.domain.document.groups import SceneGroup

    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        notes=[{"text": "excluded note", "x": 200.0, "y": 200.0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note_items = context.state.note_items()
        assert len(note_items) >= 1
        note_record_id = note_items[0].data(3)
        assert isinstance(note_record_id, int)

        groups = {1: SceneGroup(atom_ids=set(), item_ids=[note_record_id])}

        atom_items = [item for item in context.scene.items() if item.data(0) == "atom"]
        bond_items = [item for item in context.scene.items() if item.data(0) == "bond"]
        selection_items = atom_items + bond_items

        service = FigureExportService(context, groups=groups)
        items, plan = service._resolve_figure_export(
            scope="selection",
            selection=selection_items,
            sizing="custom",
            target_width_mm=170.0,
        )
        preflight_cdxml(context, items, plan, groups=groups)
        xml_bytes = serialize_cdxml(context, items, plan, groups=groups)

    root = _parse_cdxml(xml_bytes)
    assert root.tag == "CDXML"
    fragments = root.findall(".//fragment")
    assert len(fragments) >= 1


# ── Fallback glyph refusal ──────────────────────────────────────────


def test_refuse_fallback_glyph_note():
    from PyQt6.QtGui import QFontInfo, QTextLayout

    emoji = "\U0001f600"
    state = _simple_state(
        notes=[{"text": emoji, "x": 0.0, "y": 30.0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note_item = context.state.note_items()[0]
        doc_font = note_item.document().defaultFont()
        primary_family = QFontInfo(doc_font).family()

        layout = QTextLayout(emoji, doc_font)
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid():
            line.setLineWidth(1e6)
        layout.endLayout()

        has_fallback = False
        has_glyph_zero = False
        for run in layout.glyphRuns():
            raw = run.rawFont()
            run_family = raw.familyName()
            if run_family and run_family != primary_family:
                has_fallback = True
            for glyph_index in run.glyphIndexes():
                if glyph_index == 0:
                    has_glyph_zero = True

    assert has_fallback or has_glyph_zero, (
        f"emoji '{emoji}' should trigger either glyph fallback or glyph index 0 "
        f"under font '{primary_family}'; if neither occurs, the test premise "
        "is invalid on this platform"
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="fallback|glyph"):
        _export_cdxml(state)


def test_refuse_glyph_zero_in_note():
    from PyQt6.QtGui import QFontInfo, QTextLayout

    test_char = "\U0001f600"
    state = _simple_state(
        notes=[{"text": test_char, "x": 0.0, "y": 30.0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note_item = context.state.note_items()[0]
        doc_font = note_item.document().defaultFont()

        layout = QTextLayout(test_char, doc_font)
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid():
            line.setLineWidth(1e6)
        layout.endLayout()

        has_glyph_zero = False
        for run in layout.glyphRuns():
            for glyph_index in run.glyphIndexes():
                if glyph_index == 0:
                    has_glyph_zero = True

    if not has_glyph_zero:
        pytest.skip(
            f"font '{QFontInfo(doc_font).family()}' renders the test character "
            "without glyph index 0; cannot test .notdef refusal on this platform"
        )
    with pytest.raises(CdxmlUnsupportedObjectError, match="glyph"):
        _export_cdxml(state)


# ── Arrow mirrored refusal ──────────────────────────────────────────


def test_refuse_mirrored_arrow():
    state = _simple_state(
        arrows=[
            {
                "kind": "equilibrium",
                "start": [5.0, 100.0],
                "end": [25.0, 100.0],
                "control": None,
                "double": False,
                "mirrored": True,
            }
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


# ── Live note unsupported style refusal ────────────────────────────


@pytest.mark.parametrize(
    "style_id",
    [
        "capitalization_uppercase",
        "capitalization_smallcaps",
        "word_spacing",
        "font_stretch",
        "underline_dash",
    ],
)
def test_refuse_unsupported_live_note_style(tmp_path, style_id):
    from PyQt6.QtGui import QFont, QTextCharFormat, QTextCursor

    fmt = QTextCharFormat()
    if style_id == "capitalization_uppercase":
        fmt.setFontCapitalization(QFont.Capitalization.AllUppercase)
    elif style_id == "capitalization_smallcaps":
        fmt.setFontCapitalization(QFont.Capitalization.SmallCaps)
    elif style_id == "word_spacing":
        fmt.setFontWordSpacing(5.0)
    elif style_id == "font_stretch":
        fmt.setFontStretch(150)
    elif style_id == "underline_dash":
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)

    state = _simple_state(
        notes=[{"text": "styled note", "x": 0.0, "y": 30.0}],
    )
    dest = tmp_path / f"styled_{style_id}.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note_item = context.state.note_items()[0]
        doc = note_item.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeCharFormat(fmt)

        expected_match = {
            "capitalization_uppercase": "capitalization",
            "capitalization_smallcaps": "capitalization",
            "word_spacing": "word spacing",
            "font_stretch": "stretch",
            "underline_dash": "underline style",
        }[style_id]

        service = FigureExportService(context)
        with pytest.raises(CdxmlUnsupportedObjectError, match=expected_match):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert not dest.exists(), (
        f"no file should be written for unsupported style {style_id}"
    )


# ── Ring, stereo and charged structures (original synthetic fixtures) ──


def _ring_tool_benzene(first_id=0, cx=0.0, cy=0.0, *, reverse=False):
    """Atoms, bonds and ring record shaped like the benzene ring tool's output.

    The tool adds its order-2 bonds without a style, so they keep "single",
    and records the ring with the transparent default fill. Atom ids run
    clockwise on the page because scene y grows downward.
    """
    atoms = {
        first_id + index: Atom(
            "C",
            cx + 20.0 * math.cos(math.radians(90.0 + 60.0 * index)),
            cy + 20.0 * math.sin(math.radians(90.0 + 60.0 * index)),
        )
        for index in range(6)
    }
    bonds = []
    for index in range(6):
        a, b = first_id + index, first_id + (index + 1) % 6
        if reverse:
            a, b = b, a
        bonds.append(Bond(a, b, order=2 if index % 2 == 0 else 1))
    ring = {
        "points": [[atom.x, atom.y] for atom in atoms.values()],
        "atom_ids": list(atoms),
        "color": "#f4d06f",
        "alpha": 0.0,
    }
    return atoms, bonds, ring


def _benzene_state(*, ring_color="#f4d06f", ring_alpha=0.0, reverse=False):
    atoms, bonds, ring = _ring_tool_benzene(reverse=reverse)
    ring.update(color=ring_color, alpha=ring_alpha)
    return _simple_state(atoms=atoms, bonds=bonds, ring_fills=[ring])


def _butan_2_ol(style, first_id=0, dx=0.0, dy=0.0):
    """Butan-2-ol with a wedge or hash from the stereocentre to oxygen.

    On the page O is above the stereocentre, the methyl lower left and the
    ethyl lower right, so O -> ethyl -> methyl runs clockwise. A wedge brings
    O toward the viewer and leaves H behind: (R). A hash does the reverse: (S).
    """
    first = first_id
    atoms = {
        first: Atom("C", dx, dy),
        first + 1: Atom("C", dx - 17.32, dy + 10.0),
        first + 2: Atom("C", dx + 17.32, dy + 10.0),
        first + 3: Atom("C", dx + 34.64, dy),
        first + 4: Atom("O", dx, dy - 20.0),
    }
    bonds = [
        Bond(first, first + 4, style=style),
        Bond(first, first + 1),
        Bond(first, first + 2),
        Bond(first + 2, first + 3),
    ]
    return atoms, bonds


def _nitromethane_state():
    return _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("N", 20.0, 0.0),
            2: Atom("O", 30.0, -17.32),
            3: Atom("O", 30.0, 17.32),
        },
        bonds=[Bond(0, 1), Bond(1, 2, order=2, style="double"), Bond(1, 3)],
        atom_annotations={1: {"formal_charge": 1}, 3: {"formal_charge": -1}},
    )


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


def _resolved_export(context):
    service = FigureExportService(context)
    return service._resolve_figure_export(
        scope="sheet",
        selection=None,
        sizing="custom",
        target_width_mm=170.0,
    )


@pytest.mark.parametrize("ring_color", ["#f4d06f", None])
@pytest.mark.parametrize(
    ("reverse", "expected_side"), [(False, "Left"), (True, "Right")]
)
def test_ring_tool_benzene_exports_inner_double_bonds(
    ring_color, reverse, expected_side
):
    xml_bytes, _ = _export_cdxml(_benzene_state(ring_color=ring_color, reverse=reverse))
    root = _parse_cdxml(xml_bytes)
    page = root.find("page")
    assert [child.tag for child in page] == ["fragment"], (
        "the transparent ring record must not emit any graphic"
    )
    points = {
        node.get("id"): tuple(float(value) for value in node.get("p").split())
        for node in root.iter("n")
    }
    assert len(points) == 6
    assert all(node.get("Element") is None for node in root.iter("n"))
    cx = sum(x for x, _ in points.values()) / 6
    cy = sum(y for _, y in points.values()) / 6
    bonds = root.findall(".//b")
    assert len(bonds) == 6
    doubles = [bond for bond in bonds if bond.get("Order") == "2"]
    assert len(doubles) == 3
    for bond in bonds:
        assert bond.get("Display") is None
        if bond.get("Order") is None:
            assert bond.get("DoublePosition") is None
    for bond in doubles:
        bx, by = points[bond.get("B")]
        ex, ey = points[bond.get("E")]
        # The saved native witness puts CDXML Left on page normal (-dy, dx).
        inward = -(ey - by) * (cx - (bx + ex) / 2) + (ex - bx) * (cy - (by + ey) / 2)
        assert bond.get("DoublePosition") == ("Left" if inward > 0 else "Right")
        assert bond.get("DoublePosition") == expected_side


@pytest.mark.parametrize(
    ("substituent_y", "expected_side"), [(17.32, "Left"), (-17.32, "Right")]
)
def test_chain_double_bond_side_follows_its_substituent(substituent_y, expected_side):
    state = _simple_state(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 20.0, 0.0),
            2: Atom("C", 30.0, substituent_y),
        },
        bonds=[Bond(0, 1, order=2, style="double"), Bond(1, 2)],
    )
    xml_bytes, plan = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    nodes = _node_ids_by_atom(root, plan, {0: Atom("C", 0.0, 0.0)})
    (double,) = [bond for bond in root.iter("b") if bond.get("Order") == "2"]
    assert double.get("B") == nodes[0]
    assert double.get("DoublePosition") == expected_side


def test_refuse_double_bond_whose_drawn_lines_have_no_side():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=2, style="double")],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        first, second = context.state.bond_graphics_state.bond_items[0]
        second.setLine(first.line())
        items, plan = _resolved_export(context)
        with pytest.raises(CdxmlUnsupportedObjectError, match="side line"):
            preflight_cdxml(context, items, plan)


@pytest.mark.parametrize(
    ("style", "display"), [("wedge", "WedgeBegin"), ("hash", "WedgedHashBegin")]
)
@pytest.mark.parametrize("narrow_atom", [0, 1])
def test_stereo_bond_begins_at_its_narrow_end(style, display, narrow_atom):
    atoms = {0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)}
    wide_atom = 1 - narrow_atom
    state = _simple_state(
        atoms=atoms, bonds=[Bond(narrow_atom, wide_atom, style=style)]
    )
    xml_bytes, plan = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    nodes = _node_ids_by_atom(root, plan, atoms)
    bonds = root.findall(".//b")
    assert len(bonds) == 1
    assert bonds[0].get("Display") == display
    assert bonds[0].get("B") == nodes[narrow_atom]
    assert bonds[0].get("E") == nodes[wide_atom]
    assert bonds[0].get("Order") is None
    assert bonds[0].get("DoublePosition") is None


def test_refuse_wedge_whose_drawn_narrow_end_disagrees():
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF

    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, style="wedge")],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        (wedge,) = context.state.bond_graphics_state.bond_items[0]
        wedge.setPolygon(
            QPolygonF([QPointF(20.0, 0.0), QPointF(2.0, -1.5), QPointF(2.0, 1.5)])
        )
        items, plan = _resolved_export(context)
        with pytest.raises(CdxmlUnsupportedObjectError, match="narrow"):
            preflight_cdxml(context, items, plan)


def test_charged_heteroatoms_keep_element_and_charge():
    state = _nitromethane_state()
    xml_bytes, plan = _export_cdxml(state)
    root = _parse_cdxml(xml_bytes)
    atoms = deserialize_model_state(state["model"]).atoms
    nodes = _node_ids_by_atom(root, plan, atoms)
    by_id = {node.get("id"): node for node in root.iter("n")}
    assert by_id[nodes[0]].get("Element") is None
    assert _chemical_atom(by_id[nodes[1]]).get("Element") == "7"
    assert _chemical_atom(by_id[nodes[1]]).get("Charge") == "1"
    assert by_id[nodes[2]].get("Element") == "8"
    assert by_id[nodes[2]].get("Charge") is None
    assert _chemical_atom(by_id[nodes[3]]).get("Element") == "8"
    assert _chemical_atom(by_id[nodes[3]]).get("Charge") == "-1"
    (double,) = [bond for bond in _top_bonds(root) if bond.get("Order") == "2"]
    assert {double.get("B"), double.get("E")} == {nodes[1], nodes[2]}
    assert double.get("DoublePosition") in {"Right", "Left"}


@pytest.mark.parametrize("ring_color", ["#f4d06f", "#ff0000"])
def test_refuse_visible_ring_fill_and_keep_destination(tmp_path, ring_color):
    dest = tmp_path / "ring.cdxml"
    dest.write_bytes(b"previous export")
    state = _benzene_state(ring_color=ring_color, ring_alpha=0.35)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        with pytest.raises(CdxmlUnsupportedObjectError, match="ring fill"):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert dest.read_bytes() == b"previous export"


def test_cli_export_preserves_ring_and_stereo_and_leaves_source_unchanged(tmp_path):
    from chemvas.bootstrap import document_render as cli

    ring_atoms, ring_bonds, ring = _ring_tool_benzene()
    stereo_atoms, stereo_bonds = _butan_2_ol("wedge", first_id=6, dx=100.0)
    state = _simple_state(
        atoms={**ring_atoms, **stereo_atoms},
        bonds=ring_bonds + stereo_bonds,
        ring_fills=[ring],
    )
    source = tmp_path / "ring_and_stereo.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    before = source.read_bytes()
    output = tmp_path / "ring_and_stereo.cdxml"

    report = cli._render_document(
        source,
        output=output,
        background="white",
        dpi=300,
        width_mm=170.0,
    )

    assert report["written"] is True
    assert source.read_bytes() == before
    root = ET.fromstring(output.read_bytes())
    assert len(root.findall(".//fragment")) == 2
    nodes = {node.get("id"): node for node in root.iter("n")}
    assert len(nodes) == 11
    bonds = root.findall(".//b")
    assert len(bonds) == 10
    assert sum(bond.get("Order") == "2" for bond in bonds) == 3
    (wedge,) = [bond for bond in bonds if bond.get("Display") is not None]
    assert wedge.get("Display") == "WedgeBegin"
    # Narrow at the carbon stereocentre, wide at oxygen.
    assert nodes[wedge.get("B")].get("Element") is None
    assert nodes[wedge.get("E")].get("Element") == "8"
    # Every drawn bond is one bond length long; the export keeps one scale.
    bond_length = float(root.get("BondLength"))
    for bond in bonds:
        bx, by = (float(v) for v in nodes[bond.get("B")].get("p").split())
        ex, ey = (float(v) for v in nodes[bond.get("E")].get("p").split())
        assert math.hypot(ex - bx, ey - by) == pytest.approx(bond_length, rel=1e-3)


# Direct XML and native MOL semantics; external editor rendering is not covered.


def test_cdxml_ring_graph_preserves_alternating_bonds():
    xml_bytes, _ = _export_cdxml(_benzene_state())
    root = ET.fromstring(xml_bytes)
    fragments = root.findall(".//fragment")
    assert len(fragments) == 1
    nodes = {node.get("id"): node for node in fragments[0].findall("n")}
    bonds = fragments[0].findall("b")
    assert len(nodes) == len(bonds) == 6
    assert all(node.get("Element", "6") == "6" for node in nodes.values())
    assert sorted(b.get("Order", "1") for b in bonds) == ["1", "1", "1", "2", "2", "2"]
    neighbors = {key: set() for key in nodes}
    for bond in bonds:
        first, second = bond.get("B"), bond.get("E")
        assert first != second and first in nodes and second in nodes
        neighbors[first].add(second)
        neighbors[second].add(first)
    assert all(len(items) == 2 for items in neighbors.values())
    reached, pending = set(), [next(iter(nodes))]
    while pending:
        atom = pending.pop()
        if atom not in reached:
            reached.add(atom)
            pending.extend(neighbors[atom] - reached)
    assert reached == set(nodes)


@pytest.mark.parametrize(
    ("style", "display", "stereo"),
    [("wedge", "WedgeBegin", 1), ("hash", "WedgedHashBegin", 6)],
)
def test_cdxml_and_mol_preserve_drawn_stereo_direction(style, display, stereo):
    from chemvas.core.molfile import write_molfile

    atoms, bonds = _butan_2_ol(style)
    state = _simple_state(atoms=atoms, bonds=bonds)
    xml_bytes, _ = _export_cdxml(state)
    root = ET.fromstring(xml_bytes)
    nodes = {n.get("id"): n for n in root.findall(".//fragment/n")}
    (directional,) = [b for b in root.findall(".//fragment/b") if b.get("Display")]
    assert directional.get("Display") == display
    assert nodes[directional.get("B")].get("Element", "6") == "6"
    assert nodes[directional.get("E")].get("Element") == "8"
    model = deserialize_model_state(state["model"])
    rows = write_molfile(model).splitlines()[
        4 + len(model.atoms) : 4 + len(model.atoms) + len(model.bonds)
    ]
    (row,) = [r for r in rows if int(r[9:12])]
    assert int(row[9:12]) == stereo
    assert model.atoms[int(row[:3]) - 1].element == "C"
    assert model.atoms[int(row[3:6]) - 1].element == "O"


def test_cdxml_preserves_nitromethane_elements_charges_and_connectivity():
    xml_bytes, _ = _export_cdxml(_nitromethane_state())
    root = ET.fromstring(xml_bytes)
    nodes = {n.get("id"): _chemical_atom(n) for n in _top_nodes(root)}
    assert sorted(
        (n.get("Element", "6"), int(n.get("Charge", "0"))) for n in nodes.values()
    ) == [("6", 0), ("7", 1), ("8", -1), ("8", 0)]
    nitrogen = next(key for key, n in nodes.items() if n.get("Element") == "7")
    edges = []
    for bond in _top_bonds(root):
        first, second = bond.get("B"), bond.get("E")
        assert nitrogen in (first, second)
        other = nodes[second if first == nitrogen else first]
        edges.append(
            (
                other.get("Element", "6"),
                int(other.get("Charge", "0")),
                bond.get("Order", "1"),
            )
        )
    assert sorted(edges) == [("6", 0, "1"), ("8", -1, "1"), ("8", 0, "2")]


# ── Typed atom label semantics (synthetic O-LABEL fixtures) ─────────────
#
# Serializer-shape fixtures only: an O bonded to one drawn label. They do not
# claim a chemically meaningful or stable molecule, and XML checks here are
# not ChemDraw (or any consumer) visual or roundtrip evidence.

_H_A = "H\u1d43"
_H_B = "H\u1d47"

# Attributes the typed-label path adds; nothing else is admitted.
_LABEL_NODE_ATTRS = {"NodeType", "NumHydrogens", "GenericNickname", "BondOrdering"}
_LABEL_NODE_TYPES = {
    "Nickname",
    "Fragment",
    "GenericNickname",
    "ExternalConnectionPoint",
}

# Independent expectations (not read from the exporter): carbons, hydrogens.
_GROUP_FORMULAS = {"Me": (1, 3), "Ph": (6, 5), "tBu": (4, 9)}


def _label_state(label, *, bonds=None, annotations=None, extra_atoms=None):
    atoms = {
        0: Atom("O", 0.0, 0.0, explicit_label=True),
        1: Atom(label, 25.0, 0.0, explicit_label=True),
    }
    atoms.update(extra_atoms or {})
    return _simple_state(
        atoms=atoms,
        bonds=[Bond(0, 1)] if bonds is None else bonds,
        atom_annotations=annotations,
    )


def _export_bound(state, label_bindings):
    with offscreen_document_scene(state, command="test-cdxml") as context:
        items, plan = _resolved_export(context)
        preflight_cdxml(context, items, plan, label_bindings=label_bindings)
        xml_bytes = serialize_cdxml(context, items, plan, label_bindings=label_bindings)
        return xml_bytes, plan


def _page_fragments(root):
    return root.find("page").findall("fragment")


def _top_nodes(root):
    return [n for frag in _page_fragments(root) for n in frag.findall("n")]


def _chemical_atom(node):
    if node.get("NodeType") == "Fragment":
        (atom,) = [
            n
            for n in node.findall("./fragment/n")
            if n.get("NodeType") != "ExternalConnectionPoint"
        ]
        return atom
    return node


def _top_bonds(root):
    return [b for frag in _page_fragments(root) for b in frag.findall("b")]


def _label_text(node):
    (t,) = node.findall("t")
    return "".join(s.text or "" for s in t.findall("s"))


def _label_style(node):
    (t,) = node.findall("t")
    (s,) = t.findall("s")
    return {key: s.get(key) for key in ("font", "size", "color", "face")}


def _point(node):
    return tuple(float(value) for value in node.get("p").split())


def _expected_point(plan, atom):
    s = plan.out_w_pt / plan.source_w
    return ((atom.x - plan.source_x) * s, (atom.y - plan.source_y) * s)


def _assert_label_vocabulary_and_ids(root):
    ids = [el.get("id") for el in root.iter() if el.get("id") is not None]
    assert len(ids) == len(set(ids)), f"duplicate IDs: {ids}"
    for el in root.iter():
        assert el.tag in _ALLOWED_ELEMENTS, f"unexpected element: {el.tag}"
        allowed = set(_ALLOWED_ATTRS_BY_ELEMENT.get(el.tag, set()))
        if el.tag == "n":
            allowed |= _LABEL_NODE_ATTRS
        elif el.tag == "fragment":
            allowed.add("ConnectionOrder")
        for attr in el.attrib:
            assert attr in allowed, f"unexpected attribute {attr} on <{el.tag}>"
        if el.tag == "n" and el.get("NodeType") is not None:
            assert el.get("NodeType") in _LABEL_NODE_TYPES
    # IDREF closure: every bond joins two distinct nodes of its own fragment.
    for frag in root.iter("fragment"):
        node_ids = {n.get("id") for n in frag.findall("n")}
        for bond in frag.findall("b"):
            assert bond.get("B") in node_ids and bond.get("E") in node_ids
            assert bond.get("B") != bond.get("E")


def _nickname_parts(root):
    nodes = _top_nodes(root)
    (oxygen,) = [n for n in nodes if n.get("Element") == "8"]
    (group,) = [n for n in nodes if n.get("NodeType") is not None]
    return oxygen, group


# 1. Explicit hydrogen identity: exact label, Element 1, nothing else implied.


def test_hydrogen_identifier_without_binding_is_blocked():
    with pytest.raises(CdxmlUnsupportedObjectError, match="no typed element-identity"):
        _export_cdxml(_label_state(_H_A))


@pytest.mark.parametrize("charge", [0, 1])
def test_bound_hydrogen_identifiers_keep_exact_label_and_element_one(charge):
    def state(first, second):
        return _simple_state(
            atoms={
                0: Atom("O", 0.0, 0.0, explicit_label=True),
                1: Atom(first, 25.0, 0.0, explicit_label=True),
                2: Atom(second, -12.5, 21.65, explicit_label=True),
            },
            bonds=[Bond(0, 1), Bond(0, 2)],
            atom_annotations={1: {"formal_charge": charge}} if charge else None,
        )

    hydrogen = CdxmlLabelBinding.element_identity("H")
    bound_state = state(_H_A, _H_B)
    xml_bytes, plan = _export_bound(bound_state, {1: hydrogen, 2: hydrogen})
    control_bytes, _ = _export_cdxml(state("H", "H"))
    root, control = ET.fromstring(xml_bytes), ET.fromstring(control_bytes)
    _assert_label_vocabulary_and_ids(root)

    labelled = {_label_text(n): n for n in _top_nodes(root) if n.find("t") is not None}
    assert [ord(c) for c in _label_text(labelled[_H_A])] == [0x48, 0x1D43]
    assert [ord(c) for c in _label_text(labelled[_H_B])] == [0x48, 0x1D47]
    control_h = [
        n for n in _top_nodes(control) if _chemical_atom(n).get("Element") == "1"
    ]
    assert len(control_h) == 2
    atoms = deserialize_model_state(bound_state["model"]).atoms
    for atom_id, label in ((1, _H_A), (2, _H_B)):
        node = labelled[label]
        chemical = _chemical_atom(node)
        assert chemical.get("Element") == "1"
        assert chemical.get("NodeType") is None
        assert "Isotope" not in chemical.attrib
        expected_charge = str(charge) if (charge and atom_id == 1) else None
        assert chemical.get("Charge") == expected_charge
        assert _point(node) == pytest.approx(_expected_point(plan, atoms[atom_id]))
        assert _label_style(node) == _label_style(labelled["O"])
    assert len(_top_bonds(root)) == 2


@pytest.mark.parametrize("label", ["H\u00b2", "H\u207a", "Hx", _H_A + "\u00b2", "D"])
def test_bound_hydrogen_identifier_rejects_non_identifier_suffixes(label):
    state = _label_state(label)
    with pytest.raises(CdxmlUnsupportedObjectError, match="does not match bound"):
        _export_bound(state, {1: CdxmlLabelBinding.element_identity("H")})


# 2. Verified group labels: native nickname with the full internal graph.


@pytest.mark.parametrize("label", ["Me", "Ph", "tBu"])
def test_nickname_node_z_block_keeps_its_contents_together(label):
    xml_bytes, _plan = _export_cdxml(_label_state(label))
    root = ET.fromstring(xml_bytes)
    _assert_label_vocabulary_and_ids(root)
    oxygen, group = _nickname_parts(root)
    for node in (oxygen, group):
        leaves = [el for el in node.iter() if el.tag in _Z_TAGS]
        z = [int(el.get("Z")) for el in leaves]
        # The node, its contracted atoms and bonds, then its label.
        assert z == list(range(z[0], z[0] + len(z)))
        assert leaves[-1].tag == "t"
    assert all(el.get("Z") is None for el in group.iter("fragment"))


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("label", ["Me", "Ph", "tBu"])
def test_verified_group_label_exports_nickname_fragment(label, reverse):
    state = _label_state(label, bonds=[Bond(1, 0) if reverse else Bond(0, 1)])
    xml_bytes, plan = _export_cdxml(state)
    root = ET.fromstring(xml_bytes)
    _assert_label_vocabulary_and_ids(root)

    assert len(_page_fragments(root)) == 1
    assert len(_top_nodes(root)) == 2
    (outer,) = _top_bonds(root)
    oxygen, group = _nickname_parts(root)
    assert group.get("NodeType") == "Nickname"
    for attr in ("Element", "Charge", "NumHydrogens", "GenericNickname"):
        assert attr not in group.attrib
    assert _label_text(group) == label
    assert _label_style(group) == _label_style(oxygen)
    first, second = (group, oxygen) if reverse else (oxygen, group)
    assert (outer.get("B"), outer.get("E")) == (first.get("id"), second.get("id"))
    assert outer.get("Order") is None and outer.get("Display") is None
    atoms = deserialize_model_state(state["model"]).atoms
    assert _point(group) == pytest.approx(_expected_point(plan, atoms[1]))
    assert _point(oxygen) == pytest.approx(_expected_point(plan, atoms[0]))

    (inner,) = group.findall("fragment")
    inner_nodes = inner.findall("n")
    (connection,) = [n for n in inner_nodes if n.get("NodeType") is not None]
    assert connection.get("NodeType") == "ExternalConnectionPoint"
    assert _point(connection) == pytest.approx(_point(oxygen))
    carbons = [n for n in inner_nodes if n.get("NodeType") is None]
    assert all(n.get("Element") is None for n in carbons)
    expected_carbons, expected_hydrogens = _GROUP_FORMULAS[label]
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
    (ipso,) = [n for n in carbons if n.get("id") == attachment.get("B")]
    assert _point(ipso) == pytest.approx(_point(group))
    by_id = {n.get("id"): n for n in inner_nodes}
    outer_length = math.dist(_point(oxygen), _point(group))
    for bond in inner_bonds:
        length = math.dist(_point(by_id[bond.get("B")]), _point(by_id[bond.get("E")]))
        assert length == pytest.approx(outer_length, rel=1e-9)
    if label == "Ph":
        ring = [b.get("Order", "1") for b in inner_bonds if b is not attachment]
        assert sorted(ring) == ["1", "1", "1", "2", "2", "2"]


def test_group_label_export_is_deterministic():
    state = _label_state("Ph")
    assert _export_cdxml(state)[0] == _export_cdxml(state)[0]


@pytest.mark.parametrize(
    ("label", "bonds", "annotations", "match"),
    [
        ("Me", [], None, "found 0"),
        ("Ph", [Bond(0, 1), Bond(1, 2)], None, "found 2"),
        ("tBu", [Bond(0, 1, order=2, style="double")], None, "order 2"),
        ("Me", [Bond(1, 0, style="wedge")], None, "style 'wedge'"),
        ("Ph", [Bond(1, 0, style="hash")], None, "wide end"),
        ("Me", [Bond(0, 1)], {1: {"formal_charge": -1}}, "charge or radical"),
        ("tBu", [Bond(0, 1)], {1: {"radical_electrons": 1}}, "charge or radical"),
    ],
)
def test_group_label_attachment_refusals(label, bonds, annotations, match):
    state = _label_state(
        label,
        bonds=bonds,
        annotations=annotations,
        extra_atoms={2: Atom("C", 50.0, 0.0)},
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match=match):
        _export_cdxml(state)


@pytest.mark.parametrize("label", ["Et", "t-Bu", "OMe", "CO2Me", "PPh3"])
def test_unverified_alias_labels_still_refuse(label):
    with pytest.raises(CdxmlUnsupportedObjectError, match="without a verified"):
        _export_cdxml(_label_state(label))


# 3. Literal Ar is a drawn unexpanded placeholder; explicit argon stays distinct.


def test_raw_ar_requires_explicit_semantics_before_writing(tmp_path):
    from chemvas.bootstrap import document_render as cli

    state = _label_state("Ar")
    with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
        _export_cdxml(state)
    source = tmp_path / "unbound.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    before = source.read_bytes()
    output = tmp_path / "output.cdxml"
    with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
        cli._render_document(
            source, output=output, background="white", dpi=300, width_mm=170.0
        )
    assert source.read_bytes() == before
    assert not output.exists()


def test_bound_argon_exports_element_18():
    xml_bytes, _ = _export_bound(
        _label_state("Ar"), {1: CdxmlLabelBinding.element_identity("Ar")}
    )
    root = ET.fromstring(xml_bytes)
    _assert_label_vocabulary_and_ids(root)
    (argon,) = [n for n in _top_nodes(root) if n.get("Element") == "18"]
    assert argon.get("NodeType") is None and argon.find("fragment") is None
    assert _label_text(argon) == "Ar"


@pytest.mark.parametrize(
    ("neighbor_element", "atomic_number"), [("O", "8"), ("P", "15")]
)
def test_bound_generic_aryl_keeps_display_with_native_ary_query(
    neighbor_element, atomic_number
):
    xml_bytes, _ = _export_bound(
        _label_state(
            "Ar", extra_atoms={0: Atom(neighbor_element, 0.0, 0.0, explicit_label=True)}
        ),
        {1: CdxmlLabelBinding.generic_aryl()},
    )
    root = ET.fromstring(xml_bytes)
    _assert_label_vocabulary_and_ids(root)
    (oxygen,) = [n for n in _top_nodes(root) if n.get("Element") == atomic_number]
    (group,) = [n for n in _top_nodes(root) if n.get("NodeType") == "Nickname"]
    assert "Element" not in group.attrib
    inner = group.find("fragment")
    query = inner.find('n[@GenericNickname="ARY"]')
    assert query.get("NodeType") == "GenericNickname"
    assert _label_text(query) == "ARY"
    assert "Element" not in query.attrib
    port = inner.find('n[@NodeType="ExternalConnectionPoint"]')
    assert inner.find("b").get("B") == query.get("id")
    assert inner.find("b").get("E") == port.get("id")
    assert _label_text(group) == "Ar"
    assert group.find("t").get("InterpretChemically") == "yes"
    assert oxygen.find("t").get("InterpretChemically") == "yes"
    (outer,) = _top_bonds(root)
    assert outer.get("Order", "1") == "1"
    assert (outer.get("B"), outer.get("E")) == (oxygen.get("id"), group.get("id"))


def test_bound_concrete_aryl_keeps_phenyl_graph_and_ar_label():
    xml_bytes, _ = _export_bound(
        _label_state("Ar"), {1: CdxmlLabelBinding.aryl_fragment("Ph")}
    )
    root = ET.fromstring(xml_bytes)
    _assert_label_vocabulary_and_ids(root)
    _, group = _nickname_parts(root)
    assert group.get("NodeType") == "Nickname"
    assert _label_text(group) == "Ar"
    (inner,) = group.findall("fragment")
    carbons = [n for n in inner.findall("n") if n.get("NodeType") is None]
    assert len(carbons) == 6
    assert sum(int(n.get("NumHydrogens")) for n in carbons) == 5


@pytest.mark.parametrize(
    ("label", "binding", "match"),
    [
        ("Ar", CdxmlLabelBinding.aryl_fragment("Me"), "no verified aryl"),
        ("Ar", CdxmlLabelBinding.aryl_fragment("Tol"), "no verified aryl"),
        ("Me", CdxmlLabelBinding.generic_aryl(), "alias"),
        ("N", CdxmlLabelBinding.generic_aryl(), "only to the label 'Ar'"),
        ("Ar", "argon", "must be a CdxmlLabelBinding"),
        ("Ac", CdxmlLabelBinding.element_identity("Ac"), "alias"),
        (_H_A, CdxmlLabelBinding.element_identity("He"), "does not match"),
        ("Ar", CdxmlLabelBinding("isotope"), "unknown label binding"),
    ],
)
def test_label_binding_refusals(label, binding, match):
    with pytest.raises(CdxmlUnsupportedObjectError, match=match):
        _export_bound(_label_state(label), {1: binding})


def test_label_binding_for_missing_atom_refuses():
    with pytest.raises(CdxmlUnsupportedObjectError, match="not in the document"):
        _export_bound(_label_state("N"), {9: CdxmlLabelBinding.generic_aryl()})


def test_generic_aryl_refuses_double_attachment():
    state = _label_state("Ar", bonds=[Bond(0, 1, order=2, style="double")])
    with pytest.raises(CdxmlUnsupportedObjectError, match="order 2"):
        _export_bound(state, {1: CdxmlLabelBinding.generic_aryl()})


class _StrSubclass(str):
    pass


# Each meaning takes exactly its own field, as an exact str; anything else is
# the caller contradicting itself and is refused, never dropped or converted.
@pytest.mark.parametrize(
    ("label", "binding", "match"),
    [
        # Conflicting or extra fields.
        (
            "Ar",
            CdxmlLabelBinding("element", element="Ar", fragment="Ph"),
            "'element' takes no fragment field",
        ),
        (
            _H_A,
            CdxmlLabelBinding("element", element="H", fragment="Ph"),
            "'element' takes no fragment field",
        ),
        (
            "Ar",
            CdxmlLabelBinding("generic_aryl", fragment="Ph"),
            "'generic_aryl' takes no fragment field",
        ),
        (
            "Ar",
            CdxmlLabelBinding("generic_aryl", element="Ar"),
            "'generic_aryl' takes no element field",
        ),
        (
            "Ar",
            CdxmlLabelBinding("aryl_fragment", element="Ar", fragment="Ph"),
            "'aryl_fragment' takes no element field",
        ),
        (
            "Ar",
            CdxmlLabelBinding("generic_aryl", fragment=""),
            "'generic_aryl' takes no fragment field",
        ),
        # Missing required field.
        (
            "Ar",
            CdxmlLabelBinding("element"),
            "'element' needs its element field as a str",
        ),
        (
            "Ar",
            CdxmlLabelBinding("aryl_fragment"),
            "'aryl_fragment' needs its fragment field as a str",
        ),
        # Required field that is not exactly a str.
        (
            "Ar",
            CdxmlLabelBinding("element", element=18),
            "needs its element field as a str",
        ),
        (
            "Ar",
            CdxmlLabelBinding("element", element=b"Ar"),
            "needs its element field as a str",
        ),
        (
            "Ar",
            CdxmlLabelBinding("element", element=_StrSubclass("Ar")),
            "needs its element field as a str",
        ),
        ("Ar", CdxmlLabelBinding.aryl_fragment(1), "needs its fragment field as a str"),
        (
            "Ar",
            CdxmlLabelBinding.aryl_fragment(b"Ph"),
            "needs its fragment field as a str",
        ),
        (
            "Ar",
            CdxmlLabelBinding.aryl_fragment(["Ph"]),
            "needs its fragment field as a str",
        ),
        (
            "Ar",
            CdxmlLabelBinding.aryl_fragment(_StrSubclass("Ph")),
            "needs its fragment field as a str",
        ),
        # Unknown or mistyped meaning.
        ("Ar", CdxmlLabelBinding("isotope"), "unknown label binding meaning"),
        ("Ar", CdxmlLabelBinding(""), "unknown label binding meaning"),
        (
            "Ar",
            CdxmlLabelBinding("Element", element="Ar"),
            "unknown label binding meaning",
        ),
        ("Ar", CdxmlLabelBinding(None), "unknown label binding meaning"),
        ("Ar", CdxmlLabelBinding(1), "unknown label binding meaning"),
        (
            "Ar",
            CdxmlLabelBinding(_StrSubclass("element"), element="Ar"),
            "unknown label binding meaning",
        ),
    ],
)
def test_label_binding_field_contract_refusals(label, binding, match):
    with pytest.raises(CdxmlUnsupportedObjectError, match=match):
        _export_bound(_label_state(label), {1: binding})


def test_label_binding_field_contract_is_enforced_by_serialize_alone():
    binding = CdxmlLabelBinding("element", element="Ar", fragment="Ph")
    state = _label_state("Ar")
    with offscreen_document_scene(state, command="test-cdxml") as context:
        items, plan = _resolved_export(context)
        with pytest.raises(CdxmlUnsupportedObjectError, match="takes no fragment"):
            serialize_cdxml(context, items, plan, label_bindings={1: binding})


@pytest.mark.parametrize(
    ("label", "factory", "explicit"),
    [
        (
            "Ar",
            CdxmlLabelBinding.element_identity("Ar"),
            CdxmlLabelBinding("element", element="Ar"),
        ),
        (
            _H_A,
            CdxmlLabelBinding.element_identity("H"),
            CdxmlLabelBinding("element", element="H"),
        ),
        ("Ar", CdxmlLabelBinding.generic_aryl(), CdxmlLabelBinding("generic_aryl")),
        (
            "Ar",
            CdxmlLabelBinding.aryl_fragment("Ph"),
            CdxmlLabelBinding("aryl_fragment", fragment="Ph"),
        ),
    ],
)
def test_well_formed_bindings_still_export_unchanged(label, factory, explicit):
    assert factory == explicit
    factory_bytes, _ = _export_bound(_label_state(label), {1: factory})
    explicit_bytes, _ = _export_bound(_label_state(label), {1: explicit})
    assert factory_bytes == explicit_bytes


# 5. Document contract: source and model unchanged, atomic refusal.


@pytest.mark.parametrize("label", ["Ar", _H_A, "Et"])
def test_label_refusal_keeps_destination_and_writes_nothing(tmp_path, label):
    existing = tmp_path / "existing.cdxml"
    existing.write_bytes(b"previous export")
    fresh = tmp_path / "fresh.cdxml"
    state = _label_state(
        label, annotations={1: {"formal_charge": 1}} if label == "Ar" else None
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        for dest in (existing, fresh):
            with pytest.raises(CdxmlUnsupportedObjectError):
                service.export_figure(
                    str(dest),
                    fmt="cdxml",
                    scope="sheet",
                    sizing="custom",
                    target_width_mm=170.0,
                )
    assert existing.read_bytes() == b"previous export"
    assert not fresh.exists()


def test_group_label_cli_export_leaves_source_unchanged(tmp_path):
    from chemvas.bootstrap import document_render as cli

    source = tmp_path / "me.chemvas"
    write_document(source, _label_state("Me"), CANVAS_FILE_VERSION)
    before = source.read_bytes()
    output = tmp_path / "me.cdxml"
    report = cli._render_document(
        source, output=output, background="white", dpi=300, width_mm=170.0
    )
    assert report["written"] is True
    assert source.read_bytes() == before
    _, group = _nickname_parts(ET.fromstring(output.read_bytes()))
    assert group.get("NodeType") == "Nickname"


def test_bound_export_leaves_model_unchanged():
    import json

    state = _simple_state(
        atoms={
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 25.0, 0.0, explicit_label=True),
            2: Atom(_H_A, -25.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(0, 1), Bond(0, 2)],
    )
    before_state = json.dumps(state, sort_keys=True)
    bindings = {
        1: CdxmlLabelBinding.generic_aryl(),
        2: CdxmlLabelBinding.element_identity("H"),
    }
    with offscreen_document_scene(state, command="test-cdxml") as context:
        model_before = json.dumps(serialize_model_state(context.model), sort_keys=True)
        items, plan = _resolved_export(context)
        preflight_cdxml(context, items, plan, label_bindings=bindings)
        serialize_cdxml(context, items, plan, label_bindings=bindings)
        model_after = json.dumps(serialize_model_state(context.model), sort_keys=True)
    assert model_before == model_after
    assert json.dumps(state, sort_keys=True) == before_state


# 6. Label support does not unlock marks, dashed lines or other refusals.


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        (
            {
                "marks": [
                    {
                        "kind": "plus",
                        "atom_id": 0,
                        "text": "+",
                        "x": 2.0,
                        "y": -2.0,
                        "dx": 2.0,
                        "dy": -2.0,
                        "_auto_position": True,
                    }
                ]
            },
            "mark",
        ),
        (
            {
                "shapes": [
                    {
                        "kind": "shape",
                        "left": 0.0,
                        "top": 60.0,
                        "right": 20.0,
                        "bottom": 80.0,
                        "shape_kind": "rect",
                        "stroke_style": "dashed",
                    }
                ]
            },
            "dashed",
        ),
    ],
)
def test_group_label_does_not_unlock_unsupported_objects(tmp_path, extra, match):
    state = _label_state("Me")
    for key, value in extra.items():
        state[key] = value
    dest = tmp_path / "compound.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        with pytest.raises(CdxmlUnsupportedObjectError, match=match):
            service.export_figure(
                str(dest),
                fmt="cdxml",
                scope="sheet",
                sizing="custom",
                target_width_mm=170.0,
            )
    assert not dest.exists()


@pytest.mark.parametrize("contact", ["margin", "node_ink", "bond_ink"])
@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
def test_square_bracket_checks_ink_and_actual_paint_order(contact, boundary):
    from PyQt6.QtGui import QPainterPathStroker

    from chemvas.ui.canvas.graphics_items import AtomLabelItem

    state = _simple_state(
        atoms={0: Atom("P", 0.0, 0.0), 1: Atom("C", 40.0, 0.0)}, bonds=[Bond(0, 1)]
    )
    state["ts_brackets"] = [
        {
            "kind": "ts_bracket",
            "left": -6.0
            if contact == "margin"
            else (-3.0 if contact == "node_ink" else 20.0),
            "top": -15.0,
            "right": 45.0,
            "bottom": 15.0,
            "bracket_kind": "square_pair",
        }
    ]
    with offscreen_document_scene(state, command="test-cdxml") as context:
        bracket = next(i for i in context.scene.items() if i.data(0) == "ts_bracket")
        bracket.setZValue(1)
        atoms = [i for i in context.scene.items() if i.data(0) == "atom"]
        for item in atoms:
            item.setZValue(2)
        for item in context.state.bond_graphics_state.bond_items[0]:
            item.setZValue(0)
        label = next(
            i for i in atoms if isinstance(i, AtomLabelItem) and i.data(1) == 0
        )
        native_ink = label.mapToScene(label.glyph_path())
        bracket_ink = bracket.mapToScene(
            QPainterPathStroker(bracket.pen()).createStroke(bracket.path())
        )
        if contact == "margin":
            assert bracket.sceneBoundingRect().intersects(label.sceneBoundingRect())
            assert not bracket_ink.intersects(native_ink)
        elif contact == "node_ink":
            assert bracket_ink.intersects(native_ink)
        else:
            assert bracket_ink.intersects(
                context.state.bond_graphics_state.bond_items[0][0].shape()
            )
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        if contact == "bond_ink":
            with pytest.raises(CdxmlUnsupportedObjectError, match="interleaves"):
                operation(context, items, plan)
        else:
            operation(context, items, plan)


@pytest.mark.parametrize("overlap", [False, True])
@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
def test_note_hit_margin_does_not_replace_painted_ink(overlap, boundary):
    from chemvas.ui.canvas.graphics_items import note_paint_scene_path

    state = _simple_state(
        atoms={0: Atom("C", 0, 0), 1: Atom("C", 40, 0)},
        notes=[{"text": "example", "x": 5, "y": 0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note = next(i for i in context.scene.items() if i.data(0) == "note")
        ink = note_paint_scene_path(note).boundingRect()
        note.moveBy(0, (-0.1 if overlap else -2.0) - ink.bottom())
        note.setZValue(1)
        for item in context.scene.items():
            if item.data(0) == "atom":
                item.setZValue(2)
            elif item.data(0) == "bond":
                item.setZValue(0)
        bond = context.state.bond_graphics_state.bond_items[0][0]
        assert note.sceneBoundingRect().intersects(bond.sceneBoundingRect())
        assert (
            note_paint_scene_path(note)
            .boundingRect()
            .intersects(bond.sceneBoundingRect())
            == overlap
        )
        items, plan = _resolved_export(context)
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        if overlap:
            with pytest.raises(CdxmlUnsupportedObjectError, match="interleaves"):
                operation(context, items, plan)
        else:
            operation(context, items, plan)


@pytest.mark.parametrize("overlap", [False, True])
@pytest.mark.parametrize("boundary", ["preflight", "serialize"])
def test_fragment_pair_uses_painted_ink_not_label_hit_boxes(overlap, boundary):
    y = 0.0 if overlap else 15.0
    state = _simple_state(
        atoms={
            0: Atom("P", 0, 0),
            1: Atom("C", 40, 0),
            2: Atom("P", 0, y),
            3: Atom("C", 40, y),
        },
        bonds=[Bond(0, 1), Bond(2, 3)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        for item in context.scene.items():
            if item.data(0) == "bond":
                item.setZValue(item.data(1))
            elif item.data(0) == "atom":
                item.setZValue(2 if item.data(1) < 2 else 3)
        labels = [
            i
            for i in context.scene.items()
            if i.data(0) == "atom" and i.data(1) in {0, 2}
        ]
        assert labels[0].sceneBoundingRect().intersects(labels[1].sceneBoundingRect())
        items, plan = _resolved_export(context)
        operation = preflight_cdxml if boundary == "preflight" else serialize_cdxml
        if overlap:
            with pytest.raises(CdxmlUnsupportedObjectError, match="interleave"):
                operation(context, items, plan)
        else:
            operation(context, items, plan)


def test_actual_mixed_note_uses_painted_font_ranges_and_original_text():
    from PyQt6.QtGui import QFontDatabase

    if "Apple SD Gothic Neo" not in QFontDatabase.families():
        pytest.skip("actual source note font requires macOS")
    text = "Ar = 4-FC₆H₄"
    state = _simple_state(
        atoms={},
        bonds=[],
        notes=[
            {
                "text": text,
                "x": 120,
                "y": -389,
                "html": '<p style="white-space:pre-wrap"><span style="font-size:7pt; font-weight:400; color:#8C969F">'
                + text
                + "</span></p>",
            }
        ],
        settings_overrides={
            "text_font_family": "Apple SD Gothic Neo",
            "text_font_size": 7,
        },
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note = context.state.note_items()[0]
        note.boundingRect()
        block = note.document().begin()
        runs = block.layout().glyphRuns(0, block.length() - 1)
        assert {r.rawFont().familyName() for r in runs} == {
            "Apple SD Gothic Neo",
            "Helvetica",
        }
        items, plan = _resolved_export(context)
        preflight_cdxml(context, items, plan)
        root = ET.fromstring(serialize_cdxml(context, items, plan))
        fonts = {f.get("id"): f.get("name") for f in root.findall("./fonttable/font")}
        segments = root.findall("./page/t/s")
        assert "".join(s.text or "" for s in segments) == text
        assert [(s.text, fonts[s.get("font")]) for s in segments] == [
            ("Ar = 4-FC", "Apple SD Gothic Neo"),
            ("₆", "Helvetica"),
            ("H₄", "Apple SD Gothic Neo"),
        ]
        scale = plan.out_w_pt / plan.source_w
        assert all(
            float(s.get("size")) == pytest.approx(9 * scale, rel=0, abs=0.025)
            for s in segments
        )


@pytest.mark.parametrize("text", ["A\u0301₆", "A😀"])
def test_ambiguous_mixed_note_glyph_mapping_still_refuses(text):
    from PyQt6.QtGui import QFontDatabase

    if "Apple SD Gothic Neo" not in QFontDatabase.families():
        pytest.skip("actual source note font requires macOS")
    state = _simple_state(
        atoms={},
        bonds=[],
        notes=[
            {
                "text": text,
                "x": 0,
                "y": 0,
                "html": '<p><span style="font-size:7pt">' + text + "</span></p>",
            }
        ],
        settings_overrides={
            "text_font_family": "Apple SD Gothic Neo",
            "text_font_size": 7,
        },
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note = context.state.note_items()[0]
        note.boundingRect()
        block = note.document().begin()
        assert (
            len(
                {
                    r.rawFont().familyName()
                    for r in block.layout().glyphRuns(0, block.length() - 1)
                }
            )
            > 1
        )
        items, plan = _resolved_export(context)
        with pytest.raises(
            CdxmlUnsupportedObjectError, match="glyph|surrogate|ligature"
        ):
            serialize_cdxml(context, items, plan)


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<p><span style="font-size:7pt; font-weight:700; color:#8C969F">TS_M2<br/>31.6</span></p>',
            ["TS_M2", "31.6"],
        ),
        (
            '<p style="white-space:pre-wrap"><span style="font-size:7pt; color:#8C969F"> A &amp; B  <br/><br/>−42.4<br/></span></p>',
            [" A & B  ", "−42.4"],
        ),
    ],
)
def test_note_soft_linebreak_is_layout_not_visible_separator(html, expected):
    import json

    state = _simple_state(
        atoms={}, bonds=[], notes=[{"text": "", "html": html, "x": 10, "y": 20}]
    )
    state_before = json.dumps(state, ensure_ascii=False, sort_keys=True)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note = context.state.note_items()[0]
        note.boundingRect()
        block = note.document().begin()
        assert "\u2028" in block.text()
        text_before = note.document().toPlainText()
        html_before = note.document().toHtml()
        items, plan = _resolved_export(context)
        preflight_cdxml(context, items, plan)
        root = ET.fromstring(serialize_cdxml(context, items, plan))
        lines = root.findall("./page/t")
        assert [
            "".join(s.text or "" for s in t.findall("s")) for t in lines
        ] == expected
        assert not any(
            "\u2028" in (s.text or "") for t in lines for s in t.findall("s")
        )
        layout = block.layout()
        painted_baselines = []
        for index in range(layout.lineCount()):
            line = layout.lineAt(index)
            # Derive expected nonempty source lines from Qt, independently of
            # the exporter's UTF-16 range slicing.
            source_text = block.text()[
                line.textStart() : line.textStart() + line.textLength()
            ]
            if source_text and source_text != "\u2028":
                baseline = note.mapToScene(
                    layout.position().x() + line.x(),
                    layout.position().y() + line.y() + line.ascent(),
                )
                scale = plan.out_w_pt / plan.source_w
                painted_baselines.append(
                    (
                        (baseline.x() - plan.source_x) * scale,
                        (baseline.y() - plan.source_y) * scale,
                    )
                )
        assert len(painted_baselines) == len(lines)
        for t, baseline in zip(lines, painted_baselines, strict=True):
            assert tuple(map(float, t.get("p").split())) == pytest.approx(
                baseline, rel=1e-10
            )
        assert note.document().toPlainText() == text_before
        assert note.document().toHtml() == html_before
    assert json.dumps(state, ensure_ascii=False, sort_keys=True) == state_before


@pytest.mark.parametrize("degree", [0, 1, 2])
def test_explicit_generic_aryl_preserves_outer_connections(degree):
    atoms = {0: Atom("Ar", 40, 20, explicit_label=True)}
    for index in range(degree):
        atoms[index + 1] = Atom("C", 20 + index * 40, 20)
    bonds = [Bond(index + 1, 0, style="dotted") for index in range(degree)]
    state = _simple_state(atoms=atoms, bonds=bonds)
    raw, _ = _export_bound(state, {0: CdxmlLabelBinding.generic_aryl()})
    root = ET.fromstring(raw)
    group = next(n for n in _top_nodes(root) if n.get("NodeType") == "Nickname")
    query = group.find('./fragment/n[@GenericNickname="ARY"]')
    assert query is not None and _label_text(group) == "Ar"
    assert not any(n.get("Element") == "18" for n in root.iter("n"))
    outer = _top_bonds(root)
    assert len(outer) == degree
    assert all(
        b.get("E") == group.get("id") and b.get("Display") == "Dash" for b in outer
    )
    assert len(
        group.findall('./fragment/n[@NodeType="ExternalConnectionPoint"]')
    ) == bool(degree)


def test_generic_aryl_refuses_unverified_three_connections():
    state = _simple_state(
        atoms={
            0: Atom("Ar", 40, 40),
            1: Atom("C", 20, 40),
            2: Atom("C", 60, 40),
            3: Atom("C", 40, 60),
        },
        bonds=[Bond(1, 0), Bond(2, 0), Bond(3, 0)],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="at most two"):
        _export_bound(state, {0: CdxmlLabelBinding.generic_aryl()})
