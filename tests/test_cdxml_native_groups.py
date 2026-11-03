"""Native ChemDraw ``<group>`` elements become editor groups and unwrap on ungroup."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.annotations.projections import resolve_projection
from tests.canvas_factory import build_canvas_view


def drawing(*body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CDXML BondLength="20" CaptionFont="3" CaptionSize="10">'
        '<fonttable><font id="3" name="Arial"/></fonttable>'
        '<page id="1" BoundingBox="0 0 400 300">'
        f"{''.join(body)}"
        "</page></CDXML>"
    ).encode()


def molecule_and_caption_group() -> bytes:
    return drawing(
        '<group id="2">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Caption</s>',
        "</t>",
        "</group>",
    )


def molecule_and_black_rectangle_group() -> bytes:
    return drawing(
        '<group id="2">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<graphic id="8" GraphicType="Rectangle" RectangleType="Plain" '
        'BoundingBox="20 80 60 120"/>',
        "</group>",
    )


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def test_molecule_and_caption_import_as_editor_group_and_move_together(canvas):
    state = parse_cdxml_document(molecule_and_caption_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    assert state["cdxml_source"]["baseline"]["groups"] == state["groups"]

    canvas.services.canvas_document_session_service.restore_state(deepcopy(state))
    group = next(iter(canvas.runtime_state.group_state.groups.values()))
    assert group.atom_ids == {0, 1}
    note_id = group.item_ids[0]
    before_atoms = {
        atom_id: (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y)
        for atom_id in (0, 1)
    }
    before_note = scene_note_xy(canvas, note_id)

    canvas.services.selection.restore_ids(set(), set())
    resolve_projection(canvas, note_id).setSelected(True)
    canvas.services.selection.expand_selection_to_groups()
    canvas.services.scene_transform_controller.translate_selected_items(5, -3)

    for atom_id, (x, y) in before_atoms.items():
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            x + 5,
            y - 3,
        )
    assert scene_note_xy(canvas, note_id) == (before_note[0] + 5, before_note[1] - 3)


def scene_note_xy(canvas, record_id: int) -> tuple[float, float]:
    note = resolve_projection(canvas, record_id)
    return (note.pos().x(), note.pos().y())


def test_nested_group_creates_no_editor_group():
    state = parse_cdxml_document(
        drawing(
            '<group id="2">',
            '<group id="3">',
            '<fragment id="4">',
            '<n id="5" p="40 40" Element="6"/>',
            '<n id="6" p="60 40" Element="6"/>',
            '<b id="7" B="5" E="6"/>',
            "</fragment>",
            '<t id="8" p="40 80" BoundingBox="40 70 100 81">',
            '<s font="3" size="10">Inner</s>',
            "</t>",
            "</group>",
            "</group>",
            '<group id="9">',
            '<fragment id="10">',
            '<n id="11" p="150 60" Element="6"/>',
            '<n id="12" p="170 60" Element="6"/>',
            '<b id="13" B="11" E="12"/>',
            "</fragment>",
            '<t id="14" p="150 100" BoundingBox="150 90 210 101">',
            '<s font="3" size="10">Sibling</s>',
            "</t>",
            "</group>",
        )
    ).state
    # Sibling page-level group maps; nested wrapper does not add another.
    assert state["groups"] == [{"atoms": [2, 3], "items": [["notes", 1]]}]


def test_group_with_unimportable_object_creates_no_editor_group():
    state = parse_cdxml_document(
        drawing(
            '<group id="2">',
            '<fragment id="3">',
            '<n id="4" p="50 60" Element="6"/>',
            '<n id="5" p="70 60" Element="6"/>',
            '<b id="6" B="4" E="5"/>',
            "</fragment>",
            '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
            '<s font="3" size="10">Caption</s>',
            "</t>",
            '<curve id="8"/>',
            "</group>",
            '<group id="9">',
            '<fragment id="10">',
            '<n id="11" p="150 60" Element="6"/>',
            '<n id="12" p="170 60" Element="6"/>',
            '<b id="13" B="11" E="12"/>',
            "</fragment>",
            '<t id="14" p="150 100" BoundingBox="150 90 210 101">',
            '<s font="3" size="10">Sibling</s>',
            "</t>",
            "</group>",
        )
    ).state
    assert state["groups"] == [{"atoms": [2, 3], "items": [["notes", 1]]}]


def test_ungroup_then_save_unwraps_native_group():
    state = parse_cdxml_document(molecule_and_caption_group()).state
    assert state["groups"]
    state = deepcopy(state)
    del state["groups"]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    assert root.find(".//group") is None
    assert root.find('.//fragment[@id="3"]') is not None
    assert root.find('.//t[@id="7"]') is not None
    page_children = [child.tag for child in root.find("page")]
    assert page_children == ["fragment", "t"]

    reopened = parse_cdxml_document(saved).state
    assert "groups" not in reopened


def test_untouched_save_keeps_native_group_byte_identical():
    state = parse_cdxml_document(molecule_and_caption_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    saved = update_native_document(deepcopy(state))
    assert ET.canonicalize(saved.decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )


def test_deleting_one_member_keeps_native_group_wrapper():
    state = parse_cdxml_document(molecule_and_caption_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    state = deepcopy(state)
    state["notes"].pop(0)
    state["cdxml_source"]["items"]["notes"].pop(0)
    state["groups"] = [{"atoms": [0, 1], "items": []}]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    group = root.find(".//group")
    assert group is not None
    assert group.find("fragment") is not None
    assert group.find("t") is None
    assert root.find('.//t[@id="7"]') is None


def test_expanding_imported_group_keeps_native_group_original_children():
    state = parse_cdxml_document(
        drawing(
            '<group id="2">',
            '<fragment id="3">',
            '<n id="4" p="50 60" Element="6"/>',
            '<n id="5" p="70 60" Element="6"/>',
            '<b id="6" B="4" E="5"/>',
            "</fragment>",
            '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
            '<s font="3" size="10">Caption</s>',
            "</t>",
            "</group>",
            '<t id="9" p="200 100" BoundingBox="200 90 260 101">',
            '<s font="3" size="10">Extra</s>',
            "</t>",
        )
    ).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    assert state["cdxml_source"]["items"]["notes"] == ["7", "9"]
    state = deepcopy(state)
    # Expand editor membership with the extra native note; native XML stays a
    # snapshot of the original children only.
    state["groups"] = [{"atoms": [0, 1], "items": [["notes", 0], ["notes", 1]]}]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    group = root.find(".//group")
    assert group is not None
    assert [child.get("id") for child in group] == ["3", "7"]
    page = root.find("page")
    assert page is not None
    assert [child.tag for child in page] == ["group", "t"]
    assert root.find('.//t[@id="9"]') is not None
    assert root.find('.//group/t[@id="9"]') is None


def test_splitting_imported_group_unwraps_native_group():
    state = parse_cdxml_document(molecule_and_caption_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    state = deepcopy(state)
    # Split so no editor group still contains every original native member.
    state["groups"] = [
        {"atoms": [0, 1], "items": []},
        {"atoms": [], "items": [["notes", 0]]},
    ]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    assert root.find(".//group") is None
    assert root.find('.//fragment[@id="3"]') is not None
    assert root.find('.//t[@id="7"]') is not None
    assert [child.tag for child in root.find("page")] == ["fragment", "t"]


def test_molecule_and_black_rectangle_form_editor_group():
    state = parse_cdxml_document(molecule_and_black_rectangle_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["shapes", 0]]}]
    assert state["cdxml_source"]["items"]["shapes"] == ["8"]
    assert state["shapes"][0]["shape_kind"] == "rect"
