"""Boat template double bonds draw their inner line inside the folded ring."""

import pytest
from PyQt6.QtWidgets import QGraphicsLineItem

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.bootstrap.document_template import (
    insert_template,
    validate_template_request,
)
from chemvas.features.document_composition import compose_document_state

SOURCE_HASH = "a" * 64

# The template CLI builds a canvas; one application kept for the whole file
# avoids creating and destroying a QApplication for every case.
pytestmark = pytest.mark.usefixtures("qt_application")


def _boat_state():
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
        }
    )
    request = validate_template_request(
        state,
        {
            "format": "chemvas-template-insertion",
            "version": 1,
            "source_sha256": SOURCE_HASH,
            "ring_size": 6,
            "style": "boat",
            "position": [100, 100],
            "anchor": {"kind": "free"},
        },
        source_sha256=SOURCE_HASH,
    )
    candidate, _ = insert_template(state, request)
    return candidate


def _inside(point, polygon):
    x, y = point
    inside = False
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("edge", range(6))
def test_boat_double_bond_inner_line_lies_inside_the_ring(edge, reverse):
    state = _boat_state()
    ring = state["ring_fills"][0]["atom_ids"]
    a, b = ring[edge], ring[(edge + 1) % 6]
    for bond in state["model"]["bonds"]:
        if {bond["a"], bond["b"]} == {a, b}:
            bond["order"] = 2
            # The inner line's side must come from the ring, not from the
            # direction the bond happens to be stored in.
            if reverse:
                bond["a"], bond["b"] = bond["b"], bond["a"]
    with offscreen_canvas(state, command="test-boat-double-bond") as (canvas, _):
        model = canvas.model
        polygon = [(model.atoms[atom_id].x, model.atoms[atom_id].y) for atom_id in ring]
        bond_id = next(
            index
            for index, bond in enumerate(model.bonds)
            if bond is not None and {bond.a, bond.b} == {a, b}
        )
        lines = [
            item.line()
            for item in canvas.runtime_state.bond_graphics_state.bond_items[bond_id]
            if isinstance(item, QGraphicsLineItem)
        ]
        start, end = model.atoms[a], model.atoms[b]

        def offset(line):
            mid_x = (line.x1() + line.x2()) / 2 - start.x
            mid_y = (line.y1() + line.y2()) / 2 - start.y
            return abs((end.x - start.x) * mid_y - (end.y - start.y) * mid_x)

        assert len(lines) == 2
        inner = max(lines, key=offset)
        midpoint = ((inner.x1() + inner.x2()) / 2, (inner.y1() + inner.y2()) / 2)
        assert _inside(midpoint, polygon)
