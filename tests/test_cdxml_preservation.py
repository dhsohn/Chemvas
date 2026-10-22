"""Source-preserving editing contracts, using synthetic non-research drawings."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.cdxml_document import (
    embed_document,
    parse_cdxml_document,
    read_cdxml_document,
)
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.export.cdxml_native_text import write_native_caption
from chemvas.ui.window.main_window_ports import active_canvas_for_window

NATIVE = b"""<CDXML LabelFont="3" LabelSize="10" CaptionFont="3" CaptionSize="10" BondLength="20"><fonttable><font id="3" name="Arial"/></fonttable><page id="1" BoundingBox="0 0 400 300"><group id="2"><fragment id="3"><n id="4" p="50 60" AtomID="1"/><n id="5" p="70 60" NodeType="Fragment"><fragment id="6"><n id="7" p="70 60" Element="8" NumHydrogens="0"/><n id="8" p="90 60" NumHydrogens="3"/><n id="9" p="50 60" NodeType="ExternalConnectionPoint"/><b id="10" B="7" E="8"/><b id="11" B="7" E="9"/></fragment><t p="70 60"><s font="3" size="10" face="96">OMe</s></t></n><b id="12" B="4" E="5"/></fragment><t id="13" p="50 100" BoundingBox="50 90 110 101"><s font="3" size="10" face="1">Condition</s><s font="3" size="8" face="32">2</s></t><curve id="14" CurvePoints="120 60 120 60 130 40 150 40 160 60 160 60"/><arrow id="15" Head3D="200 80 0" Tail3D="150 80 0" ArrowheadHead="Full"/><scheme id="16"><step id="17" ReactionStepReactants="3" ReactionStepArrows="15"/></scheme></group></page></CDXML>"""


def imported():
    return parse_cdxml_document(NATIVE, preserve_source=True).state


def native(state):
    return ET.fromstring(
        update_native_document(state, note_writer=write_native_caption)
    )


def test_untouched_native_tree_is_preserved_including_nested_chemistry():
    state = imported()
    assert len(state["model"]["atoms"]) == 2
    assert state["model"]["atoms"][1]["element"] == "OMe"
    assert len(state["images"]) == 2
    assert ET.canonicalize(update_native_document(state).decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )


def test_moving_contracted_node_translates_definition_without_replacing_it():
    state = imported()
    state["model"]["atoms"][1]["x"] += 7
    root = native(state)
    node = root.find('.//n[@id="5"]')
    assert node.get("p") == "77 60"
    assert node.find('.//n[@id="7"]').get("p") == "77 60"
    assert node.find('.//b[@id="10"]').attrib == {"id": "10", "B": "7", "E": "8"}
    assert root.find(".//step").get("ReactionStepReactants") == "3"
    assert root.find('.//t[@id="13"]/s').get("face") == "1"


def test_moving_curve_keeps_native_control_points_and_reaction_reference():
    state = imported()
    state["images"][0]["x"] += 10
    root = native(state)
    assert (
        root.find(".//curve").get("CurvePoints")
        == "130 60 130 60 140 40 160 40 170 60 170 60"
    )
    assert root.find(".//step").get("ReactionStepArrows") == "15"


def test_deleted_arrow_is_removed_from_reaction_step():
    state = imported()
    state["images"].pop()
    state["cdxml_source"]["items"]["images"].pop()
    root = native(state)
    assert root.find(".//step").attrib == {"id": "17", "ReactionStepReactants": "3"}
    assert root.find(".//arrow") is None


def test_source_provenance_survives_snapshot_json_numbers():
    state = imported()
    state["model"]["atoms"][0]["y"] += 3
    raw = embed_document(update_native_document(state), state)
    reopened = parse_cdxml_document(raw).state
    assert reopened["model"]["atoms"]["0"]["y"] == -87
    assert "fragment" in reopened["cdxml_source"]["xml"]
    assert ET.canonicalize(
        update_native_document(reopened).decode()
    ) == ET.canonicalize(update_native_document(state).decode())


def test_new_generic_label_is_native_query_not_carbon():
    state = imported()
    state["model"]["atoms"][0]["element"] = "R2"
    root = native(state)
    node = root.find('.//n[@id="4"]')
    assert node.get("NodeType") == "GenericNickname"
    assert node.get("GenericNickname") == "R"
    assert node.get("Element") is None
    assert "".join(node.find("t").itertext()) == "R2"


def test_qt_normalization_does_not_rewrite_untouched_rich_text(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    path = tmp_path / "native.cdxml"
    path.write_bytes(NATIVE)
    box = Mock()
    try:
        service = window.services.document_action_service
        assert service.load_canvas_from_path(window, str(path), message_box=box)
        state = canvas.services.canvas_document_session_service.snapshot_state()
        assert ET.canonicalize(
            update_native_document(state, note_writer=write_native_caption).decode()
        ) == ET.canonicalize(state["cdxml_source"]["xml"])
        canvas.services.atom_label_service.apply_atom_label_prompt(0, "N")
        assert service.save_canvas_to_path(window, str(path), message_box=box), (
            box.warning.call_args
        )
        raw = path.read_bytes().split(b"\n<!-- ChemvasDocument:")[0]
        assert ET.fromstring(raw).find('.//n[@id="4"]').get("Element") == "7"
        assert read_cdxml_document(path).state["model"]["atoms"]["0"]["element"] == "N"
    finally:
        window.services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()


def test_new_caption_and_arrow_have_native_elements():
    app = QApplication.instance() or QApplication([])
    state = imported()
    state["notes"].append(dict(text="New", html="", x=0, y=0))
    state["cdxml_source"]["items"]["notes"].append(None)
    state["arrows"].append(dict(kind="arrow", start=[0, 0], end=[30, 0]))
    root = native(state)
    assert any("New" == "".join(t.itertext()) for t in root.iter("t"))
    assert len(list(root.iter("arrow"))) == 2
    app.processEvents()


def test_modified_caption_writes_rich_runs_without_losing_unrelated_objects():
    app = QApplication.instance() or QApplication([])
    state = imported()
    state["notes"][0]["text"] = "Edited"
    state["notes"][0]["html"] = (
        '<p><span style="font-size:14pt;font-weight:700">Edited</span></p>'
    )
    root = native(state)
    assert root.find('.//t[@id="13"]/s').get("size") == "14"
    assert root.find('.//t[@id="13"]/s').get("face") == "1"
    assert root.find(".//step").attrib == ET.fromstring(NATIVE).find(".//step").attrib
    app.processEvents()


def test_delete_undo_restores_source_note_identity():
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    try:
        session.apply_state(imported())
        before = session.snapshot_state()
        note = canvas.runtime_state.note_items()[0]
        canvas.services.selection.select_note(note, additive=True)
        assert canvas.services.scene_delete_controller.delete_selected_items()
        assert session.snapshot_state()["cdxml_source"]["items"]["notes"] == []
        canvas.services.history_service.undo()
        assert session.snapshot_state() == before
        assert ET.canonicalize(
            update_native_document(
                session.snapshot_state(), note_writer=write_native_caption
            ).decode()
        ) == ET.canonicalize(before["cdxml_source"]["xml"])
    finally:
        window.services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()


def test_malformed_baseline_bindings_rejected_before_save():
    state = imported()
    state["cdxml_source"]["baseline_items"]["notes"] = []
    with pytest.raises(ValueError, match="bindings"):
        update_native_document(state)


def test_deleting_native_charge_graphic_does_not_leave_hidden_charge():
    raw = NATIVE.replace(
        b'<curve id="14"',
        b'<graphic id="18" GraphicType="Symbol" SymbolType="Plus" BoundingBox="45 45 50 50"><represent attribute="Charge" object="4"/></graphic><curve id="14"',
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    index = state["cdxml_source"]["items"]["images"].index("18")
    state["images"].pop(index)
    state["cdxml_source"]["items"]["images"].pop(index)
    with pytest.raises(ValueError, match="chemical annotation"):
        update_native_document(state)


def embedded_native():
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGBA", (3, 2), "red").save(out, format="PNG")
    return NATIVE.replace(
        b"</page>",
        (
            '<embeddedobject id="30" BoundingBox="10 20 40 40" PNG="'
            + out.getvalue().hex()
            + '" EnhancedMetafile="original-metafile"><annotation Keyword="Name" Content="diagram"/></embeddedobject></page>'
        ).encode(),
    )


def test_embedded_png_display_and_native_metafile_survive_move():
    state = parse_cdxml_document(embedded_native(), preserve_source=True).state
    index = state["cdxml_source"]["items"]["images"].index("30")
    image = state["images"][index]
    assert (image["pixel_width"], image["pixel_height"]) == (3, 2)
    image["x"] += 5
    node = native(state).find(".//embeddedobject")
    assert node.get("BoundingBox") == "15 20 45 40"
    assert node.get("EnhancedMetafile") == "original-metafile"
    assert node.find("annotation").get("Content") == "diagram"


def test_invalid_embedded_png_is_refused_without_metafile_execution():
    raw = embedded_native()
    root = ET.fromstring(raw)
    root.find(".//embeddedobject").set("PNG", "not-hex")
    with pytest.raises(ValueError, match="PNG encoding"):
        parse_cdxml_document(ET.tostring(root), preserve_source=True)


def test_empty_native_curve_is_preserved_without_display_object():
    raw = NATIVE.replace(b"</page>", b'<curve id="31" CurveType="12"/></page>')
    state = parse_cdxml_document(raw, preserve_source=True).state
    assert len(state["images"]) == 2
    assert native(state).find('.//curve[@id="31"]').get("CurveType") == "12"


def test_large_native_workspace_retains_exact_coordinates():
    raw = NATIVE.replace(b"0 0 400 300", b"0 0 4320 5758")
    state = parse_cdxml_document(raw, preserve_source=True).state
    assert state["settings"]["sheet_custom_size_mm"] == pytest.approx(
        [1524, 5758 * 25.4 / 72]
    )
    assert native(state).find("page").get("BoundingBox") == "0 0 4320 5758"


def test_native_negative_quarter_arc_does_not_draw_three_quarters():
    raw = NATIVE.replace(
        b'Head3D="200 80 0" Tail3D="150 80 0"',
        b'Head3D="613.88 837 0" Tail3D="623.25 702 0" Center3D="551.06 764.81 0" AngularSize="-90"',
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    arrow = state["images"][1]
    assert arrow["width"] < 45
    assert 130 < arrow["height"] < 150
    assert native(state).find(".//arrow").get("AngularSize") == "-90"


def test_native_background_fill_stays_below_bonds():
    raw = (
        NATIVE.replace(b'<n id="4"', b'<n Z="100" id="4"')
        .replace(b'<n id="5"', b'<n Z="100" id="5"')
        .replace(b'<b id="12"', b'<b Z="100" id="12"')
        .replace(
            b"</page>",
            b'<graphic id="32" Z="10" GraphicType="Rectangle" RectangleType="Filled" BoundingBox="10 10 100 100"/></page>',
        )
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    index = state["cdxml_source"]["items"]["images"].index("32")
    assert state["images"][index]["z"] < 0
    assert native(state).find('.//graphic[@id="32"]').get("Z") == "10"


@pytest.mark.parametrize(
    "index, expected", [(0, (0, 0, 0)), (1, (255, 255, 255)), (2, (255, 0, 0))]
)
def test_molecular_area_uses_cdxml_color_mapping(index, expected):
    import base64
    import io

    from PIL import Image

    raw = f'''<CDXML><colortable><color r="1" g="0" b="0"/></colortable>
    <page id="1" Width="100" Height="100"><fragment id="2">
    <n id="3" p="10 10"/><n id="4" p="80 10"/><n id="5" p="40 80"/>
    </fragment><ColoredMolecularArea id="6" BasisObjects="3 4 5" bgcolor="{index}"/>
    </page></CDXML>'''.encode()
    state = parse_cdxml_document(raw, preserve_source=True).state
    with Image.open(
        io.BytesIO(base64.b64decode(state["images"][0]["data_base64"]))
    ) as image:
        assert (
            image.convert("RGB").getpixel((image.width // 2, image.height // 3))
            == expected
        )


@pytest.mark.parametrize("index", ["2", "99", "-1"])
def test_missing_molecular_area_color_is_refused(index):
    raw = f'''<CDXML><page id="1" Width="100" Height="100"><fragment id="2">
    <n id="3" p="10 10"/><n id="4" p="80 10"/><n id="5" p="40 80"/>
    </fragment><ColoredMolecularArea id="6" BasisObjects="3 4 5" bgcolor="{index}"/>
    </page></CDXML>'''.encode()
    with pytest.raises(ValueError, match="missing color"):
        parse_cdxml_document(raw, preserve_source=True)
