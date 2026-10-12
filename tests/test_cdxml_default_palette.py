"""An omitted color table still defines standard background/foreground colors."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.domain.document import Atom, Bond
from chemvas.features.export.cdxml_consumer_validation import (
    _Scene,
    validate_consumer_objects,
)
from tests.test_cdxml_export import _export_cdxml, _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")


def test_review_regression_accepts_omitted_table_and_attached_run_color():
    source = ET.fromstring(
        '<CDXML><fonttable><font id="0" name="Arial"/></fonttable>'
        '<colortable><color r="1" g="1" b="1"/>'
        '<color r="0" g="0" b="0"/></colortable>'
        '<page id="1"><fragment id="2"><n id="3" p="0 0" color="0">'
        '<objecttag Name="chemvasMark"><t p="0 0">'
        '<s font="0" size="8.25" color="0">+</s>'
        "</t></objecttag></n></fragment></page></CDXML>"
    )
    consumer = deepcopy(source)
    consumer.remove(consumer.find("colortable"))
    del consumer.find(".//objecttag/t/s").attrib["color"]
    validate_consumer_objects(source, consumer, {"Arial": "Arial"})


@pytest.mark.parametrize("index,expected", [(0, 0), (1, 1), (2, 1), (3, 0)])
def test_standard_colors_without_a_table(index, expected):
    root = ET.fromstring(f'<CDXML><graphic color="{index}"/></CDXML>')
    assert _Scene(root).color(root[0]) == (float(expected),) * 3


@pytest.mark.parametrize(
    "table,index",
    [
        ("", 4),
        ("<colortable/>", 2),
        ("<colortable/>", 3),
        ('<colortable><color r="1" g="1" b="1"/></colortable>', 3),
    ],
)
def test_undefined_colors_remain_invalid(table, index):
    root = ET.fromstring(f'<CDXML>{table}<graphic color="{index}"/></CDXML>')
    with pytest.raises(ValueError, match="undefined color"):
        _Scene(root).color(root.find("graphic"))


@pytest.mark.parametrize("run_color", [None, "0", "3", "1", "2", "4"])
def test_public_guard_handles_attached_default_without_a_color_table(run_color):
    state = _simple_state(
        atoms={0: Atom("P", 0, 0, color="#000000"), 1: Atom("C", 20, 0)},
        bonds=[Bond(0, 1)],
        atom_annotations={0: {"formal_charge": 1}},
        marks=[{"kind": "plus", "atom_id": 0, "dx": 0, "dy": 35, "x": 0, "y": 35}],
    )
    data, _ = _export_cdxml(state)
    source = ET.fromstring(data)
    native = deepcopy(source)
    native.remove(native.find("colortable"))
    tag = native.find('.//objecttag[@Name="chemvasMark"]')
    parent = {child: owner for owner in native.iter() for child in owner}
    parent[tag].set("color", "0")
    run = tag.find("t/s")
    if run_color is None:
        del run.attrib["color"]
    else:
        run.set("color", run_color)
    fonts = {f.get("name"): f.get("name") for f in source.findall("fonttable/font")}
    if run_color in [None, "0", "3"]:
        validate_consumer_objects(source, native, fonts)
    else:
        error = "undefined color" if run_color == "4" else "changed text color"
        with pytest.raises(ValueError, match=error):
            validate_consumer_objects(source, native, fonts)
