"""Native ChemDraw ``<group>`` elements become editor groups and unwrap on ungroup."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document.cdxml_source import validate_cdxml_source
from chemvas.features.cdxml_document import embed_document, parse_cdxml_document
from chemvas.features.cdxml_native_groups import (
    INHERITED_STYLE_KEYS,
    sync_native_groups_on_save,
)
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.annotations.projections import resolve_projection
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.export.cdxml_document_writer import save_cdxml_document
from chemvas.ui.export.cdxml_native_text import write_native_caption
from chemvas.ui.scene.scene_group_operations import ungroup_selection_for
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


def molecule_and_filled_shape_group() -> bytes:
    return drawing(
        '<group id="2">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<graphic id="8" GraphicType="Rectangle" RectangleType="Filled" '
        'LineWidth="0" BoundingBox="20 80 60 120"/>',
        "</group>",
    )


def molecule_and_outlined_rectangle_group() -> bytes:
    return drawing(
        '<group id="2">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<graphic id="8" GraphicType="Rectangle" RectangleType="Plain" '
        'color="0" LineWidth="2" BoundingBox="20 80 60 120"/>',
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


def test_molecule_and_filled_shape_form_editor_group():
    state = parse_cdxml_document(molecule_and_filled_shape_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["shapes", 0]]}]
    assert state["cdxml_source"]["items"]["shapes"] == ["8"]
    assert state["shapes"][0]["shape_kind"] == "rect"


def test_outlined_rectangle_and_molecule_move_ungroup_save_and_reopen(canvas):
    state = parse_cdxml_document(molecule_and_outlined_rectangle_group()).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["shapes", 0]]}]
    outlined = state["shapes"][0]
    assert outlined["stroke_style"] == "solid"
    assert outlined.get("fill") is None

    canvas.services.canvas_document_session_service.restore_state(deepcopy(state))
    group = next(iter(canvas.runtime_state.group_state.groups.values()))
    assert group.atom_ids == {0, 1}
    assert len(group.item_ids) == 1
    session = canvas.services.canvas_document_session_service
    before_atoms = {
        atom_id: (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y)
        for atom_id in (0, 1)
    }
    before_shape = dict(session.snapshot_state()["shapes"][0])

    canvas.scene().clearSelection()
    visible_atom_item_for(canvas, 0).setSelected(True)
    canvas.services.selection.expand_selection_to_groups()
    assert canvas.services.scene_transform_controller.translate_selected_items(12, -8)

    for atom_id, (x, y) in before_atoms.items():
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            x + 12,
            y - 8,
        )
    moved_shape = session.snapshot_state()["shapes"][0]
    assert moved_shape["left"] == pytest.approx(before_shape["left"] + 12)
    assert moved_shape["top"] == pytest.approx(before_shape["top"] - 8)

    assert ungroup_selection_for(canvas)
    ungrouped = session.snapshot_state()
    assert "groups" not in ungrouped

    saved = update_native_document(ungrouped)
    root = ET.fromstring(saved)
    assert root.find(".//group") is None
    assert root.find('.//fragment[@id="3"]') is not None
    graphic = root.find('.//graphic[@id="8"]')
    assert graphic is not None
    assert graphic.get("RectangleType") == "Plain"
    assert graphic.get("LineWidth") == "2"

    reopened = parse_cdxml_document(saved).state
    assert "groups" not in reopened
    assert reopened["cdxml_source"]["items"]["shapes"] == ["8"]
    assert reopened["shapes"][0]["stroke_style"] == "solid"
    assert reopened["shapes"][0]["left"] == moved_shape["left"]


def test_group_mapping_adds_no_persisted_source_field():
    state = parse_cdxml_document(molecule_and_caption_group()).state
    source = state["cdxml_source"]
    assert set(source) == {
        "xml",
        "offset",
        "atoms",
        "bonds",
        "items",
        "baseline",
        "baseline_items",
    }
    validate_cdxml_source(source, state)
    source["native_group_ids"] = ["2"]
    with pytest.raises(ValueError, match="Invalid CDXML source fields"):
        validate_cdxml_source(source, state)


def test_ungroup_save_rejects_step_reference_to_group_id():
    payload = drawing(
        '<group id="20">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Caption</s>',
        "</t>",
        "</group>",
        '<arrow id="15" Head3D="200 80 0" Tail3D="150 80 0" ArrowheadHead="Full"/>',
        '<scheme><step id="17" ReactionStepReactants="20" ReactionStepArrows="15"/></scheme>',
    )
    state = parse_cdxml_document(payload).state
    assert state["groups"]
    state = deepcopy(state)
    del state["groups"]
    before = deepcopy(state)
    with pytest.raises(ValueError, match=r"Ungrouping .*step\.ReactionStepReactants"):
        update_native_document(state)
    assert state == before


def test_ungroup_save_preserves_inherited_group_color(tmp_path):
    fixture = (
        Path(__file__).resolve().parent / "fixtures" / "cdxml-interop-colors.cdxml"
    )
    state = parse_cdxml_document(fixture.read_bytes()).state
    assert state["groups"] == [{"atoms": [], "items": [["notes", 0], ["shapes", 0]]}]
    state = deepcopy(state)
    del state["groups"]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    note = root.find('.//t[@id="9"]')
    rectangle = root.find('.//graphic[@id="10"]')
    assert note is not None and note.get("color") == "3"
    assert rectangle is not None and rectangle.get("color") == "3"
    assert root.find('.//group[@id="8"]') is None


def test_edit_inside_unmapped_group_keeps_wrapper_after_chemical_property_detach():
    payload = drawing(
        '<group id="2">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Caption</s>',
        "</t>",
        '<chemicalproperty id="8" ChemicalPropertyDisplayID="7" BasisObjects="4 5"/>',
        "</group>",
    )
    state = parse_cdxml_document(payload).state
    assert "groups" not in state
    state = deepcopy(state)
    state["notes"][0] = {
        **state["notes"][0],
        "text": "Edited caption",
        "html": "<p>Edited caption</p>",
    }

    saved = update_native_document(state, note_writer=write_native_caption)
    root = ET.fromstring(saved)
    # Detaching the property would let the edited XML qualify; the group
    # was not mapped at import, so its wrapper and children stay.
    assert root.find(".//chemicalproperty") is None
    group = root.find('.//group[@id="2"]')
    assert group is not None
    assert [child.get("id") for child in group] == ["3", "7"]


def resolved_styles(root: ET.Element) -> dict[tuple[str, str], str | None]:
    """Every identified element's inherited style values, ancestors included."""
    parents = {child: parent for parent in root.iter() for child in parent}
    resolved: dict[tuple[str, str], str | None] = {}
    for element in root.iter():
        identity = element.get("id")
        if identity is None or element.tag in {"group", "font"}:
            continue
        for key in INHERITED_STYLE_KEYS:
            current: ET.Element | None = element
            while current is not None and key not in current.attrib:
                current = parents.get(current)
            resolved[(identity, key)] = None if current is None else current.get(key)
    return resolved


def styled_group() -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<CDXML BondLength="20" CaptionFont="3" CaptionSize="10" color="4">'
        b'<fonttable><font id="3" name="Arial"/></fonttable>'
        b'<colortable><color r="1" g="0" b="0"/><color r="0" g="0" b="1"/>'
        b'<color r="0" g="1" b="0"/></colortable>'
        b'<page id="1" BoundingBox="0 0 400 300">'
        b'<group id="2" color="3" LineWidth="1.5" BoundingBox="40 50 120 130" Z="9">'
        b'<fragment id="3">'
        b'<n id="4" p="50 60" Element="6"/>'
        b'<n id="5" p="70 60" Element="6" color="2"/>'
        b'<b id="6" B="4" E="5"/>'
        b"</fragment>"
        b'<t id="7" p="50 100" BoundingBox="50 90 110 101">'
        b'<s font="3" size="10">Inherited</s><s font="3" size="10" color="2">Red</s>'
        b"</t>"
        b'<t id="8" p="50 120" BoundingBox="50 110 110 121" color="2">'
        b'<s font="3" size="10">Override</s>'
        b"</t>"
        b"</group>"
        b"</page></CDXML>"
    )


def test_ungroup_save_keeps_inherited_styles_and_child_overrides():
    raw = styled_group()
    state = parse_cdxml_document(raw).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0], ["notes", 1]]}]
    state = deepcopy(state)
    del state["groups"]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    assert root.find(".//group") is None
    assert resolved_styles(root) == resolved_styles(
        ET.fromstring(state["cdxml_source"]["xml"])
    )
    by_id = {e.get("id"): e for e in root.iter() if e.tag != "font"}
    # Only direct children take the group value; overrides keep their own.
    assert by_id["3"].get("color") == "3"
    assert by_id["3"].get("LineWidth") == "1.5"
    assert by_id["7"].get("color") == "3"
    assert by_id["8"].get("color") == "2"
    assert "color" not in by_id["4"].attrib
    assert by_id["5"].get("color") == "2"
    assert "color" not in by_id["6"].attrib
    assert by_id["7"].get("LineWidth") == by_id["8"].get("LineWidth") == "1.5"
    for identity in ("4", "5", "6"):
        assert "LineWidth" not in by_id[identity].attrib
    # Group-own geometry and rank are never copied onto members.
    for identity in ("3", "4", "5", "6"):
        assert "BoundingBox" not in by_id[identity].attrib
        assert "Z" not in by_id[identity].attrib
    assert by_id["7"].get("BoundingBox") == "50 90 110 101"
    assert "Z" not in by_id["7"].attrib

    reopened = parse_cdxml_document(saved).state
    original = parse_cdxml_document(raw).state
    assert reopened["model"]["atoms"] == original["model"]["atoms"]
    assert reopened["model"]["bonds"] == original["model"]["bonds"]
    assert [note["html"] for note in reopened["notes"]] == [
        note["html"] for note in original["notes"]
    ]


def test_ungroup_save_keeps_hidden_caption_hidden():
    raw = drawing(
        '<group id="2" Visible="no">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Hidden</s>',
        "</t>",
        "</group>",
    )
    state = parse_cdxml_document(raw).state
    assert state["notes"] == []
    assert state["groups"] == [{"atoms": [0, 1], "items": []}]
    state = deepcopy(state)
    del state["groups"]

    saved = update_native_document(state)
    root = ET.fromstring(saved)
    assert root.find(".//group") is None
    assert root.find('.//t[@id="7"]').get("Visible") == "no"
    assert parse_cdxml_document(saved).state["notes"] == []


@pytest.mark.parametrize(
    ("group_open", "extra", "detail"),
    [
        ('<group id="2" Integral="yes">', "", "Integral"),
        ('<group id="2" fgcolor="3">', "", "fgcolor"),
        (
            '<group id="2">',
            '<objecttag id="30" TagType="Unknown" Name="note" Value="x"/>',
            "objecttag",
        ),
    ],
)
def test_ungroup_save_refuses_unsupported_group_metadata(group_open, extra, detail):
    raw = drawing(
        group_open,
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        extra,
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Caption</s>',
        "</t>",
        "</group>",
    )
    state = parse_cdxml_document(raw).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    # Kept groups write the metadata back unchanged.
    untouched = ET.fromstring(update_native_document(deepcopy(state)))
    assert untouched.find('.//group[@id="2"]') is not None
    state = deepcopy(state)
    del state["groups"]
    before = deepcopy(state)
    with pytest.raises(ValueError, match=rf"native group #2 would drop .*{detail}"):
        update_native_document(state)
    assert state == before


def test_refused_ungroup_save_leaves_existing_file_unchanged(canvas, tmp_path):
    raw = drawing(
        '<group id="2" Integral="yes">',
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
    path = tmp_path / "grouped.cdxml"
    path.write_bytes(raw)
    state = deepcopy(parse_cdxml_document(raw).state)
    del state["groups"]
    with pytest.raises(ValueError, match="Integral"):
        save_cdxml_document(canvas, str(path), state)
    assert path.read_bytes() == raw


def reference_drawing(reference: str) -> bytes:
    return drawing(
        '<group id="20">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Caption</s>',
        "</t>",
        "</group>",
        '<t id="12" p="50 160" BoundingBox="50 150 110 161">',
        '<s font="3" size="10">C2H6</s>',
        "</t>",
        '<arrow id="15" Head3D="200 80 0" Tail3D="150 80 0" ArrowheadHead="Full"/>',
        reference,
    )


def test_ungroup_save_refuses_step_object_reference_instead_of_pruning():
    state = parse_cdxml_document(
        reference_drawing(
            '<scheme><step id="17" ReactionStepArrows="15" '
            'ReactionStepObjectsAboveArrow="20"/></scheme>'
        )
    ).state
    assert state["groups"]
    state = deepcopy(state)
    del state["groups"]
    with pytest.raises(
        ValueError, match=r"Ungrouping .*step\.ReactionStepObjectsAboveArrow"
    ):
        update_native_document(state)


def test_ungroup_save_detaches_chemical_property_based_on_group():
    state = parse_cdxml_document(
        reference_drawing(
            '<chemicalproperty id="16" ChemicalPropertyDisplayID="12" '
            'ChemicalPropertyType="1" BasisObjects="20"/>'
        )
    ).state
    assert state["groups"] == [{"atoms": [0, 1], "items": [["notes", 0]]}]
    untouched = ET.fromstring(update_native_document(deepcopy(state)))
    assert untouched.find('.//chemicalproperty[@id="16"]') is not None
    state = deepcopy(state)
    del state["groups"]

    root = ET.fromstring(update_native_document(state))
    assert root.find(".//group") is None
    assert root.find(".//chemicalproperty") is None
    assert root.find('.//t[@id="12"]') is not None


def test_snapshot_without_imported_groups_keeps_native_wrapper():
    raw = molecule_and_caption_group()
    old = deepcopy(parse_cdxml_document(raw).state)
    # Snapshots written before group mapping carry no groups in either state.
    del old["groups"]
    del old["cdxml_source"]["baseline"]["groups"]
    reopened = parse_cdxml_document(embed_document(raw, old))
    assert reopened.has_snapshot
    assert "groups" not in reopened.state

    root = ET.fromstring(update_native_document(deepcopy(reopened.state)))
    group = root.find('.//group[@id="2"]')
    assert group is not None
    assert [child.get("id") for child in group] == ["3", "7"]


def test_ungroup_after_member_deletion_unwraps_remaining_members():
    state = deepcopy(parse_cdxml_document(molecule_and_caption_group()).state)
    state["notes"].pop(0)
    state["cdxml_source"]["items"]["notes"].pop(0)
    del state["groups"]

    root = ET.fromstring(update_native_document(state))
    assert root.find(".//group") is None
    assert [child.tag for child in root.find("page")] == ["fragment"]


def test_save_sync_never_requalifies_groups_from_the_xml_being_written():
    payload = drawing(
        '<group id="2">',
        '<fragment id="3">',
        '<n id="4" p="50 60" Element="6"/>',
        '<n id="5" p="70 60" Element="6"/>',
        '<b id="6" B="4" E="5"/>',
        "</fragment>",
        '<t id="7" p="50 100" BoundingBox="50 90 110 101">',
        '<s font="3" size="10">Caption</s>',
        "</t>",
        '<chemicalproperty id="8" ChemicalPropertyDisplayID="7" BasisObjects="4 5"/>',
        "</group>",
        '<group id="9">',
        '<fragment id="10">',
        '<n id="11" p="150 60" Element="6"/>',
        '<n id="12" p="170 60" Element="6"/>',
        '<b id="13" B="11" E="12"/>',
        "</fragment>",
        "</group>",
    )
    state = parse_cdxml_document(payload).state
    assert state["groups"] == [{"atoms": [2, 3], "items": []}]
    source = state["cdxml_source"]
    # The XML being written has already lost the property that kept group 2
    # unmapped at import; only the immutable source decides what was mapped.
    root = ET.fromstring(source["xml"])
    page = root.find("page")
    group = root.find('.//group[@id="2"]')
    group.remove(group.find("chemicalproperty"))
    parents = {child: parent for parent in root.iter() for child in parent}
    by_id = {e.get("id"): e for e in root.iter() if e.tag not in {"font", "objecttag"}}

    assert (
        sync_native_groups_on_save(
            page, parents=parents, by_id=by_id, state=state, source=source
        )
        == set()
    )
    assert [child.get("id") for child in page] == ["2", "9"]
    assert sync_native_groups_on_save(
        page,
        parents=parents,
        by_id=by_id,
        state={**state, "groups": []},
        source=source,
    ) == {"9"}
    assert [child.get("id") for child in page] == ["2", "10"]
