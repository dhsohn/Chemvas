"""CDXML export of dashed lines and TS brackets (synthetic documents only).

One mock energy diagram drawn from the public document schema: a small
structure, fake plain notes ("A", "TS1", "x"), solid levels, dashed
connectors, a square TS bracket around the fake TS level and a double dagger,
with deliberately overlapping z-order. No research values, figures or label
sidecars are used. Each supported object is checked for its exact
coordinates, colour, width, font, label, uniform scale and z-order; each
refused object must leave no output and keep an existing destination.
A square bracket between a molecule's bonds and atom labels is judged by
its painted strokes: clear strokes export, touching strokes refuse.
Z is written on every n, b, t and graphic (the objects ZOrder.htm lists),
never on a group or fragment: one contiguous block per page object.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.annotations import (
    BRACKET_SYMBOLS,
    bracket_path_commands,
    bracket_stroke_width,
    bracket_symbol_layout,
)
from chemvas.ui.export.export_cdxml import (
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService
from tests.document_file_helpers import write_document

pytestmark = pytest.mark.usefixtures("qt_application")

_SQUARE = {"left": 110.0, "top": 20.0, "right": 170.0, "bottom": 60.0}
_DAGGER = {"left": 172.0, "top": 10.0, "right": 192.0, "bottom": 35.0}

_LEVELS = [
    {"kind": "line", "start": [40.0, 100.0], "end": [80.0, 100.0]},
    {"kind": "line", "start": [120.0, 40.0], "end": [160.0, 40.0]},
    {
        "kind": "line",
        "start": [200.0, 130.0],
        "end": [240.0, 130.0],
        "color": "#0000ff",
    },
]
# Each connector starts exactly on a level end, so the two overlap there.
_CONNECTORS = [
    {"kind": "line_dashed", "start": [80.0, 100.0], "end": [120.0, 40.0]},
    {
        "kind": "line_dashed",
        "start": [160.0, 40.0],
        "end": [200.0, 130.0],
        "color": "#cc0000",
    },
]
_NOTES = [
    {"text": "A", "x": 50.0, "y": 110.0},
    {"text": "TS1", "x": 125.0, "y": 45.0},
    {"text": "x", "x": 210.0, "y": 140.0},
]


# ZOrder.htm: Z belongs to Node, Bond, Text and Graphic, not Group, Fragment
# or Page; a missing Z is 0 and objects sharing 0 are ordered randomly.
_Z_TAGS = ("n", "b", "t", "graphic", "arrow")


def _line_endpoints(line):
    assert line.tag == "arrow"
    assert line.get("ArrowheadHead", "None") == "None"
    assert line.get("ArrowheadTail", "None") == "None"
    tail, head = line.get("Tail3D").split(), line.get("Head3D").split()
    assert tail[2] == head[2] == "0"
    return " ".join((*tail[:2], *head[:2]))


def _z_leaves(element):
    return [el for el in element.iter() if el.tag in _Z_TAGS]


def _z(element):
    return int(element.get("Z"))


def _page_z_blocks(page):
    """Sorted Z values of each page child; together they must be 1..N."""
    blocks = [sorted(_z(el) for el in _z_leaves(child)) for child in page]
    flat = [z for block in blocks for z in block]
    assert all(blocks)
    assert flat == list(range(1, len(flat) + 1))
    return blocks


def _bracket(kind, rect):
    return {"kind": "ts_bracket", "bracket_kind": kind, **rect}


def _state(*, arrows=None, ts_brackets=None, notes=None, atoms=None, charges=None):
    if atoms is None:
        # Far from every graphic so no stacking rule is involved.
        atoms = {0: Atom("C", 300.0, 200.0), 1: Atom("O", 320.0, 200.0)}
    model = MoleculeModel(atoms=atoms, bonds=[Bond(0, 1)])
    for atom_id, charge in (charges or {}).items():
        model.set_atom_annotation(atom_id, {"formal_charge": charge})
    return {
        "model": serialize_model_state(model),
        "ring_fills": [],
        "notes": notes or [],
        "marks": [],
        "arrows": arrows or [],
        "ts_brackets": ts_brackets or [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def _mock_diagram(*, dagger=True):
    # The dagger is a glyph in the document font; tests that do not check it
    # leave it out so a font without U+2021 cannot decide their outcome.
    brackets = [_bracket("square_pair", _SQUARE)]
    if dagger:
        brackets.append(_bracket("double_dagger", _DAGGER))
    return _state(arrows=[*_LEVELS, *_CONNECTORS], ts_brackets=brackets, notes=_NOTES)


def _export(context):
    service = FigureExportService(context)
    items, plan = service._resolve_figure_export(
        scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
    )
    preflight_cdxml(context, items, plan)
    return serialize_cdxml(context, items, plan), plan


def _f(value):
    return f"{value:.12g}"


def _bbox(x1, y1, x2, y2, plan):
    s = plan.out_w_pt / plan.source_w
    ox, oy = plan.source_x, plan.source_y
    values = ((x1 - ox) * s, (y1 - oy) * s, (x2 - ox) * s, (y2 - oy) * s)
    return " ".join(_f(v) for v in values)


def _color_hex(root, ref):
    entries = root.find("colortable").findall("color")
    entry = entries[int(ref) - 2]
    rgb = (round(float(entry.get(c)) * 255) for c in ("r", "g", "b"))
    return "#" + "".join(f"{v:02x}" for v in rgb)


def _primary_font_has(font, char):
    from PyQt6.QtGui import QRawFont

    return QRawFont.fromFont(font).supportsCharacter(ord(char))


def _bracket_item(context, kind):
    for item in context.state.ts_bracket_items():
        rec = context.state.ts_bracket_state.records[item.data(3)]
        if rec.bracket_kind == kind:
            return item
    raise AssertionError(kind)


def _assert_refused_and_kept(tmp_path, state, match):
    dest = tmp_path / "existing.cdxml"
    original = b"existing destination bytes"
    dest.write_bytes(original)
    fresh = tmp_path / "fresh.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        for target in (dest, fresh):
            with pytest.raises(CdxmlUnsupportedObjectError, match=match):
                service.export_figure(
                    str(target),
                    fmt="cdxml",
                    scope="sheet",
                    sizing="custom",
                    target_width_mm=170.0,
                )
    assert dest.read_bytes() == original
    assert not fresh.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["existing.cdxml"]


# ── Supported objects: exact values ───────────────────────────────────


def _page_lines(root):
    page = root.find("page")
    return [g for g in page if g.tag == "arrow"]


def test_solid_levels_keep_exact_geometry_width_and_colour():
    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        xml_bytes, plan = _export(context)
        arrow_width = context.state.tool_settings_state.arrow_line_width
        bond_hex = context.renderer.bond_pen().color().name()
    root = ET.fromstring(xml_bytes)
    s = plan.out_w_pt / plan.source_w
    solid = [g for g in _page_lines(root) if g.get("LineType") == "Solid"]
    assert [_line_endpoints(g) for g in solid] == [
        _bbox(*rec["start"], *rec["end"], plan) for rec in _LEVELS
    ]
    for g, rec in zip(solid, _LEVELS, strict=True):
        assert g.get("ArrowheadHead", "None") == "None"
        assert g.get("ArrowheadTail", "None") == "None"
        assert g.get("LineWidth") == _f(arrow_width * s)
        expected = rec.get("color", bond_hex)
        if expected == "#000000":
            assert g.get("color") is None
        else:
            assert _color_hex(root, g.get("color")) == expected


def test_dashed_connectors_are_native_dashed_lines():
    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        xml_bytes, plan = _export(context)
        arrow_width = context.state.tool_settings_state.arrow_line_width
        bond_hex = context.renderer.bond_pen().color().name()
    root = ET.fromstring(xml_bytes)
    s = plan.out_w_pt / plan.source_w
    dashed = [g for g in _page_lines(root) if g.get("LineType") == "Dashed"]
    assert [_line_endpoints(g) for g in dashed] == [
        _bbox(*rec["start"], *rec["end"], plan) for rec in _CONNECTORS
    ]
    for g, rec in zip(dashed, _CONNECTORS, strict=True):
        assert g.get("ArrowheadHead", "None") == "None"
        assert g.get("ArrowheadTail", "None") == "None"
        assert g.get("LineWidth") == _f(arrow_width * s)
        expected = rec.get("color", bond_hex)
        if expected == "#000000":
            assert g.get("color") is None
        else:
            assert _color_hex(root, g.get("color")) == expected
    # Never flattened: no extra solid pieces along a connector.
    assert len(_page_lines(root)) == len(_LEVELS) + len(_CONNECTORS)


def test_square_bracket_is_exact_m_l_polyline():
    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        xml_bytes, plan = _export(context)
        style = context.renderer.style
        bond_length = style.bond_length_px
        width = bracket_stroke_width(style.bond_line_width)
        paint = _bracket_item(context, "square_pair").brush().color().name()
    root = ET.fromstring(xml_bytes)
    s = plan.out_w_pt / plan.source_w
    bounds = (
        _SQUARE["left"],
        _SQUARE["top"],
        _SQUARE["right"] - _SQUARE["left"],
        _SQUARE["bottom"] - _SQUARE["top"],
    )
    expected = []
    current = None
    for cmd, args in bracket_path_commands(bounds, "square_pair", bond_length):
        assert cmd in ("M", "L")
        if cmd == "L":
            expected.append(_bbox(*current, *args, plan))
        current = args
    assert len(expected) == 6
    groups = [g for g in root.find("page") if g.tag == "group"]
    assert len(groups) == 1
    lines = list(groups[0])
    assert [_line_endpoints(g) for g in lines] == expected
    for g in lines:
        assert g.tag == "arrow"
        assert g.get("LineType") == "Solid"
        assert g.get("ArrowheadHead", "None") == "None"
        assert g.get("ArrowheadTail", "None") == "None"
        assert g.get("LineWidth") == _f(width * s)
        if paint == "#000000":
            assert g.get("color") is None
        else:
            assert _color_hex(root, g.get("color")) == paint


def test_double_dagger_is_exact_glyph_text():
    from PyQt6.QtGui import QFontInfo

    with offscreen_document_scene(_mock_diagram(), command="test-cdxml") as context:
        item = _bracket_item(context, "double_dagger")
        text, font = item.export_glyph_run()
        if not _primary_font_has(font, BRACKET_SYMBOLS["double_dagger"]):
            with pytest.raises(CdxmlUnsupportedObjectError, match="glyph"):
                _export(context)
            return
        xml_bytes, plan = _export(context)
        family = QFontInfo(font).family()
        paint = item.brush().color().name()
        bond_length = context.renderer.style.bond_length_px
    root = ET.fromstring(xml_bytes)
    s = plan.out_w_pt / plan.source_w
    bounds = (
        _DAGGER["left"],
        _DAGGER["top"],
        _DAGGER["right"] - _DAGGER["left"],
        _DAGGER["bottom"] - _DAGGER["top"],
    )
    pixels, x, y = bracket_symbol_layout(bounds, bond_length)
    assert text == "\u2021"
    daggers = [
        t for t in root.find("page") if t.tag == "t" and t.findtext("s") == "\u2021"
    ]
    assert len(daggers) == 1
    t_el = daggers[0]
    sx = (x - plan.source_x) * s
    sy = (y - plan.source_y) * s
    assert t_el.get("p") == f"{_f(sx)} {_f(sy)}"
    assert t_el.get("Justification") == "Left"
    assert t_el.get("InterpretChemically") == "no"
    (s_el,) = list(t_el)
    assert float(s_el.get("size")) == pytest.approx(pixels * s, rel=0, abs=0.025)
    fonts = {f.get("id"): f.get("name") for f in root.iter("font")}
    assert fonts[s_el.get("font")] == family
    if paint == "#000000":
        assert s_el.get("color") == "3"
    else:
        assert _color_hex(root, s_el.get("color")) == paint


def test_fake_notes_keep_exact_text():
    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        xml_bytes, _plan = _export(context)
    root = ET.fromstring(xml_bytes)
    texts = [
        "".join(s.text or "" for s in t)
        for t in root.find("page")
        if t.tag == "t" and t.findtext("s") not in BRACKET_SYMBOLS.values()
    ]
    assert sorted(texts) == sorted(n["text"] for n in _NOTES)


def test_mock_diagram_z_order_follows_scene():
    from PyQt6.QtCore import Qt

    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        roles = []
        for item in context.scene.items(Qt.SortOrder.AscendingOrder):
            role = item.data(0)
            if role in ("line", "line_dashed", "note", "ts_bracket"):
                roles.append(role)
        xml_bytes, _plan = _export(context)
    root = ET.fromstring(xml_bytes)
    page = root.find("page")
    _page_z_blocks(page)
    emitted = []
    for child in page:
        if child.tag == "arrow":
            dashed = child.get("LineType") == "Dashed"
            emitted.append("line_dashed" if dashed else "line")
        elif child.tag == "group":
            emitted.append("ts_bracket")
        elif child.tag == "t":
            glyph = child.findtext("s") in BRACKET_SYMBOLS.values()
            emitted.append("ts_bracket" if glyph else "note")
    assert emitted == roles
    assert roles.count("ts_bracket") == 1
    assert roles.count("line_dashed") == len(_CONNECTORS)


def test_every_z_object_has_its_own_explicit_z():
    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        xml_bytes, _plan = _export(context)
    root = ET.fromstring(xml_bytes)
    page = root.find("page")
    leaves = _z_leaves(page)
    assert {el.tag for el in leaves} == set(_Z_TAGS) - {"graphic"}
    for el in root.iter():
        if el.tag in _Z_TAGS:
            assert 1 <= _z(el) <= 32767
        else:
            assert "Z" not in el.attrib, f"<{el.tag}> must not carry Z"
    _page_z_blocks(page)
    (group,) = page.findall("group")
    # Each stroke of the bracket has its own Z; nothing is inherited.
    assert len(group) == 6
    assert all(child.tag == "arrow" and child.get("Z") for child in group)


def _crossing_lines_state():
    # Two levels cross both vertical strokes of the square bracket.
    return _state(
        arrows=[
            {"kind": "line", "start": [100.0, 30.0], "end": [180.0, 30.0]},
            {"kind": "line", "start": [100.0, 50.0], "end": [180.0, 50.0]},
        ],
        ts_brackets=[_bracket("square_pair", _SQUARE)],
    )


def test_bracket_strokes_sit_between_overlapping_lines():
    from PyQt6.QtCore import QPointF, Qt

    with offscreen_document_scene(
        _crossing_lines_state(), command="test-cdxml"
    ) as context:
        lines = {
            context.arrows.record(it).start[1]: it
            for it in context.state.arrow_items()
            if it is not None
        }
        below, above = lines[30.0], lines[50.0]
        bracket = _bracket_item(context, "square_pair")
        # Above the atom labels (z 3), so no fragment window is involved.
        for item, z in ((below, 4.0), (bracket, 5.0), (above, 6.0)):
            item.setZValue(z)
        order = list(context.scene.items(Qt.SortOrder.AscendingOrder))
        ranks = [order.index(it) for it in (below, bracket, above)]
        assert ranks == sorted(ranks)
        path = bracket.path()
        for y in (30.0, 50.0):
            hits = [
                x / 4
                for x in range(400, 721)
                if path.contains(bracket.mapFromScene(QPointF(x / 4, y)))
            ]
            assert hits, f"line y={y} must cross a painted stroke"
        xml_bytes, plan = _export(context)
    page = ET.fromstring(xml_bytes).find("page")
    by_box = {_line_endpoints(g): g for g in page if g.tag == "arrow"}
    z_below = _z(by_box[_bbox(100.0, 30.0, 180.0, 30.0, plan)])
    z_above = _z(by_box[_bbox(100.0, 50.0, 180.0, 50.0, plan)])
    (group,) = page.findall("group")
    strokes = [_z(g) for g in group]
    assert len(strokes) == 6
    assert z_below < min(strokes) <= max(strokes) < z_above


def test_mock_diagram_ids_unique_and_deterministic(tmp_path):
    first, _ = _export_twice(tmp_path)
    root = ET.fromstring(first)
    ids = [el.get("id") for el in root.iter() if el.get("id") is not None]
    assert len(ids) == len(set(ids))
    font_ids = {f.get("id") for f in root.iter("font")}
    for s_el in root.iter("s"):
        assert s_el.get("font") in font_ids
    n_colors = len(root.find("colortable").findall("color"))
    for el in root.iter():
        ref = el.get("color")
        if ref is not None:
            assert 2 <= int(ref) <= n_colors + 1


def _export_twice(tmp_path):
    outputs = []
    for _ in range(2):
        state = _mock_diagram(dagger=False)
        with offscreen_document_scene(state, command="test-cdxml") as context:
            outputs.append(_export(context)[0])
    assert outputs[0] == outputs[1]
    return outputs


def test_mock_diagram_source_unchanged(tmp_path):
    from chemvas.bootstrap import document_render as cli

    state = _mock_diagram()
    before_state = json.dumps(state, sort_keys=True)
    source = tmp_path / "mock-source.cdxml"
    write_document(source, state, CANVAS_FILE_VERSION)
    before_bytes = source.read_bytes()
    output = tmp_path / "mock.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item = _bracket_item(context, "double_dagger")
        _text, font = item.export_glyph_run()
        glyph_ok = _primary_font_has(font, "\u2021")
    if glyph_ok:
        cli._render_document(
            source, output=output, background="white", dpi=300, width_mm=170.0
        )
        assert output.exists()
    assert source.read_bytes() == before_bytes
    assert json.dumps(state, sort_keys=True) == before_state


# ── Refused objects: no output, existing destination kept ─────────────


@pytest.mark.parametrize(
    "kind",
    ["parentheses_pair", "parenthesis_left", "braces_pair", "brace_left"],
)
def test_refuse_curved_brackets(tmp_path, kind):
    state = _state(ts_brackets=[_bracket(kind, _SQUARE)])
    _assert_refused_and_kept(tmp_path, state, "curves")


@pytest.mark.parametrize("kind", ["line_wavy"])
def test_refuse_wavy_lines(tmp_path, kind):
    line = {"kind": kind, "start": [40.0, 100.0], "end": [80.0, 100.0]}
    state = _state(arrows=[line])
    _assert_refused_and_kept(tmp_path, state, "no proved")


def test_refuse_dashed_connector_with_label(tmp_path):
    state = _state(
        arrows=[
            {
                "kind": "line_dashed",
                "start": [80.0, 100.0],
                "end": [120.0, 40.0],
                "labels": {"above": "x"},
            }
        ]
    )
    _assert_refused_and_kept(tmp_path, state, "label")


# ── Bracket around a structure: painted strokes decide contact ────────
# A wide bracket (left 100, right 200, hook 11 at bond length 20) whose
# bounding rect covers the molecule while its strokes may or may not touch it.
_AROUND = {"left": 100.0, "top": 0.0, "right": 200.0, "bottom": 80.0}


def _between_fragment_layers(context):
    """Put the bracket between the molecule's bonds and atom labels in z."""
    from PyQt6.QtCore import Qt

    item = _bracket_item(context, "square_pair")
    item.setZValue(1.0)
    order = list(context.scene.items(Qt.SortOrder.AscendingOrder))
    ranks = {id(it): i for i, it in enumerate(order)}
    fragment = [it for it in order if it.data(0) in ("atom", "bond")]
    fragment_ranks = [ranks[id(it)] for it in fragment]
    assert min(fragment_ranks) < ranks[id(item)] < max(fragment_ranks)
    return item, fragment


def _rect_tuple(rect):
    return (rect.left(), rect.top(), rect.right(), rect.bottom())


def _near_edge(x, y, rect, margin):
    left, top, right, bottom = rect
    inside_x = left - margin <= x <= right + margin
    if not (inside_x and top - margin <= y <= bottom + margin):
        return False
    edges = (abs(x - left), abs(x - right), abs(y - top), abs(y - bottom))
    return min(edges) < margin


def test_bracket_around_structure_exports_when_strokes_clear():
    from chemvas.ui.export.export_cdxml import (
        _closed_rects_touch,
        _ts_bracket_contact_rects,
    )

    state = _state(
        atoms={0: Atom("N", 140.0, 40.0), 1: Atom("O", 160.0, 40.0)},
        ts_brackets=[_bracket("square_pair", _AROUND)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item, fragment = _between_fragment_layers(context)
        bounds = item.sceneBoundingRect()
        # The bounding-rect rule alone would refuse this picture.
        assert any(bounds.intersects(it.sceneBoundingRect()) for it in fragment)
        reach = _ts_bracket_contact_rects(context, item)
        assert reach is not None
        for it in fragment:
            frag = _rect_tuple(it.sceneBoundingRect())
            assert not any(_closed_rects_touch(rect, frag) for rect in reach)
        xml_bytes, _plan = _export(context)
    page = ET.fromstring(xml_bytes).find("page")
    assert sorted(child.tag for child in page) == ["fragment", "group"]
    group, fragment = page.find("group"), page.find("fragment")
    assert len(list(group)) == 6
    # The molecule is written as one fragment above the bracket. Its bonds sat
    # below the bracket in the scene, but no painted area changes order
    # because the bracket's reach is clear of every atom and bond item.
    assert max(_z(g) for g in group) < min(_z(el) for el in _z_leaves(fragment))


def test_bracket_around_structure_keeps_decision_at_other_scales():
    state = _state(
        atoms={0: Atom("N", 140.0, 40.0), 1: Atom("O", 160.0, 40.0)},
        ts_brackets=[_bracket("square_pair", _AROUND)],
    )
    outputs = []
    for width_mm in (170.0, 85.0):
        with offscreen_document_scene(state, command="test-cdxml") as context:
            _between_fragment_layers(context)
            service = FigureExportService(context)
            items, plan = service._resolve_figure_export(
                scope="sheet",
                selection=None,
                sizing="custom",
                target_width_mm=width_mm,
            )
            preflight_cdxml(context, items, plan)
            page = ET.fromstring(serialize_cdxml(context, items, plan)).find("page")
        outputs.append([(el.tag, el.get("Z")) for el in _z_leaves(page)])
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    ("bracket_z", "below"),
    [
        pytest.param(1.0, True, id="between-bonds-and-labels"),
        pytest.param(5.0, False, id="above-labels"),
    ],
)
def test_enclosing_bracket_and_fragment_leaves_follow_the_policy(bracket_z, below):
    from PyQt6.QtCore import Qt

    state = _state(
        atoms={0: Atom("N", 140.0, 40.0), 1: Atom("O", 160.0, 40.0)},
        ts_brackets=[_bracket("square_pair", _AROUND)],
    )
    with offscreen_document_scene(state, command="test-cdxml") as context:
        _bracket_item(context, "square_pair").setZValue(bracket_z)
        painted = []
        for item in context.scene.items(Qt.SortOrder.AscendingOrder):
            key = (item.data(0), item.data(1))
            if key[0] in ("atom", "bond") and key not in painted:
                painted.append(key)
        xml_bytes, _plan = _export(context)
    page = ET.fromstring(xml_bytes).find("page")
    group, fragment = page.find("group"), page.find("fragment")
    strokes = [_z(g) for g in group]
    molecule = [_z(el) for el in _z_leaves(fragment)]
    if below:
        # Policy: the fragment stays one page object at its top atom rank.
        assert max(strokes) < min(molecule)
    else:
        assert max(molecule) < min(strokes)
    # Inside the fragment each atom and bond follows its scene paint order,
    # a node directly followed by its label.
    nodes, bonds = fragment.findall("n"), fragment.findall("b")
    element_of = {("atom", 0): nodes[0], ("atom", 1): nodes[1], ("bond", 0): bonds[0]}
    expected = [leaf for key in painted for leaf in _z_leaves(element_of[key])]
    assert sorted(_z_leaves(fragment), key=_z) == expected
    assert painted[0] == ("bond", 0)
    for node in nodes:
        (label,) = node.findall("t")
        assert _z(label) == _z(node) + 1


def test_refuse_bond_split_by_an_atom_in_z_order():
    state = _state()
    model = MoleculeModel(
        atoms={0: Atom("C", 300.0, 200.0), 1: Atom("C", 320.0, 200.0)},
        bonds=[Bond(0, 1, order=2, style="double_center")],
    )
    state["model"] = serialize_model_state(model)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        parts = [it for it in context.scene.items() if it.data(0) == "bond"]
        assert len(parts) >= 2
        # One bond line above the atoms (z 3), the other below them.
        parts[0].setZValue(4.0)
        with pytest.raises(CdxmlUnsupportedObjectError, match="split"):
            _export(context)


def test_z_overflow_refuses_before_output_and_keeps_destination(tmp_path, monkeypatch):
    from chemvas.ui.export import export_cdxml

    state = _mock_diagram(dagger=False)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        xml_bytes, _plan = _export(context)
    count = len(_z_leaves(ET.fromstring(xml_bytes).find("page")))
    assert export_cdxml._Z_MAX == 32767
    monkeypatch.setattr(export_cdxml, "_Z_MAX", count)
    with offscreen_document_scene(state, command="test-cdxml") as context:
        assert _export(context)[0] == xml_bytes
    monkeypatch.setattr(export_cdxml, "_Z_MAX", count - 1)
    _assert_refused_and_kept(tmp_path, state, "INT16")


@pytest.mark.parametrize(
    "atoms",
    [
        pytest.param(
            {0: Atom("N", 90.0, 40.0), 1: Atom("O", 130.0, 40.0)},
            id="bond-crosses-stroke",
        ),
        pytest.param(
            {0: Atom("N", 100.0, 40.0), 1: Atom("O", 140.0, 40.0)},
            id="label-on-stroke",
        ),
    ],
)
def test_refuse_bracket_stroke_over_structure(atoms):
    state = _state(atoms=atoms, ts_brackets=[_bracket("square_pair", _AROUND)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        bracket, _ = _between_fragment_layers(context)
        if context.model.atoms[0].x == 100.0:
            # Contacting label below the bracket; the other atom keeps the
            # fragment anchor above it, producing an actual order reversal.
            labels = [
                item
                for item in context.scene.items()
                if item.data(0) == "atom" and item.data(1) == 0
            ]
            for item in labels:
                item.setZValue(bracket.zValue() - 0.5)
        with pytest.raises(CdxmlUnsupportedObjectError, match="interleave"):
            _export(context)


@pytest.mark.parametrize("kind", ["square_pair", "square_left"])
def test_bracket_stroke_rects_match_the_painted_path(kind):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.export.export_cdxml import _square_bracket_stroke_rects

    state = _state(ts_brackets=[_bracket(kind, _AROUND)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item = _bracket_item(context, kind)
        style = context.renderer.style
        commands = bracket_path_commands(
            (100.0, 0.0, 100.0, 80.0), kind, style.bond_length_px
        )
        width = bracket_stroke_width(style.bond_line_width)
        painted = _square_bracket_stroke_rects(commands, width, consumer_caps=False)
        path = item.path()
        span = (
            min(r[0] for r in painted),
            min(r[1] for r in painted),
            max(r[2] for r in painted),
            max(r[3] for r in painted),
        )
        assert span == pytest.approx(_rect_tuple(item.sceneBoundingRect()), abs=1e-6)
        step, margin = width / 8, width / 64
        checked = 0
        for _cmd, (x0, y0) in commands:
            for i in range(-16, 17):
                for j in range(-16, 17):
                    x, y = x0 + (i + 1 / 3) * step, y0 + (j + 1 / 3) * step
                    if any(_near_edge(x, y, r, margin) for r in painted):
                        continue
                    inside = any(
                        r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in painted
                    )
                    assert path.contains(QPointF(x, y)) == inside, (x, y)
                    checked += 1
    assert checked > 1000


def test_bracket_contact_boundaries_for_width_cap_and_join():
    from PyQt6.QtCore import QRectF

    from chemvas.ui.export.export_cdxml import (
        _item_touches,
        _ts_bracket_contact_rects,
    )

    state = _state(ts_brackets=[_bracket("square_left", _AROUND)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item = _bracket_item(context, "square_left")
        style = context.renderer.style
        half = bracket_stroke_width(style.bond_line_width) / 2
        commands = bracket_path_commands(
            (100.0, 0.0, 100.0, 80.0), "square_left", style.bond_length_px
        )
        inner, top = commands[0][1]
        outer = commands[1][1][0]
        reach = _ts_bracket_contact_rects(context, item)
        assert reach is not None
        bounds = item.sceneBoundingRect()

        def touches(left, upper, right, lower):
            frag = QRectF(left, upper, right - left, lower - upper)
            return _item_touches(bounds, reach, frag)

        # Stroke width: touching the stroke edge is contact, a gap is not.
        assert touches(80.0, 30.0, outer - half, 50.0)
        assert not touches(80.0, 30.0, outer - half - 0.25, 50.0)
        # Free end: the scene's flat cap stops at the inner x; a consumer
        # square cap may reach half the width further, so that zone refuses.
        assert touches(inner + 0.25 * half, top - 5.0, inner + 20.0, top + 5.0)
        assert touches(inner + half, top - 5.0, inner + 20.0, top + 5.0)
        assert not touches(inner + half + 0.25, top - 5.0, inner + 20.0, top + 5.0)
        # Mitre join: the outer corner square is painted.
        assert touches(outer - 10.0, top - 10.0, outer - 0.8 * half, top - 0.8 * half)
        assert not touches(
            outer - 10.0, top - 10.0, outer - half - 0.1, top - half - 0.1
        )


def test_bracket_contact_follows_uniform_transform_only():
    from PyQt6.QtGui import QTransform

    from chemvas.ui.export.export_cdxml import (
        _ts_bracket_contact_rects,
        _uniform_scale_offset,
    )

    uniform = QTransform(2.0, 0.0, 0.0, 2.0, 5.0, 3.0)
    assert _uniform_scale_offset(uniform) == (2.0, 5.0, 3.0)
    for refused in (
        QTransform(2.0, 0.0, 0.0, 3.0, 0.0, 0.0),
        QTransform(1.0, 0.5, 0.0, 1.0, 0.0, 0.0),
        QTransform(-1.0, 0.0, 0.0, -1.0, 0.0, 0.0),
        QTransform(1.0, 0.0, 0.001, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        QTransform().rotate(30.0),
    ):
        assert _uniform_scale_offset(refused) is None
    state = _state(ts_brackets=[_bracket("square_pair", _AROUND)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item = _bracket_item(context, "square_pair")
        before = _ts_bracket_contact_rects(context, item)
        item.setScale(2.0)
        item.setPos(5.0, 3.0)
        after = _ts_bracket_contact_rects(context, item)
        item.setRotation(30.0)
        rotated = _ts_bracket_contact_rects(context, item)
    assert before is not None
    assert after == [
        (2 * a + 5, 2 * b + 3, 2 * c + 5, 2 * d + 3) for a, b, c, d in before
    ]
    assert rotated is None


def test_dagger_bracket_keeps_bounding_rect_rule():
    from chemvas.ui.export.export_cdxml import _ts_bracket_contact_rects

    with offscreen_document_scene(_mock_diagram(), command="test-cdxml") as context:
        item = _bracket_item(context, "double_dagger")
        assert _ts_bracket_contact_rects(context, item) is None


def test_refuse_moved_bracket_item(tmp_path):
    state = _state(ts_brackets=[_bracket("square_pair", _SQUARE)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        _bracket_item(context, "square_pair").setPos(5.0, 0.0)
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="moved"):
            preflight_cdxml(context, items, plan)


def test_refuse_bracket_item_not_painting_its_record(tmp_path):
    from PyQt6.QtGui import QPainterPath

    state = _state(ts_brackets=[_bracket("square_pair", _SQUARE)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        path = QPainterPath()
        path.addRect(110.0, 20.0, 60.0, 40.0)
        _bracket_item(context, "square_pair").setPath(path)
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="path of its record"):
            preflight_cdxml(context, items, plan)


def test_bracket_path_check_draws_the_record_through_its_single_painter(
    monkeypatch,
):
    """The exporter gets a record's path only from ``annotations.records``.

    The painter draws onto a detached item, one call per exported bracket,
    and the scene items keep their path, position, pen, brush and role.
    """
    from chemvas.ui.annotations import records

    calls = []
    painter = records.render_ts_bracket_item

    def spy(context, item, ts_bracket):
        calls.append((item, ts_bracket))
        painter(context, item, ts_bracket)

    with offscreen_document_scene(_mock_diagram(), command="test-cdxml") as context:
        scene_items = list(context.state.ts_bracket_items())
        monkeypatch.setattr(records, "render_ts_bracket_item", spy)

        def look(item):
            return (
                item.path(),
                item.pos(),
                item.pen().style(),
                item.brush().color().name(),
                item.data(0),
            )

        before = [look(item) for item in scene_items]
        _text, font = _bracket_item(context, "double_dagger").export_glyph_run()
        has_dagger = _primary_font_has(font, BRACKET_SYMBOLS["double_dagger"])
        if has_dagger:
            _export(context)
        else:
            # The path is checked before the glyph, so the dagger's record
            # is still drawn through the painter before the font refuses.
            with pytest.raises(CdxmlUnsupportedObjectError, match="glyph"):
                _export(context)
        after = [look(item) for item in scene_items]
        recorded = [
            context.state.ts_bracket_state.records[item.data(3)] for item in scene_items
        ]
    kinds = {record.bracket_kind for _, record in calls}
    assert after == before
    assert all(item not in scene_items and item.scene() is None for item, _ in calls)
    assert all(record in recorded for _, record in calls)
    assert "double_dagger" in kinds
    if has_dagger:
        assert kinds == {"square_pair", "double_dagger"}
        assert len(calls) == len(scene_items)


@pytest.mark.parametrize("kind", ["square_pair", "square_left", "double_dagger"])
def test_record_painter_path_matches_the_painted_geometry(kind):
    """The owner path is the geometry the scene paints and the export writes.

    It equals the scene item's own path and the decoration path of the
    record's ordered bounds, so the check compares the same geometry as
    before. The stroke keeps its width, flat cap and mitre join through
    ``test_bracket_stroke_rects_match_the_painted_path``.
    """
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QGraphicsPathItem

    from chemvas.ui.annotations.records import render_ts_bracket_item

    rect = _DAGGER if kind in BRACKET_SYMBOLS else _AROUND
    state = _state(ts_brackets=[_bracket(kind, rect)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        item = _bracket_item(context, kind)
        record = context.state.ts_bracket_state.records[item.data(3)]
        detached = QGraphicsPathItem()
        render_ts_bracket_item(context, detached, record)
        bounds = QRectF(
            record.left,
            record.top,
            record.right - record.left,
            record.bottom - record.top,
        )
        direct = context.decorations.ts_bracket_path(bounds, kind)
        assert detached.path() == item.path()
        assert detached.path() == direct
        assert detached.pos() == item.pos()


def test_refuse_translucent_bracket(tmp_path):
    state = _state(ts_brackets=[_bracket("square_pair", _SQUARE)])
    with offscreen_document_scene(state, command="test-cdxml") as context:
        _bracket_item(context, "square_pair").setOpacity(0.5)
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="translucent"):
            preflight_cdxml(context, items, plan)


# ── Still fail closed: atom-bound marks and untyped Ar/H labels ──────


def test_atom_bound_mark_still_refused(tmp_path):
    state = _state(
        atoms={0: Atom("N", 300.0, 200.0), 1: Atom("O", 320.0, 200.0)},
        ts_brackets=[_bracket("square_pair", _SQUARE)],
        charges={0: 1},
    )
    state["marks"] = [
        {
            "kind": "plus",
            "atom_id": 0,
            "text": "+",
            "x": 302.0,
            "y": 198.0,
            "dx": 2.0,
            "dy": -2.0,
            "_auto_position": True,
        }
    ]
    _assert_refused_and_kept(tmp_path, state, "mark")


@pytest.mark.parametrize("label", ["Ar", "H\u1d43"])
def test_literal_ar_graphics_and_untyped_identifier_h(tmp_path, label):
    state = _state(
        atoms={0: Atom("O", 300.0, 200.0), 1: Atom(label, 320.0, 200.0)},
        ts_brackets=[_bracket("square_pair", _SQUARE)],
        arrows=[_CONNECTORS[0]],
    )
    _assert_refused_and_kept(tmp_path, state, "binding|ambiguous|typed")


def test_refuse_dashed_line_over_bonded_fragment(tmp_path):
    state = _state(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 20.0, 0.0)},
        arrows=[{"kind": "line_dashed", "start": [0.0, 0.0], "end": [20.0, 0.0]}],
    )
    _assert_refused_and_kept(tmp_path, state, "interleave")


@pytest.mark.parametrize("length", [15.0, 30.0])
@pytest.mark.parametrize("end", [[80.0, 100.0], [40.0, 140.0], [10.0, 130.0]])
def test_bold_annotation_uses_common_flat_stroke(length, end):
    state = _state(
        arrows=[dict(kind="line_bold", start=[40.0, 100.0], end=end, color="#316699")]
    )
    state["settings"]["bond_length_px"] = length
    with offscreen_document_scene(state, command="bold-annotation") as context:
        content, plan = _export(context)
        root = ET.fromstring(content)
        native = root.find("./page/arrow")
        assert native is not None
        assert native.get("LineType") == "Solid"
        assert native.get("ArrowheadHead") is None
        scale = plan.out_w_pt / plan.source_w
        assert float(native.get("LineWidth")) == pytest.approx(
            context.renderer.bold_bond_pen().widthF() * scale, abs=1e-9
        )
        assert [float(x) for x in _line_endpoints(native).split()] == pytest.approx(
            [
                (40 - plan.source_x) * scale,
                (100 - plan.source_y) * scale,
                (end[0] - plan.source_x) * scale,
                (end[1] - plan.source_y) * scale,
            ]
        )
        assert native.get("color") is not None


def test_bold_annotation_mirror_still_refuses(tmp_path):
    state = _state(
        arrows=[dict(kind="line_bold", start=[0, 0], end=[20, 0], mirrored=True)]
    )
    with pytest.raises(ValueError):
        with offscreen_document_scene(state, command="invalid-mirrored-line"):
            pytest.fail("invalid line record was accepted")
