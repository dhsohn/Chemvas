"""Desktop partial open of bare external CDXML with source protection."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from PyQt6.QtWidgets import QMessageBox

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.session import DocDescriptor
from chemvas.features.session.logic import manifest_from_json, manifest_to_json
from chemvas.ui.session.session_snapshot_store import SessionSnapshotStore
from chemvas.ui.window.main_window_path_logic import (
    suggested_partial_import_copy_path,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from chemvas.ui.window.recent_documents_store import recent_documents_file

pytestmark = pytest.mark.usefixtures("qt_application")

_CORE = b"""<CDXML BondLength="20"><page id="1" Width="400" Height="300"><fragment id="2">
<n id="3" p="100 100"/><n id="4" p="120 100" Element="8"><t><s>O</s></t></n>
<b id="5" B="3" E="4"/></fragment>"""

_ARROW = b'<graphic id="6" GraphicType="Line" BoundingBox="10 10 50 50" ArrowType="FullHead"/>'


def _with_arc() -> bytes:
    return (
        _CORE
        + b'<graphic id="7" GraphicType="Arc" BoundingBox="10 10 50 50"/></page></CDXML>'
    )


def _with_arrow_and_arc() -> bytes:
    return (
        _CORE
        + _ARROW
        + b'<graphic id="7" GraphicType="Arc" BoundingBox="10 10 50 50"/>'
        b'<scheme id="8"><step id="9" ReactionStepArrows="6"/></scheme></page></CDXML>'
    )


def _with_linked_arc() -> bytes:
    return (
        _CORE + b'<graphic id="6" GraphicType="Arc" BoundingBox="10 10 50 50">'
        b'<represent object="3"/></graphic></page></CDXML>'
    )


def _with_referenced_arc() -> bytes:
    return (
        _CORE + b'<graphic id="6" GraphicType="Arc" BoundingBox="10 10 50 50"/>'
        b'<t id="7" p="20 20" BoundingBox="0 0 10 10"><s>tag</s></t></page></CDXML>'
    ).replace(
        b'<t id="7"',
        b'<t id="7" GraphicID="6"',
    )


def _malformed_arc() -> bytes:
    return (
        _CORE
        + b'<graphic id="6" GraphicType="Arc" BoundingBox="10 10"/></page></CDXML>'
    )


def test_prepare_partial_strips_standalone_arc():
    prepared = parse_cdxml_document(_with_arc(), allow_decorative_omissions=True)
    assert prepared.omitted_decorations == 1
    assert prepared.state["model"]["atoms"]
    assert "import_origin" not in prepared.state["cdxml_source"]
    assert 'GraphicType="Arc"' not in prepared.state["cdxml_source"]["xml"]


def test_scalar_values_matching_arc_id_are_not_references():
    raw = (
        _with_arc()
        .replace(b'id="7"', b'id="18"')
        .replace(b'BondLength="20"', b'BondLength="20" BondSpacing="18"')
        .replace(b"<s>O</s>", b'<s size="18">O</s>')
    )
    assert (
        parse_cdxml_document(raw, allow_decorative_omissions=True).omitted_decorations
        == 1
    )


def test_prepare_partial_keeps_referenced_arrow_and_strips_arc():
    prepared = parse_cdxml_document(
        _with_arrow_and_arc(), allow_decorative_omissions=True
    )
    assert prepared.omitted_decorations == 1
    assert prepared.state["arrows"]
    assert 'GraphicType="Arc"' not in prepared.state["cdxml_source"]["xml"]


def test_prepare_partial_refuses_semantic_graphic():
    with pytest.raises(ValueError, match="Arc"):
        parse_cdxml_document(_with_linked_arc(), allow_decorative_omissions=True)


def test_prepare_partial_refuses_referenced_decoration():
    with pytest.raises(ValueError, match="cannot be omitted safely"):
        parse_cdxml_document(_with_referenced_arc(), allow_decorative_omissions=True)


def test_prepare_partial_refuses_malformed_decoration():
    with pytest.raises(ValueError, match="graphic bounds"):
        parse_cdxml_document(_malformed_arc(), allow_decorative_omissions=True)


def test_strict_parse_unchanged_without_opt_in():
    with pytest.raises(ValueError):
        parse_cdxml_document(_with_arc())


def test_partial_open_cancel_leaves_window_blank(tmp_path, monkeypatch):
    path = tmp_path / "external.cdxml"
    path.write_bytes(_with_arc())
    recent = tmp_path / "recent.json"
    monkeypatch.setattr(
        "chemvas.ui.window.main_window_document_action_service.record_recent",
        lambda *_args, **_kwargs: recent_documents_file(),
    )
    monkeypatch.setattr(
        "chemvas.ui.window.recent_documents_store.recent_documents_file",
        lambda: recent,
    )
    window = build_main_window()
    box = mock.Mock()
    box.question.return_value = QMessageBox.StandardButton.Cancel
    try:
        assert not window.services.document_action_service.load_canvas_from_path(
            window, str(path), message_box=box
        )
        canvas = active_canvas_for_window(window)
        state = canvas.services.canvas_document_session_service.snapshot_state()
        assert not state["model"]["atoms"]
        assert path.read_bytes() == _with_arc()
        assert not recent.exists()
    finally:
        window.services.canvas_document_service.mark_clean(
            active_canvas_for_window(window)
        )
        window.close()


def test_partial_open_and_save_as_protects_source(tmp_path):
    path = tmp_path / "external.cdxml"
    original = _with_arc()
    path.write_bytes(original)
    window = build_main_window()
    box = mock.Mock()
    box.question.return_value = QMessageBox.StandardButton.Open
    try:
        assert window.services.document_action_service.load_canvas_from_path(
            window, str(path), message_box=box
        )
        canvas = active_canvas_for_window(window)
        assert canvas.runtime_state.document_metadata_state.file_path is None
        assert canvas.runtime_state.document_metadata_state.protected_import_source_path
        assert window.services.canvas_document_service.is_dirty(canvas)
        warning = mock.Mock()
        assert not window.services.document_action_service.save_canvas_to_path(
            window, str(path), message_box=warning
        )
        assert path.read_bytes() == original
        copy_path = tmp_path / "copy.cdxml"
        assert window.services.document_action_service.save_canvas_to_path(
            window, str(copy_path), message_box=warning
        )
        assert copy_path.exists()
        assert path.read_bytes() == original
        assert window.services.canvas_document_service.is_dirty(canvas) is False
        assert canvas.runtime_state.document_metadata_state.protected_import_source_path
        assert not window.services.document_action_service.save_canvas_to_path(
            window, str(path), message_box=warning
        )
        assert path.read_bytes() == original
        with pytest.raises(ValueError, match="new file name"):
            canvas.services.canvas_document_session_service.export_figure(
                str(path), fmt="cdxml"
            )
        assert window.services.document_action_service.save_canvas_to_path(
            window, str(copy_path), message_box=warning
        )
        reopened = parse_cdxml_document(copy_path.read_bytes())
        assert reopened.state["model"]["atoms"]
        assert window.services.document_action_service.load_canvas_from_path(
            window, str(copy_path), message_box=warning
        )
    finally:
        for canvas in window.tab_references.all_canvases():
            window.services.canvas_document_service.mark_clean(canvas)
        window.close()


def test_suggested_copy_path_uses_cdxml_suffix(tmp_path):
    source = tmp_path / "scheme.cdxml"
    suggested = suggested_partial_import_copy_path(str(source))
    assert suggested.endswith(" (Chemvas copy).cdxml")


def test_partial_manifest_round_trip_protected_path():
    from chemvas.features.session import DocEntry, SessionManifest

    manifest = SessionManifest(
        pid=1,
        clean_exit=False,
        docs=[
            DocEntry(
                file_path=None,
                display_name="Draft",
                dirty=True,
                snapshot="doc.json",
                protected_import_source_path="/tmp/source.cdxml",
            )
        ],
    )
    restored = manifest_from_json(manifest_to_json(manifest))
    assert restored is not None
    assert restored.docs[0].protected_import_source_path == "/tmp/source.cdxml"


def test_partial_draft_recovery_keeps_protected_path(tmp_path, monkeypatch):
    store = SessionSnapshotStore(tmp_path / "sessions", session_id="a", pid=4242)
    store.begin()
    state = parse_cdxml_document(_with_arc(), allow_decorative_omissions=True).state
    store.save_documents(
        [
            DocDescriptor(
                state=state,
                file_path=None,
                display_name="Draft",
                dirty=True,
                protected_import_source_path=str((tmp_path / "source.cdxml").resolve()),
            )
        ]
    )
    store = SessionSnapshotStore(tmp_path / "sessions", session_id="b", pid=5150)
    result = store.consume_previous_sessions()
    assert result.docs
    assert result.docs[0].protected_import_source_path


def test_partial_open_requests_autosave_when_accepted(tmp_path, monkeypatch):
    path = tmp_path / "external.cdxml"
    path.write_bytes(_with_arc())
    requested: list[bool] = []
    monkeypatch.setattr(
        "chemvas.ui.window.main_window_document_action_service.request_snapshot",
        lambda: requested.append(True),
    )
    window = build_main_window()
    box = mock.Mock()
    box.question.return_value = QMessageBox.StandardButton.Open
    try:
        assert window.services.document_action_service.load_canvas_from_path(
            window, str(path), message_box=box
        )
        assert requested
    finally:
        window.services.canvas_document_service.mark_clean(
            active_canvas_for_window(window)
        )
        window.close()


@pytest.mark.parametrize(
    "raw",
    [
        b"<CDXML><page/><page/></CDXML>",
        _CORE.replace(b'E="4"', b'E="999"') + b"</page></CDXML>",
    ],
)
def test_prepare_partial_does_not_relax_malformed_or_graph_errors(raw):
    with pytest.raises(ValueError):
        parse_cdxml_document(raw, allow_decorative_omissions=True)
