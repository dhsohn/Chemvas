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
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService

pytestmark = pytest.mark.usefixtures("qt_application")


# ── Helpers ────────────────────────────────────────────────────────────


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
    "fragment": {"id", "Z"},
    "n": {"id", "p", "Element", "Charge", "color"},
    "b": {"id", "B", "E", "Order", "Display", "DoublePosition", "color"},
    "t": {"id", "p", "Z", "Justification", "InterpretChemically", "CaptionLineHeight"},
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
    "group": {"id", "Z"},
}


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
        for g in root.findall(".//graphic"):
            if g.get("GraphicType") == "Line":
                vals = [float(v) for v in g.get("BoundingBox").split()]
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
    assert size_170 / size_84 == pytest.approx(expected_ratio, rel=1e-9)


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
    ratio = size_170 / size_84
    expected = points_for_mm(170.0) / points_for_mm(84.0)
    assert ratio == pytest.approx(expected, rel=1e-9)


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


def test_refuse_bold_bond():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, style="bold_in")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


def test_refuse_dotted_bond():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, style="dotted")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


def test_refuse_double_either_bond():
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=2, style="double_either")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


def test_refuse_double_outer_bond():
    # The outer variant shortens the axis line inside rings; one CDXML
    # DoublePosition cannot say which of the two lines is shortened.
    state = _simple_state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 20.0, 0.0)},
        bonds=[Bond(0, 1, order=2, style="double_outer")],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="no proved"):
        _export_cdxml(state)


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


def test_line_exports_as_graphic():
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
    graphics = root.findall(".//graphic")
    line_graphics = [g for g in graphics if g.get("GraphicType") == "Line"]
    assert len(line_graphics) >= 1
    assert line_graphics[0].get("ArrowType") == "NoHead"


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
    graphics = groups[0].findall("graphic")
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
    assert exported_size == pytest.approx(expected_size, rel=1e-9), (
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
    label_ts = [t for t in root.findall(".//t") if t.get("InterpretChemically") == "no"]
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
    graphics = root.findall(".//graphic")
    lines = [g for g in graphics if g.get("GraphicType") == "Line"]
    assert len(lines) >= 1
    bbox = [float(v) for v in lines[0].get("BoundingBox").split()]
    assert bbox[1] > bbox[3], (
        f"BoundingBox y1={bbox[1]} should be > y2={bbox[3]} for negative slope "
        "(endpoint order preserved, not min/max)"
    )


# ── Z-order: page children reflect scene ascending order ────────────


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
        z = child.get("Z")
        assert z is not None, f"<{child.tag}> missing Z attribute"
        z_values.append(int(z))
        if child.tag == "t" and child.get("InterpretChemically") == "no":
            cdxml_roles_ordered.append("note")
        elif child.tag == "graphic" and child.get("GraphicType") == "Line":
            cdxml_roles_ordered.append("line")
    assert z_values == sorted(z_values), "Z values must be monotonically increasing"
    assert len(z_values) == len(set(z_values)), "Z values must be unique"
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
        notes=[{"text": "overlapping", "x": 10.0, "y": 0.0}],
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


def test_arrow_components_no_head3d_tail3d():
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
    for g in groups:
        for graphic in g.findall("graphic"):
            assert graphic.get("Head3D") is None, (
                "arrow component should not have Head3D"
            )
            assert graphic.get("Tail3D") is None, (
                "arrow component should not have Tail3D"
            )


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


# ── Formal charge with mark refuses ──────────────────────────────────


def test_refuse_formal_charge_with_mark():
    state = _simple_state(
        atoms={0: Atom("N", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"formal_charge": 1}},
        marks=[
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
        ],
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="mark"):
        _export_cdxml(state)


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


# ── Rotation refusal ─────────────────────────────────────────────────


def test_refuse_rotated_note_no_record():
    from PyQt6.QtGui import QTransform

    state = _simple_state(
        notes=[{"text": "rotated", "x": 0.0, "y": 30.0}],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        note_item = context.state.note_items()[0]
        angle = 45.0
        t = QTransform()
        t.rotate(angle)
        note_item.setTransform(t)

        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="rotated"):
            preflight_cdxml(context, items, plan)


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
    for node in root.iter("n"):
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
    ("reverse", "expected_side"), [(False, "Right"), (True, "Left")]
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
        # CDX "Right" looks from B to E on the y-down page: normal (-dy, dx).
        inward = -(ey - by) * (cx - (bx + ex) / 2) + (ex - bx) * (cy - (by + ey) / 2)
        assert bond.get("DoublePosition") == ("Right" if inward > 0 else "Left")
        assert bond.get("DoublePosition") == expected_side


@pytest.mark.parametrize(
    ("substituent_y", "expected_side"), [(17.32, "Right"), (-17.32, "Left")]
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
    assert by_id[nodes[1]].get("Element") == "7"
    assert by_id[nodes[1]].get("Charge") == "1"
    assert by_id[nodes[2]].get("Element") == "8"
    assert by_id[nodes[2]].get("Charge") is None
    assert by_id[nodes[3]].get("Element") == "8"
    assert by_id[nodes[3]].get("Charge") == "-1"
    (double,) = [bond for bond in root.iter("b") if bond.get("Order") == "2"]
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


# ── Optional RDKit consumer check (molecule level only) ──────────────
#
# RDKit's CDXML reader is an independent consumer of the exported graph,
# charges and wedge directions. It does not verify ChemDraw rendering.


def _rdkit_molecules_from_cdxml(xml_bytes):
    pytest.importorskip("rdkit")
    from rdkit import Chem

    reader = getattr(Chem, "MolsFromCDXML", None)
    if reader is None:
        pytest.skip("this RDKit build has no CDXML reader")
    return Chem, [mol for mol in reader(xml_bytes.decode("utf-8")) if mol is not None]


def test_rdkit_reads_ring_tool_benzene_as_benzene():
    xml_bytes, _ = _export_cdxml(_benzene_state())
    Chem, molecules = _rdkit_molecules_from_cdxml(xml_bytes)
    assert len(molecules) == 1
    assert Chem.MolToSmiles(molecules[0]) == Chem.CanonSmiles("c1ccccc1")


@pytest.mark.parametrize(
    ("style", "expected_smiles", "expected_cip"),
    [("wedge", "C[C@@H](O)CC", "R"), ("hash", "C[C@H](O)CC", "S")],
)
def test_rdkit_reads_the_drawn_absolute_configuration(
    style, expected_smiles, expected_cip
):
    from chemvas.core.molfile import write_molfile

    atoms, bonds = _butan_2_ol(style)
    state = _simple_state(atoms=atoms, bonds=bonds)
    xml_bytes, _ = _export_cdxml(state)
    Chem, molecules = _rdkit_molecules_from_cdxml(xml_bytes)
    assert len(molecules) == 1
    molecule = molecules[0]
    assert Chem.MolToSmiles(molecule) == Chem.CanonSmiles(expected_smiles)
    assert Chem.FindMolChiralCenters(molecule) == [(0, expected_cip)]
    # The MOL writer encodes the same wedge with the same begin atom.
    via_molfile = Chem.MolFromMolBlock(
        write_molfile(deserialize_model_state(state["model"]))
    )
    assert Chem.MolToSmiles(via_molfile) == Chem.MolToSmiles(molecule)


def test_rdkit_reads_charges_and_heteroatoms():
    xml_bytes, _ = _export_cdxml(_nitromethane_state())
    Chem, molecules = _rdkit_molecules_from_cdxml(xml_bytes)
    assert len(molecules) == 1
    assert Chem.MolToSmiles(molecules[0]) == Chem.CanonSmiles("C[N+](=O)[O-]")
