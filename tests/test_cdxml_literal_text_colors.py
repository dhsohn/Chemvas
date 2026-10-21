"""Literal text colors must survive native default-color elision."""

import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

import pytest

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import Atom, Bond
from chemvas.features.export.cdxml_consumer_validation import (
    _Scene,
    validate_consumer_objects,
)
from tests.document_file_helpers import read_payload
from tests.test_cdxml_export import _export_cdxml, _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")

NATIVE = read_payload(
    (Path(__file__).parent / "fixtures/native_attached_text_colors.json").read_text()
)


@pytest.mark.parametrize("case", NATIVE["cases"])
def test_native_attached_run_color_matches_actual_svg_paint(case):
    root = ET.fromstring(case["native_xml"])
    run = root.find(".//objecttag/t/s")
    rgb = _Scene(root).color(run)
    actual = "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)
    assert actual == case["native_svg_fill"]


@pytest.mark.parametrize("kind", ["plus", "minus"])
@pytest.mark.parametrize("mark_color", [None, "#000000", "#ffffff", "#ff0000"])
def test_attached_mark_retains_painted_color_under_colored_owner(kind, mark_color):
    mark = {"kind": kind, "atom_id": 0, "dx": 0, "dy": 35, "x": 0, "y": 35}
    if mark_color is not None:
        mark["color"] = mark_color
    state = _simple_state(
        atoms={0: Atom("P", 0, 0, color="#252930"), 1: Atom("C", 20, 0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"formal_charge": 1 if kind == "plus" else -1}},
        marks=[mark],
    )
    before = deepcopy(state)
    with offscreen_document_scene(state, command="literal-color-test") as context:
        item = next(i for i in context.scene.items() if i.data(0) == "mark")
        painted = item.defaultTextColor().getRgb()[:3]
        assert item.data(1)["atom_id"] == 0
    data, _ = _export_cdxml(state)
    assert state == before
    root = ET.fromstring(data)
    tag = root.find('.//objecttag[@Name="chemvasMark"]')
    assert tag.get("PositioningType") == "offset"
    run = tag.find("t/s")
    scene = _Scene(root)
    assert tuple(round(c * 255) for c in scene.color(run)) == painted
    # Native save elides palette default index 3. It retains absolute black 0,
    # absolute white 1 and custom palette entries (independent native fixture).
    if painted in [(0, 0, 0), (255, 255, 255)]:
        assert run.get("color") == ("0" if painted == (0, 0, 0) else "1")
    else:
        assert int(run.get("color")) >= 4
    owner = scene.parents[tag]
    assert tuple(round(c * 255) for c in scene.color(owner)) == (37, 41, 48)
    charged = owner.find("fragment/n[@Charge]")
    assert charged.get("Charge") == ("1" if kind == "plus" else "-1")


def test_attached_text_default_foreground_has_its_own_color_scope():
    root = ET.fromstring(
        '<CDXML><colortable><color r="1" g="1" b="1"/>'
        '<color r="0" g="0" b="0"/><color r="1" g="0" b="0"/>'
        '</colortable><page id="1"><fragment id="2"><n id="3" color="4">'
        '<objecttag Name="chemvasMark"><t><s color="0">+</s></t></objecttag>'
        "</n></fragment></page></CDXML>"
    )
    run = root.find(".//s")
    assert _Scene(root).color(run) == (0, 0, 0)
    # Native SVG retains black after eliding the default foreground run color.
    # An explicit changed color must still be observable to the strict guard.
    del run.attrib["color"]
    assert _Scene(root).color(run) == (0, 0, 0)
    run.set("color", "4")
    assert _Scene(root).color(run) == (1, 0, 0)


@pytest.mark.parametrize("native_color", [None, "0", "3", "1", "4"])
def test_reference_guard_accepts_default_black_but_refuses_recoloring(native_color):
    state = _simple_state(
        atoms={0: Atom("P", 0, 0, color="#252930"), 1: Atom("C", 20, 0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"formal_charge": 1}},
        marks=[{"kind": "plus", "atom_id": 0, "dx": 0, "dy": 35, "x": 0, "y": 35}],
    )
    data, _ = _export_cdxml(state)
    root = ET.fromstring(data)
    native = deepcopy(root)
    run = native.find('.//objecttag[@Name="chemvasMark"]/t/s')
    if native_color is None:
        del run.attrib["color"]
    else:
        run.set("color", native_color)
    fonts = {f.get("name"): f.get("name") for f in root.findall("fonttable/font")}
    if native_color in [None, "0", "3"]:
        validate_consumer_objects(root, native, fonts)
    else:
        with pytest.raises(ValueError, match="changed text color"):
            validate_consumer_objects(root, native, fonts)
