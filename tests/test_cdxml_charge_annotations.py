"""Regression tests for editing native charge annotations."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json
import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document.inspection import document_annotations, document_model
from chemvas.features.cdxml_document import (
    embed_document,
    parse_cdxml_document,
    read_cdxml_document,
)
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.canvas.input_view_access import set_zoom_for
from chemvas.ui.export.cdxml_native_text import write_native_caption
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from tests.canvas_factory import build_canvas_view
from tests.document_file_helpers import read_document

_FONT = (
    b'<CDXML LabelFont="3" LabelSize="10" BondLength="20">'
    b'<fonttable><font id="3" name="Arial"/></fonttable>'
)
_PAGE = b'<page id="1" BoundingBox="0 0 400 300">'
_PAGE_END = b"</page></CDXML>"


def _native_charge_fragment(
    node_id: str,
    graphic_id: str,
    symbol: str,
    charge: int,
    p: str = "49.41 79.11",
    box: str = "49.39 88.50 41.89 88.50",
) -> bytes:
    return (
        f'<fragment id="2"><n id="{node_id}" p="{p}" Element="7" Charge="{charge}">'
        f'<t p="{p}"><s font="3" size="10" face="96">N</s></t></n>'
        f'<graphic id="{graphic_id}" GraphicType="Symbol" SymbolType="{symbol}" '
        f'BoundingBox="{box}"><represent attribute="Charge" object="{node_id}"/>'
        f"</graphic></fragment>"
    ).encode()


def charge_document(
    symbol: str = "CirclePlus",
    charge: int = 1,
    *,
    extra_fragment: bytes = b"",
) -> bytes:
    fragment = _native_charge_fragment("27", "36", symbol, charge).decode()
    if extra_fragment:
        fragment = fragment.replace(
            "</fragment>",
            extra_fragment.decode() + "</fragment>",
            1,
        )
    body = fragment.encode()
    return _FONT + _PAGE + body + _PAGE_END


def dual_charge_document() -> bytes:
    p = "49.41 79.11"
    body = (
        f'<fragment id="2"><n id="27" p="{p}" Element="7" Charge="1">'
        f'<t p="{p}"><s font="3" size="10" face="96">N</s></t></n>'
        f'<graphic id="36" GraphicType="Symbol" SymbolType="CirclePlus" '
        f'BoundingBox="49.39 88.50 41.89 88.50">'
        f'<represent attribute="Charge" object="27"/></graphic>'
        f'<graphic id="37" GraphicType="Symbol" SymbolType="CirclePlus" '
        f'BoundingBox="90.00 110.00 82.50 110.00">'
        f'<represent attribute="Charge" object="27"/></graphic>'
        f"</fragment>"
    )
    return _FONT + _PAGE + body.encode() + _PAGE_END


def imported(raw: bytes):
    return parse_cdxml_document(raw, preserve_source=True).state


def native_xml(state):
    return ET.fromstring(
        update_native_document(state, note_writer=write_native_caption)
    )


def image_binding_index(state, native_id: str) -> int:
    return state["cdxml_source"]["items"]["images"].index(native_id)


def remove_native_charge_graphic(state, native_graphic_id: str) -> None:
    index = image_binding_index(state, native_graphic_id)
    state["images"].pop(index)
    state["cdxml_source"]["items"]["images"].pop(index)


def clear_model_charge(state, atom_id: int) -> None:
    annotations = state["model"].get("atom_annotations") or {}
    if atom_id in annotations:
        del annotations[atom_id]
    elif str(atom_id) in annotations:
        del annotations[str(atom_id)]
    state["model"]["atom_annotations"] = annotations


def set_model_charge(state, atom_id: int, formal_charge: int) -> None:
    annotations = dict(state["model"].get("atom_annotations") or {})
    key = atom_id if atom_id in state["model"]["atoms"] else str(atom_id)
    if formal_charge:
        annotations[key] = {"formal_charge": formal_charge}
    else:
        annotations.pop(key, None)
        annotations.pop(atom_id, None)
        annotations.pop(str(atom_id), None)
    state["model"]["atom_annotations"] = annotations


def append_mark(
    state,
    *,
    kind: str,
    x: float,
    y: float,
    atom_id: int | None = None,
    dx: float = 0.0,
    dy: float = 0.0,
    color: str = "#000000",
) -> None:
    state.setdefault("marks", []).append(
        dict(
            kind=kind,
            text=None,
            x=x,
            y=y,
            atom_id=atom_id,
            dx=dx,
            dy=dy,
            color=color,
        )
    )
    bindings = state["cdxml_source"]["items"].setdefault("marks", [])
    bindings.append(None)


def charge_graphic_center(state, native_graphic_id: str) -> tuple[float, float]:
    image = state["images"][image_binding_index(state, native_graphic_id)]
    return image["x"] + image["width"] / 2, image["y"] + image["height"] / 2


def annotations_for(state):
    return document_annotations(state, document_model(state))


def assert_update_native_rejects_unchanged(state):
    # Snapshot after the caller has completed all deliberate setup edits.
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        update_native_document(state, note_writer=write_native_caption)
    assert state == before


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(700, 500)
    view.show()
    app.processEvents()
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()


def snapshot(canvas):
    return canvas.services.canvas_document_session_service.snapshot_state()


def click(canvas, pos: QPointF):
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.mapFromScene(pos),
    )
    QApplication.processEvents()


@pytest.mark.parametrize(
    ("symbol", "charge"),
    [
        ("Plus", 1),
        ("CirclePlus", 1),
        ("Minus", -1),
        ("CircleMinus", -1),
    ],
)
def test_supported_native_charge_glyph_delete_clears_charge_in_xml(symbol, charge):
    raw = charge_document(symbol, charge)
    state = imported(raw)
    before = copy.deepcopy(state)
    assert annotations_for(state)[0]["formal_charge"] == charge
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    assert annotations_for(state) == {}
    root = native_xml(state)
    node = root.find('.//n[@id="27"]')
    assert node is not None
    assert "Charge" not in node.attrib
    assert root.find('.//graphic[@id="36"]') is None
    unrelated = {
        k: before[k]
        for k in before
        if k not in {"images", "cdxml_source", "model", "marks"}
    }
    after_unrelated = {
        k: state[k]
        for k in state
        if k not in {"images", "cdxml_source", "model", "marks"}
    }
    assert after_unrelated == unrelated


@pytest.mark.parametrize(
    ("symbol", "charge", "mark_kind"),
    [
        ("Plus", 1, "plus"),
        ("CirclePlus", 1, "circled_plus"),
        ("Minus", -1, "minus"),
        ("CircleMinus", -1, "circled_minus"),
    ],
)
def test_delete_native_glyph_same_sign_mark_replacement(symbol, charge, mark_kind):
    raw = charge_document(symbol, charge)
    state = imported(raw)
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind=mark_kind,
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    set_model_charge(state, 0, charge)
    assert annotations_for(state)[0]["formal_charge"] == charge
    before = copy.deepcopy(state)
    root = native_xml(state)
    assert state == before
    node = root.find('.//n[@id="27"]')
    assert node is not None and int(node.get("Charge", "0")) == charge
    assert root.find('.//graphic[@id="36"]') is None
    assert any(
        graphic.find('represent[@attribute="Charge"][@object="27"]') is not None
        for graphic in root.iter("graphic")
    )


def test_unsupported_charge_graphic_delete_without_model_sync_rejected():
    state = imported(charge_document())
    remove_native_charge_graphic(state, "36")
    set_model_charge(state, 0, 2)
    assert_update_native_rejects_unchanged(state)


@pytest.mark.parametrize(
    "extra",
    [
        (
            '<graphic id="99" GraphicType="Symbol" SymbolType="Plus" '
            'BoundingBox="49.39 70.00 41.89 70.00">'
            '<represent attribute="Charge" object="27"/>'
            '<represent attribute="Charge" object="27"/></graphic>'
        ),
        (
            '<graphic id="99" GraphicType="Symbol" SymbolType="Plus" '
            'BoundingBox="49.39 70.00 41.89 70.00">'
            '<represent attribute="Radical" object="27"/></graphic>'
        ),
        (
            '<graphic id="99" GraphicType="Symbol" SymbolType="Plus" '
            'BoundingBox="49.39 70.00 41.89 70.00">'
            '<represent attribute="Charge" object="27"/>'
            '<represent attribute="Radical" object="27"/></graphic>'
        ),
    ],
)
def test_ambiguous_or_noncharge_represent_rejected_on_save(extra):
    raw = charge_document().replace(
        b"</graphic></fragment>",
        (extra + "</graphic></fragment>").encode(),
    )
    state = imported(raw)
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    assert_update_native_rejects_unchanged(state)


def test_partial_dual_charge_graphic_deletion_rejected():
    state = imported(dual_charge_document())
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    assert_update_native_rejects_unchanged(state)


def test_unchanged_native_charge_document_preserves_source_xml():
    raw = charge_document()
    state = imported(raw)
    before = copy.deepcopy(state)
    written = update_native_document(state, note_writer=write_native_caption).decode()
    assert state == before
    assert ET.canonicalize(written) == ET.canonicalize(state["cdxml_source"]["xml"])


def test_delete_only_neutral_reflected_in_document_annotations_before_save():
    state = imported(charge_document())
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    assert annotations_for(state) == {}


def test_sign_change_via_mark_reflected_in_document_annotations():
    state = imported(charge_document("Minus", -1))
    remove_native_charge_graphic(state, "36")
    set_model_charge(state, 0, 1)
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="circled_plus",
        atom_id=0,
        x=atom["x"] + 5,
        y=atom["y"] - 10,
        dx=5,
        dy=-10,
    )
    assert annotations_for(state)[0]["formal_charge"] == 1
    before = copy.deepcopy(state)
    root = native_xml(state)
    assert state == before
    node = root.find('.//n[@id="27"]')
    assert node is not None and int(node.get("Charge", "0")) == 1
    graphic = root.find('.//graphic[@SymbolType="CirclePlus"]')
    assert graphic is not None
    assert graphic.find('represent[@attribute="Charge"][@object="27"]') is not None
    unrelated = {
        k: before[k]
        for k in before
        if k not in {"marks", "cdxml_source", "model", "images"}
    }
    after_unrelated = {
        k: state[k]
        for k in state
        if k not in {"marks", "cdxml_source", "model", "images"}
    }
    assert after_unrelated == unrelated


def test_native_minus_replaced_by_circled_plus_mark_without_model_annotation():
    state = imported(charge_document("Minus", -1))
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="circled_plus",
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    before = copy.deepcopy(state)
    raw = update_native_document(state, note_writer=write_native_caption)
    assert state == before
    root = ET.fromstring(raw)
    represents = [
        represent
        for graphic in root.iter("graphic")
        for represent in graphic.findall('represent[@attribute="Charge"][@object="27"]')
    ]
    assert root.find('.//n[@id="27"]').get("Charge") == "1"
    assert len(represents) == 1
    assert annotations_for(imported(raw))[0]["formal_charge"] == 1


def test_sibling_electron_charge_represent_rejected_after_circle_plus_delete():
    extra = (
        b'<graphic id="99" GraphicType="Symbol" SymbolType="Electron" '
        b'BoundingBox="60.00 70.00 52.50 70.00">'
        b'<represent attribute="Charge" object="27"/></graphic>'
    )
    state = imported(charge_document(extra_fragment=extra))
    assert len(state["images"]) == 2
    remove_native_charge_graphic(state, "36")
    assert_update_native_rejects_unchanged(state)


def neutral_n_document(
    *, charge: int | None = None, radical: str | None = None
) -> bytes:
    p = "49.41 79.11"
    attributes = ' Element="7"'
    if charge is not None:
        attributes += f' Charge="{charge}"'
    if radical is not None:
        attributes += f' Radical="{radical}"'
    body = (
        f'<fragment id="2"><n id="27" p="{p}"{attributes}>'
        f'<t p="{p}"><s font="3" size="10" face="96">N</s></t></n></fragment>'
    )
    return _FONT + _PAGE + body.encode() + _PAGE_END


@pytest.mark.parametrize(
    ("radical", "mark_kind", "model_charge"),
    [(None, "minus", -1), ("Doublet", "plus", 1)],
)
def test_unseen_native_charge_cannot_be_replaced_by_new_mark(
    radical, mark_kind, model_charge
):
    state = imported(neutral_n_document(charge=1, radical=radical))
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind=mark_kind,
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    set_model_charge(state, 0, model_charge)
    assert_update_native_rejects_unchanged(state)


def test_neutral_native_atom_adds_single_charge_via_mark():
    state = imported(neutral_n_document())
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="plus",
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    set_model_charge(state, 0, 1)
    before = copy.deepcopy(state)
    saved = native_xml(state)
    assert state == before
    assert saved.find('.//n[@id="27"]').get("Charge") == "1"
    assert len(list(saved.iter("graphic"))) == 1
    unrelated = {
        k: before[k]
        for k in before
        if k not in {"marks", "cdxml_source", "model", "images"}
    }
    after_unrelated = {
        k: state[k]
        for k in state
        if k not in {"marks", "cdxml_source", "model", "images"}
    }
    assert after_unrelated == unrelated


def test_free_floating_mark_has_no_charge_represent():
    state = imported(charge_document())
    before = copy.deepcopy(state)
    append_mark(state, kind="minus", atom_id=None, x=80.0, y=40.0)
    root = native_xml(state)
    native = root.find('.//graphic[@id="36"]')
    assert native is not None
    assert native.find('represent[@attribute="Charge"][@object="27"]') is not None
    for graphic in root.iter("graphic"):
        if graphic.get("id") == "36":
            continue
        if graphic.get("SymbolType") == "Minus":
            assert graphic.find("represent") is None
    assert annotations_for(state)[0]["formal_charge"] == 1
    unrelated = {
        k: before[k] for k in before if k not in {"marks", "cdxml_source", "images"}
    }
    after_unrelated = {
        k: state[k] for k in state if k not in {"marks", "cdxml_source", "images"}
    }
    assert after_unrelated == unrelated


def test_native_glyph_remaining_while_adding_attached_mark_rejected():
    state = imported(charge_document())
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="plus",
        atom_id=0,
        x=atom["x"],
        y=atom["y"] - 12,
        dx=0,
        dy=-12,
    )
    set_model_charge(state, 0, 2)
    assert_update_native_rejects_unchanged(state)


def test_annotation_change_without_matching_marks_not_silently_dropped():
    state = imported(charge_document())
    set_model_charge(state, 0, 2)
    with pytest.raises(ValueError, match="Conflicting"):
        annotations_for(state)


def test_renamed_native_n_to_generic_r_with_matching_mark_is_rejected():
    state = imported(neutral_n_document())
    state["model"]["atoms"][0]["element"] = "R"
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="plus",
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    set_model_charge(state, 0, 1)
    assert_update_native_rejects_unchanged(state)


@pytest.mark.parametrize(
    ("source", "annotation"),
    [
        (neutral_n_document(), {"formal_charge": 1}),
        (charge_document(), {"radical_electrons": 1}),
    ],
)
def test_model_only_electronic_annotation_is_rejected_on_save(source, annotation):
    state = imported(source)
    state["model"]["atom_annotations"] = {0: annotation}
    assert_update_native_rejects_unchanged(state)


def test_neutral_native_plus_and_radical_marks_match_model_for_inspection():
    state = imported(neutral_n_document())
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="plus",
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    append_mark(
        state,
        kind="radical",
        atom_id=0,
        x=atom["x"] - 4,
        y=atom["y"] - 8,
        dx=-4,
        dy=-8,
    )
    state["model"]["atom_annotations"] = {
        0: {"formal_charge": 1, "radical_electrons": 1}
    }
    assert annotations_for(state) == {0: {"formal_charge": 1, "radical_electrons": 1}}


def test_two_plus_marks_matching_model_are_supported_for_inspection():
    state = imported(neutral_n_document())
    atom = state["model"]["atoms"][0]
    for offset in (4, 8):
        append_mark(
            state,
            kind="plus",
            atom_id=0,
            x=atom["x"] + offset,
            y=atom["y"] - 8,
            dx=offset,
            dy=-8,
        )
    state["model"]["atom_annotations"] = {0: {"formal_charge": 2}}
    assert annotations_for(state) == {0: {"formal_charge": 2}}


def test_undeleted_native_plus_and_new_minus_remain_an_inspection_conflict():
    state = imported(charge_document())
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="minus",
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    set_model_charge(state, 0, -1)
    with pytest.raises(ValueError, match="Conflicting"):
        annotations_for(state)


def test_replacement_graphic_reimports_at_front_z(tmp_path):
    raw = (
        charge_document()
        .replace(
            b'<n id="27" p="49.41 79.11" Element="7" Charge="1">',
            b'<n id="27" p="49.41 79.11" Element="7" Charge="1" Z="10">',
        )
        .replace(
            b'BoundingBox="49.39 88.50 41.89 88.50">',
            b'BoundingBox="49.39 88.50 41.89 88.50" Z="11">',
        )
    )
    state = imported(raw)
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="plus",
        atom_id=0,
        x=atom["x"] + 4,
        y=atom["y"] - 8,
        dx=4,
        dy=-8,
    )
    set_model_charge(state, 0, 1)
    saved = update_native_document(state, note_writer=write_native_caption)
    root = ET.fromstring(saved)
    replacement = next(
        graphic
        for graphic in root.iter("graphic")
        if graphic.get("id") != "36"
        and graphic.find('represent[@attribute="Charge"][@object="27"]') is not None
    )
    assert int(replacement.get("Z")) > int(root.find('.//n[@id="27"]').get("Z"))
    path = tmp_path / "replacement-z.cdxml"
    path.write_bytes(saved)
    reopened = parse_cdxml_document(path.read_bytes(), preserve_source=True).state
    index = reopened["cdxml_source"]["items"]["images"].index(replacement.get("id"))
    assert reopened["images"][index]["z"] == 1.0


def test_mark_center_stable_through_raw_reimport(tmp_path):
    state = imported(charge_document())
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    dx, dy = 6.5, -9.25
    append_mark(
        state,
        kind="circled_plus",
        atom_id=0,
        x=atom["x"] + dx,
        y=atom["y"] + dy,
        dx=dx,
        dy=dy,
    )
    set_model_charge(state, 0, 1)
    before = copy.deepcopy(state)
    raw = update_native_document(state, note_writer=write_native_caption)
    assert state == before
    saved = ET.fromstring(raw)
    new_graphic = next(
        graphic
        for graphic in saved.iter("graphic")
        if graphic.get("id") != "36"
        and graphic.find('represent[@attribute="Charge"][@object="27"]') is not None
    )
    graphic_id = new_graphic.get("id")
    assert graphic_id is not None
    path = tmp_path / "charge.cdxml"
    path.write_bytes(raw)
    reopened = parse_cdxml_document(path.read_bytes(), preserve_source=True).state
    assert reopened.get("marks", []) == []
    index = reopened["cdxml_source"]["items"]["images"].index(graphic_id)
    image = reopened["images"][index]
    assert image["x"] + image["width"] / 2 == pytest.approx(atom["x"] + dx)
    assert image["y"] + image["height"] / 2 == pytest.approx(atom["y"] + dy)


def test_embedded_save_reopen_round_trip(tmp_path):
    state = imported(charge_document())
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="circled_plus",
        atom_id=0,
        x=atom["x"] + 3,
        y=atom["y"] - 7,
        dx=3,
        dy=-7,
    )
    set_model_charge(state, 0, 1)
    before = copy.deepcopy(state)
    raw = embed_document(
        update_native_document(state, note_writer=write_native_caption), state
    )
    assert state == before
    path = tmp_path / "embedded.cdxml"
    path.write_bytes(raw)
    reopened = read_cdxml_document(path).state
    assert annotations_for(reopened)[0]["formal_charge"] == 1
    assert ET.canonicalize(
        update_native_document(reopened, note_writer=write_native_caption).decode()
    ) == ET.canonicalize(
        update_native_document(before, note_writer=write_native_caption).decode()
    )


def test_failed_save_leaves_destination_bytes_intact(tmp_path, canvas):
    raw = dual_charge_document()
    path = tmp_path / "native.cdxml"
    path.write_bytes(raw)
    session = canvas.services.canvas_document_session_service
    session.apply_state(imported(raw))
    before_bytes = path.read_bytes()
    before_size = path.stat().st_size
    atom = canvas.model.atoms[0]
    set_zoom_for(canvas, 4)
    canvas.centerOn(atom.x, atom.y)
    center = charge_graphic_center(session.snapshot_state(), "36")
    canvas.services.tool_mode_controller.set_tool("delete")
    click(canvas, QPointF(*center))
    before_snap = snapshot(canvas)
    assert before_snap["cdxml_source"]["items"]["images"] == ["37"]
    with pytest.raises(ValueError):
        session.save_to_file(str(path))
    assert path.read_bytes() == before_bytes
    assert path.stat().st_size == before_size
    assert snapshot(canvas) == before_snap


def test_canvas_delete_native_charge_glyph_undo_redo_and_save(tmp_path, canvas):
    raw = charge_document()
    path = tmp_path / "canvas_charge.cdxml"
    path.write_bytes(raw)
    session = canvas.services.canvas_document_session_service
    session.apply_state(imported(raw))
    atom = canvas.model.atoms[0]
    set_zoom_for(canvas, 4)
    canvas.centerOn(atom.x, atom.y)
    center = charge_graphic_center(session.snapshot_state(), "36")
    before = snapshot(canvas)
    canvas.services.tool_mode_controller.set_tool("delete")
    click(canvas, QPointF(*center))
    assert annotations_for(snapshot(canvas)) == {}
    canvas.services.history_service.undo()
    assert snapshot(canvas) == before
    canvas.services.history_service.redo()
    assert annotations_for(snapshot(canvas)) == {}
    assert session.save_to_file(str(path)) == []
    root = ET.fromstring(path.read_bytes().split(b"\n<!-- ChemvasDocument:")[0])
    assert root.find('.//graphic[@id="36"]') is None
    assert "Charge" not in root.find('.//n[@id="27"]').attrib


def test_canvas_add_circled_plus_on_cleared_native_charge(tmp_path, canvas):
    raw = charge_document()
    path = tmp_path / "add_charge.cdxml"
    path.write_bytes(raw)
    session = canvas.services.canvas_document_session_service
    session.apply_state(imported(raw))
    atom = canvas.model.atoms[0]
    set_zoom_for(canvas, 4)
    canvas.centerOn(atom.x, atom.y)
    center = charge_graphic_center(session.snapshot_state(), "36")
    canvas.services.tool_mode_controller.set_tool("delete")
    click(canvas, QPointF(*center))
    add_mark_for_atom_for(canvas, 0, QPointF(atom.x, atom.y), kind="circled_plus")
    assert canvas.model.atom_annotations[0]["formal_charge"] == 1
    before = snapshot(canvas)
    assert session.save_to_file(str(path)) == []
    session.apply_state(read_document(path).state)
    assert json.dumps(snapshot(canvas), sort_keys=True) == json.dumps(
        before, sort_keys=True
    )


def test_represent_on_native_atom_without_charge_still_rejected():
    raw = charge_document().replace(b' Charge="1"', b"")
    state = imported(raw)
    remove_native_charge_graphic(state, "36")
    assert_update_native_rejects_unchanged(state)


def test_unsupported_mark_kind_rejected_on_save():
    state = imported(charge_document())
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    append_mark(
        state,
        kind="custom_label",
        atom_id=0,
        x=atom["x"],
        y=atom["y"] - 5,
        dx=0,
        dy=-5,
    )
    set_model_charge(state, 0, 1)
    assert_update_native_rejects_unchanged(state)


def test_canvas_drag_attached_charge_mark_keeps_atom_binding(tmp_path, canvas):
    raw = charge_document()
    path = tmp_path / "drag_charge.cdxml"
    path.write_bytes(raw)
    session = canvas.services.canvas_document_session_service
    session.apply_state(imported(raw))
    atom = canvas.model.atoms[0]
    set_zoom_for(canvas, 4)
    canvas.centerOn(atom.x, atom.y)
    center = charge_graphic_center(session.snapshot_state(), "36")
    canvas.services.tool_mode_controller.set_tool("delete")
    click(canvas, QPointF(*center))
    add_mark_for_atom_for(canvas, 0, QPointF(atom.x, atom.y), kind="circled_plus")
    mark = canvas.runtime_state.mark_items()[0]
    mark_center = canvas.services.scene_decoration_build_service.mark_center(mark)
    before = snapshot(canvas)
    canvas.services.tool_mode_controller.set_tool("select")
    click(canvas, mark_center)
    start = canvas.mapFromScene(mark_center)
    end = canvas.mapFromScene(mark_center + QPointF(18, 0))
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    QTest.mouseMove(canvas.viewport(), end, delay=30)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
    )
    QApplication.processEvents()
    moved = canvas.services.scene_decoration_build_service.mark_center(mark)
    assert moved.x() == pytest.approx(mark_center.x() + 18)
    assert mark.data(1)["atom_id"] == 0
    assert snapshot(canvas)["model"] == before["model"]
    canvas.services.history_service.undo()
    assert snapshot(canvas) == before


def test_atom_with_radical_annotation_preserved_fail_closed_on_charge_edit():
    raw = charge_document()
    root = ET.fromstring(raw.decode())
    node = root.find('.//n[@id="27"]')
    node.set("Radical", "Doublet")
    state = imported(ET.tostring(root, encoding="utf-8"))
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    assert_update_native_rejects_unchanged(state)
    source = ET.fromstring(state["cdxml_source"]["xml"])
    assert source.find('.//n[@id="27"]').get("Radical") == "Doublet"


@pytest.mark.parametrize(
    "mark_kinds",
    [("plus", "plus"), ("plus", "minus")],
)
def test_multiple_attached_charge_marks_rejected_after_native_delete(mark_kinds):
    state = imported(charge_document())
    remove_native_charge_graphic(state, "36")
    clear_model_charge(state, 0)
    atom = state["model"]["atoms"][0]
    for offset, kind in enumerate(mark_kinds):
        append_mark(
            state,
            kind=kind,
            atom_id=0,
            x=atom["x"] + 4 + offset,
            y=atom["y"] - 8,
            dx=4 + offset,
            dy=-8,
        )
    set_model_charge(state, 0, 1)
    assert_update_native_rejects_unchanged(state)


def test_delete_native_atom_and_glyph_removes_atom_and_dangling_represent(
    tmp_path, canvas
):
    raw = charge_document()
    path = tmp_path / "delete_atom_charge.cdxml"
    path.write_bytes(raw)
    session = canvas.services.canvas_document_session_service
    session.apply_state(imported(raw))
    atom = canvas.model.atoms[0]
    set_zoom_for(canvas, 4)
    canvas.centerOn(atom.x, atom.y)
    canvas.services.tool_mode_controller.set_tool("delete")
    glyph_center = charge_graphic_center(session.snapshot_state(), "36")
    click(canvas, QPointF(*glyph_center))
    click(canvas, QPointF(atom.x, atom.y))
    state = snapshot(canvas)
    assert state["model"]["atoms"] == {}
    assert state["model"]["next_atom_id"] >= 1
    assert session.save_to_file(str(path)) == []
    saved = ET.fromstring(path.read_bytes().split(b"\n<!-- ChemvasDocument:")[0])
    assert saved.find('.//n[@id="27"]') is None
    assert not list(saved.findall('.//represent[@object="27"]'))
