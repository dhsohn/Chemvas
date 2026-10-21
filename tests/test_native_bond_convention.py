"""Native paint witnesses and shared preview/edit/export behavior."""

import json
import math
import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import Atom, Bond
from chemvas.features.rendering import style_for_existing_bond_overlay
from chemvas.ui.molecule.bond_preview_renderer import (
    build_bond_preview_items,
    update_bond_preview_items,
)
from tests.document_file_helpers import read_document, write_document
from tests.test_cdxml_export import _export_cdxml, _simple_state


def _ring(style, reverse=False):
    points = [
        (40, 30),
        (80, 30),
        (100, 30 + 20 * math.sqrt(3)),
        (80, 30 + 40 * math.sqrt(3)),
        (40, 30 + 40 * math.sqrt(3)),
        (20, 30 + 20 * math.sqrt(3)),
    ]
    atoms = {i: Atom("C", x, y) for i, (x, y) in enumerate(points)}
    bonds = [
        Bond(i, (i + 1) % 6, 2 if i == 0 else 1, style if i == 0 else "single")
        for i in range(6)
    ]
    if reverse:
        bonds[0].a, bonds[0].b = bonds[0].b, bonds[0].a
    return _simple_state(atoms=atoms, bonds=bonds)


def _paint(item):
    if isinstance(item, QGraphicsPolygonItem):
        return ("polygon", sorted((p.x(), p.y()) for p in item.polygon()))
    line = item.line()
    polygon = item.stroke_polygon() if hasattr(item, "stroke_polygon") else None
    return (
        "line",
        (line.x1(), line.y1(), line.x2(), line.y2()),
        None if polygon is None else sorted((p.x(), p.y()) for p in polygon),
    )


@pytest.mark.parametrize(
    "style,offset,secondary_length",
    [("double", 4.84, 34.4112), ("double_outer", -4.84, 40)],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_product_ring_strips_match_saved_native_witness(
    style, offset, secondary_length, reverse
):
    state = _ring(style, reverse)
    before = deepcopy(state)
    with offscreen_document_scene(state, command="native-convention") as context:
        first, second = context.state.bond_graphics_state.bond_items[0]
        assert first.line().length() == pytest.approx(40)
        assert second.line().length() == pytest.approx(secondary_length, abs=0.0002)
        assert (second.line().y1() + second.line().y2()) / 2 == pytest.approx(
            30 + offset
        )
        # Existing native SVG: primary endface meets the adjacent bond bisector.
        actual = sorted((p.x(), p.y()) for p in first.stroke_polygon())
        expected = sorted(
            [(39.56699, 29.25), (40.43301, 30.75), (79.56699, 30.75), (80.43301, 29.25)]
        )
        for point, witness in zip(actual, expected, strict=True):
            assert point == pytest.approx(witness, abs=0.0002)
        assert first.shape().boundingRect() == first.boundingRect()
    assert state == before
    raw, plan = _export_cdxml(state)
    root = ET.fromstring(raw)
    bond = next(b for b in root.iter("b") if b.get("Order") == "2")
    positive = (offset > 0) != reverse
    assert bond.get("DoublePosition") == ("Left" if positive else "Right")
    assert float(bond.get("BondSpacing")) == pytest.approx(12.1)
    assert float(bond.get("BondSpacing")) * 40 / 100 == pytest.approx(4.84)


@pytest.mark.parametrize("length", [20, 40, 80])
@pytest.mark.parametrize("style", ["double", "double_center", "double_outer"])
def test_native_spacing_uses_actual_bond_length(length, style):
    state = _simple_state(
        atoms={0: Atom("C", 40, 30), 1: Atom("C", 40 + length, 30)},
        bonds=[Bond(0, 1, 2, style)],
    )
    raw, plan = _export_cdxml(state)
    root = ET.fromstring(raw)
    bond = root.find(".//b")
    # Preserve the unrounded 4.84 pt target independently of root BondLength.
    # Native truncates 6.05% to 6.0% at length 80 (4.80 pt after reopen).
    nodes = {n.get("id"): n for n in root.findall(".//n")}
    start, end = [
        tuple(map(float, nodes[bond.get(key)].get("p").split())) for key in ["B", "E"]
    ]
    assert float(bond.get("BondSpacing")) * math.dist(start, end) / 100 == (
        pytest.approx(4.84 * plan.out_w_pt / plan.source_w)
    )


@pytest.mark.parametrize("style", ["bold_in", "bold_out"])
@pytest.mark.parametrize("reverse", [False, True])
def test_both_single_bold_tokens_are_centered_and_native_editable(style, reverse):
    state = _simple_state(
        atoms={0: Atom("C", 0, 0), 1: Atom("C", 40, 0)},
        bonds=[Bond(1 if reverse else 0, 0 if reverse else 1, style=style)],
    )
    with offscreen_document_scene(state, command="native-bold") as context:
        item = context.state.bond_graphics_state.bond_items[0][0]
        ys = [p.y() for p in item.polygon()]
        assert min(ys) == pytest.approx(-1.65)
        assert max(ys) == pytest.approx(1.65)
    raw, _ = _export_cdxml(state)
    root = ET.fromstring(raw)
    assert root.find(".//b").get("Display") == "Bold"
    assert len(root.findall(".//b")) == 1 and not root.findall(".//graphic")
    assert style_for_existing_bond_overlay(style, 1, "bold_in", 1) == (style, 1)


@pytest.mark.parametrize(
    "style,order",
    [
        (x, 2)
        for x in [
            "single",
            "double",
            "double_center",
            "double_outer",
            "bold_in",
            "bold_center",
            "bold_out",
        ]
    ]
    + [(x, 1) for x in ["single", "bold_in", "bold_out"]],
)
@pytest.mark.parametrize("ring", [False, True])
def test_preview_build_and_reuse_follow_committed_geometry(style, order, ring):
    state = (
        _ring(style)
        if ring
        else _simple_state(
            atoms={0: Atom("C", 40, 30), 1: Atom("C", 80, 30)},
            bonds=[Bond(0, 1, order, style)],
        )
    )
    state["model"]["bonds"][0]["order"] = order
    with offscreen_document_scene(state, command="shared-preview") as context:
        renderer = context.bonds

        def options():
            return dict(
                style=style,
                order=order,
                a_id=0,
                b_id=1,
                canvas_renderer=context.renderer,
                bond_renderer=renderer,
            )

        start, end = QPointF(40, 30), QPointF(80, 30)
        preview = build_bond_preview_items(start, end, **options())
        committed = context.state.bond_graphics_state.bond_items[0]
        assert [_paint(i) for i in preview] == [_paint(i) for i in committed]
        identities = list(map(id, preview))
        context.model.atoms[1].x += 7
        end = QPointF(87, 30)
        renderer.update_bond_geometry(0)
        assert update_bond_preview_items(preview, start, end, **options())
        assert list(map(id, preview)) == identities
        assert [_paint(i) for i in preview] == [_paint(i) for i in committed]
        snapshot = [_paint(i) for i in preview]
        assert not update_bond_preview_items(preview[:-1], start, end, **options())
        assert [_paint(i) for i in preview] == snapshot
        assert not update_bond_preview_items(
            [QGraphicsPolygonItem()] * len(preview)
            if order == 2
            else [QGraphicsLineItem()],
            start,
            end,
            **options(),
        )


@pytest.mark.parametrize("version", [7, 8, 9])
@pytest.mark.parametrize("style", ["double", "double_outer", "bold_in", "bold_out"])
def test_supported_old_files_receive_same_rule_without_rewriting(
    tmp_path, version, style
):
    state = _ring(style)
    if style.startswith("bold"):
        state["model"]["bonds"][0]["order"] = 1
    path = tmp_path / f"v{version}.cdxml"
    write_document(path, state, version)
    original = path.read_bytes()
    loaded = read_document(path)
    with offscreen_document_scene(loaded.state, command="old-file-rule") as context:
        paint = [_paint(i) for i in context.state.bond_graphics_state.bond_items[0]]
    with offscreen_document_scene(state, command="current-rule") as context:
        assert paint == [
            _paint(i) for i in context.state.bond_graphics_state.bond_items[0]
        ]
    assert path.read_bytes() == original
    assert loaded.state["model"] == json.loads(json.dumps(state["model"]))
