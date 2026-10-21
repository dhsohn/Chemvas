import hashlib
import json
import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.cdxml_document import (
    embed_document,
    parse_cdxml_document,
    read_cdxml_document,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window

NATIVE = b"""<?xml version="1.0"?><!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd">
<CDXML BondLength="20"><page id="1" Width="400" Height="300"><fragment id="2">
<n id="3" p="100 100"/><n id="4" p="120 100" Element="8"><t><s>O</s></t></n>
<b id="5" B="3" E="4" Order="2" DoublePosition="Center"/>
</fragment><t id="6" p="100 140"><s size="12" face="1">Sample</s></t>
<arrow id="7" Tail3D="150 100 0" Head3D="200 100 0" ArrowheadHead="Full"/></page></CDXML>"""


def test_native_atoms_bonds_text_arrow():
    doc = parse_cdxml_document(NATIVE)
    assert doc.source_sha256 == hashlib.sha256(NATIVE).hexdigest()
    assert doc.state["model"]["atoms"][1]["element"] == "O"
    assert doc.state["model"]["bonds"][0]["style"] == "double_center"
    assert doc.state["notes"][0]["text"] == "Sample"
    assert doc.state["arrows"][0]["kind"] == "arrow"


@pytest.mark.parametrize(
    "raw",
    [
        b"<CDXML><page/><page/></CDXML>",
        NATIVE.replace(b'Element="8"', b'Element="8" Isotope="18"'),
        NATIVE.replace(b'p="120 100"', b'p="nan 100"'),
        NATIVE.replace(b'E="4"', b'E="999"'),
        NATIVE.replace(b'<fragment id="2">', b'<fragment id="3">'),
        NATIVE.replace(b"</page>", b'<embeddedobject id="99"/></page>'),
        b'<!DOCTYPE CDXML [<!ENTITY a "x">]><CDXML><page/></CDXML>',
        b"<CDXML>",
    ],
)
def test_rejects_unsupported_and_malformed_without_partial_document(raw):
    with pytest.raises(ValueError):
        parse_cdxml_document(raw)


def test_snapshot_is_invalidated_by_native_edit():
    doc = parse_cdxml_document(NATIVE)
    saved = embed_document(NATIVE, doc.state)
    assert parse_cdxml_document(saved).state == json.loads(json.dumps(doc.state))
    edited = saved.replace(b'Element="8"', b'Element="7"').replace(b">O</s>", b">N</s>")
    assert parse_cdxml_document(edited).state["model"]["atoms"][1]["element"] == "N"


def test_save_edit_reopen_and_external_change_protection(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    service = window.services.document_action_service
    box = Mock()
    path = tmp_path / "sample.cdxml"
    path.write_bytes(NATIVE)
    try:
        assert service.load_canvas_from_path(window, str(path), message_box=box)
        canvas = active_canvas_for_window(window)
        assert canvas.runtime_state.document_metadata_state.file_path == str(path)
        canvas.services.atom_label_service.apply_atom_label_prompt(1, "N")
        assert service.save_canvas_to_path(window, str(path), message_box=box)
        saved = read_cdxml_document(path)
        assert saved.state["model"]["atoms"]["1"]["element"] == "N"
        assert (
            canvas.runtime_state.document_metadata_state.source_sha256
            == saved.source_sha256
        )
        assert not window.services.canvas_document_service.is_dirty(canvas)
        old = path.read_bytes()
        path.write_bytes(old + b"\n")
        box.question.return_value = 0
        assert not service.save_canvas_to_path(window, str(path), message_box=box)
        assert path.read_bytes() == old + b"\n"
        assert not box.warning.called, box.warning.call_args
    finally:
        window.services.canvas_document_service.mark_clean(
            active_canvas_for_window(window)
        )
        window.close()
        app.processEvents()


def test_wedge_end_preserves_narrow_end_and_charge():
    raw = NATIVE.replace(
        b'Order="2" DoublePosition="Center"', b'Display="WedgeEnd"'
    ).replace(b'Element="8"', b'Element="8" Charge="-1"')
    state = parse_cdxml_document(raw).state
    bond = state["model"]["bonds"][0]
    assert (bond["a"], bond["b"], bond["style"]) == (1, 0, "wedge")
    assert state["marks"][0]["kind"] == "minus"


def test_group_and_graphics_are_editable():
    raw = b'<CDXML><page Width="400" Height="300"><group id="2"><graphic id="3" GraphicType="Rectangle" BoundingBox="10 10 50 60"/><graphic id="4" GraphicType="Line" BoundingBox="80 80 120 80"/></group></page></CDXML>'
    state = parse_cdxml_document(raw).state
    assert state["shapes"][0]["shape_kind"] == "rect"
    assert state["arrows"][0]["kind"] == "line"
    assert state["groups"] == [{"atoms": [], "items": [["shapes", 0], ["arrows", 0]]}]


def test_failed_import_leaves_existing_canvas_unchanged(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    path = tmp_path / "bad.cdxml"
    path.write_bytes(NATIVE.replace(b"</page>", b"<embeddedobject/></page>"))
    box = Mock()
    try:
        assert not window.services.document_action_service.load_canvas_from_path(
            window, str(path), message_box=box
        )
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        assert box.warning.called
    finally:
        window.close()
        app.processEvents()


def test_failed_cdxml_save_preserves_file_and_dirty_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    path = tmp_path / "existing.cdxml"
    path.write_bytes(NATIVE)
    box = Mock()
    service = window.services.document_action_service
    try:
        assert service.load_canvas_from_path(window, str(path), message_box=box)
        canvas = active_canvas_for_window(window)
        canvas.services.atom_label_service.apply_atom_label_prompt(1, "UnverifiedAlias")
        assert not service.save_canvas_to_path(window, str(path), message_box=box)
        assert path.read_bytes() == NATIVE
        assert window.services.canvas_document_service.is_dirty(canvas)
    finally:
        window.services.canvas_document_service.mark_clean(
            active_canvas_for_window(window)
        )
        window.close()
        app.processEvents()


def test_empty_cdxml_document_can_be_saved(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    path = tmp_path / "empty.cdxml"
    box = Mock()
    try:
        assert window.services.document_action_service.save_canvas_to_path(
            window, str(path), message_box=box
        ), box.warning.call_args
        assert not read_cdxml_document(path).state["model"]["atoms"]
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize(
    "display",
    [
        "Solid",
        "WedgeBegin",
        "WedgeEnd",
        "WedgedHashBegin",
        "WedgedHashEnd",
        "Dash",
        "Bold",
    ],
)
def test_imported_bond_displays_can_be_saved(display, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    path = tmp_path / "bonds.cdxml"
    path.write_bytes(
        NATIVE.replace(
            b'Order="2" DoublePosition="Center"', f'Display="{display}"'.encode()
        )
    )
    box = Mock()
    try:
        service = window.services.document_action_service
        assert service.load_canvas_from_path(window, str(path), message_box=box), (
            box.warning.call_args
        )
        assert service.save_canvas_to_path(window, str(path), message_box=box), (
            box.warning.call_args
        )
        assert read_cdxml_document(path).state["model"]["bonds"][0]["order"] == 1
    finally:
        window.services.canvas_document_service.mark_clean(
            active_canvas_for_window(window)
        )
        window.close()
        app.processEvents()


def test_cdxml_unsaved_changes_survive_session_recovery(tmp_path, monkeypatch):
    from chemvas.features.session import DocDescriptor
    from chemvas.ui.session import session_snapshot_store
    from chemvas.ui.session.session_snapshot_store import SessionSnapshotStore

    root = tmp_path / "sessions"
    writer = SessionSnapshotStore(
        root, session_id="old", pid=424242, process_identity="fixture"
    )
    writer.begin()
    state = parse_cdxml_document(NATIVE).state
    state["notes"][0]["text"] = "unsaved edit"
    state["notes"][0].pop("html", None)
    path = str(tmp_path / "source.cdxml")
    writer.save_documents([DocDescriptor(state, path, "source.cdxml", True)])
    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda pid: False)
    reader = SessionSnapshotStore(
        root, session_id="new", pid=424243, process_identity="fixture2"
    )
    recovered = reader.consume_previous_sessions()
    assert len(recovered.docs) == 1
    assert recovered.docs[0].state["notes"][0]["text"] == "unsaved edit"
    assert recovered.docs[0].file_path == path
    assert recovered.docs[0].dirty


def test_save_as_cdxml_filter_adds_cdxml_extension(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    picker = Mock()
    picker.getSaveFileName.return_value = (
        str(tmp_path / "new"),
        "ChemDraw XML (*.cdxml)",
    )
    try:
        assert window.services.document_action_service.save_canvas_as(
            window, file_dialog=picker
        )
        assert (tmp_path / "new.cdxml").read_bytes().startswith(b"<?xml")
        assert not (tmp_path / "new.chemvas").exists()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize(
    "replacement",
    [
        b'Element="8" NumHydrogens="2"',
        b'Element="8" AS="R"',
        b'Element="8" NodeType="GenericNickname"',
    ],
)
def test_chemical_properties_are_not_silently_discarded(replacement):
    with pytest.raises(ValueError, match="Unsupported CDXML"):
        parse_cdxml_document(NATIVE.replace(b'Element="8"', replacement))


def test_declared_byte_budget_is_enforced(monkeypatch):
    from chemvas.features import cdxml_document

    monkeypatch.setattr(cdxml_document, "MAX_DOCUMENT_BYTES", len(NATIVE) - 1)
    with pytest.raises(ValueError, match="byte limit"):
        parse_cdxml_document(NATIVE)


def test_bad_native_xml_cannot_be_hidden_by_valid_snapshot():
    state = parse_cdxml_document(NATIVE).state
    raw = embed_document(b"<not-cdxml/>", state)
    with pytest.raises(ValueError, match="one page"):
        parse_cdxml_document(raw)
