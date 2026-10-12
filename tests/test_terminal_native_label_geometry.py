"""Terminal double labels share their two stroke axes; model coordinates stay put."""

import math

import pytest

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import Atom, Bond
from chemvas.features.annotations import atom_label_presentation
from tests.test_cdxml_export import _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.mark.parametrize("angle", [0, 45, 90, 135, 180, 225, 270, 315])
@pytest.mark.parametrize("style", ["double", "double_center", "double_outer"])
def test_terminal_label_center_matches_both_painted_axes(angle, style):
    x, y = 40 * math.cos(math.radians(angle)), 40 * math.sin(math.radians(angle))
    state = _simple_state(
        atoms={0: Atom("C", 0, 0), 1: Atom("O", x, y)},
        bonds=[Bond(0, 1, order=2, style=style)],
    )
    with offscreen_document_scene(state, command="terminal-label") as context:
        item = context.state.atom_graphics_state.atom_items[1]
        center = item.mapToScene(item.label_position_center())
        bond = context.model.bonds[0]
        _, (a, b, normal) = context.bonds.geometry_planner._double_segments(
            bond, context.model.atoms[0], context.model.atoms[1], style=style
        )
        nx, ny = normal
        expected = (a[0] + a[2] + b[0] + b[2]) * nx / 4 + (
            a[1] + a[3] + b[1] + b[3]
        ) * ny / 4
        assert center.x() * nx + center.y() * ny == pytest.approx(expected, abs=1e-6)
        assert (center.x() - x) * math.cos(math.radians(angle)) + (
            center.y() - y
        ) * math.sin(math.radians(angle)) == pytest.approx(0, abs=1e-6)
        assert context.model.atoms[1].x == x and context.model.atoms[1].y == y
        if style == "double_center":
            assert (center.x(), center.y()) == pytest.approx((x, y), abs=1e-12)


@pytest.mark.parametrize(
    "vectors",
    [
        [(0, 30)],
        [(0, -30)],
        [(0, 30), (20, 10)],
        [(20, 10), (0, 30)],
        [(0, -30), (20, -10)],
    ],
)
def test_vertical_and_multiple_ar_attachments_keep_native_leading_anchor(vectors):
    atoms = {0: Atom("Ar", 0, 0)}
    bonds = []
    for i, (x, y) in enumerate(vectors, 1):
        atoms[i] = Atom("C", x, y)
        bonds.append(Bond(0, i))
    state = _simple_state(atoms=atoms, bonds=bonds)
    with offscreen_document_scene(state, command="ar-anchor") as context:
        assert atom_label_presentation(context.model, 0, "Ar") == (
            "Ar",
            "A",
            False,
            None,
        )
        assert context.model.atoms[0].element == "Ar"
