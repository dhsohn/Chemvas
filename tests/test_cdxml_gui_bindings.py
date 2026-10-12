"""Reviewed GUI bindings stay tied to the exact clean saved drawing."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QComboBox, QDialog, QLineEdit, QPushButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.export import read_cdxml_label_bindings
from chemvas.ui.window import main_window_document_action_service as actions
from chemvas.ui.window import main_window_document_dialogs as dialogs
from chemvas.ui.window.main_window_document_dialogs import FigureExportOptions
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.test_cdxml_export import _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.fixture
def saved_window(tmp_path):
    from chemvas.domain.document import Atom, Bond

    state = _simple_state(
        atoms={0: Atom("C", 0, 0), 1: Atom("Ar", 20, 0)}, bonds=[Bond(0, 1)]
    )
    source = tmp_path / "source.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    window = build_main_window()
    service = actions.MainWindowDocumentActionService()
    assert service.load_canvas_from_path(window, str(source))
    sidecar = tmp_path / "review.json"
    payload = dict(
        format="chemvas-cdxml-label-bindings",
        version=1,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bindings=[dict(atom_id=1, expected_label="Ar", meaning="generic_aryl")],
    )
    sidecar.write_text(json.dumps(payload))
    yield window, service, source, sidecar, payload
    window.services.canvas_document_service.mark_clean(active_canvas_for_window(window))
    window.close()


def export(saved_window, monkeypatch, destination, *, binding=True):
    window, service, _, sidecar, _ = saved_window
    options = FigureExportOptions(
        fmt="cdxml",
        scope="sheet",
        sizing="bond",
        dpi=300,
        background="white",
        cdxml_label_bindings_path=str(sidecar) if binding else None,
    )
    monkeypatch.setattr(actions, "prompt_export_options", lambda _: options)
    file_dialog = Mock()
    file_dialog.getSaveFileName.return_value = (str(destination), "")
    message_box = Mock()
    service.export_figure(window, file_dialog=file_dialog, message_box=message_box)
    return message_box


def test_gui_binding_export_uses_explicit_saved_meaning(
    saved_window, monkeypatch, tmp_path
):
    output = tmp_path / "output.cdxml"
    source_before = saved_window[2].read_bytes()
    messages = export(saved_window, monkeypatch, output)
    messages.warning.assert_not_called()
    root = ET.parse(output).getroot()
    assert len(root.findall('.//n[@GenericNickname="ARY"]')) == 1
    assert not root.findall('.//n[@Element="18"]')
    assert saved_window[2].read_bytes() == source_before


@pytest.mark.parametrize(
    "failure",
    [
        "unbound",
        "dirty",
        "changed_file",
        "wrong_hash",
        "wrong_label",
        "invalid_json",
        "untrusted_clean",
        "saved_edit",
    ],
)
def test_stale_or_invalid_binding_creates_no_file(
    saved_window, monkeypatch, tmp_path, failure
):
    window, _, source, sidecar, payload = saved_window
    canvas = active_canvas_for_window(window)
    if failure in {"dirty", "saved_edit"}:
        canvas.model.atoms[0].x += 2
        if failure == "saved_edit":
            session = canvas.services.canvas_document_session_service
            document = write_document(
                source, session.snapshot_state(), CANVAS_FILE_VERSION
            )
            window.services.canvas_document_service.mark_clean(canvas)
            canvas.runtime_state.document_metadata_state.set_source_sha256(
                document.source_sha256
            )
    elif failure == "changed_file":
        source.write_bytes(source.read_bytes() + b"\n")
    elif failure == "wrong_hash":
        payload["source_sha256"] = "f" * 64
        sidecar.write_text(json.dumps(payload))
    elif failure == "wrong_label":
        payload["bindings"][0]["expected_label"] = "Ph"
        sidecar.write_text(json.dumps(payload))
    elif failure == "invalid_json":
        sidecar.write_text('{"version":1,"version":1}')
    elif failure == "untrusted_clean":
        canvas.runtime_state.document_metadata_state.clean_digest = None
    output = tmp_path / "rejected.cdxml"
    messages = export(saved_window, monkeypatch, output, binding=failure != "unbound")
    messages.warning.assert_called_once()
    assert not output.exists()


def test_binding_error_preserves_existing_destination(
    saved_window, monkeypatch, tmp_path
):
    output = tmp_path / "preserved.cdxml"
    output.write_bytes(b"previous export")
    saved_window[3].write_text("null")
    messages = export(saved_window, monkeypatch, output)
    messages.warning.assert_called_once()
    assert output.read_bytes() == b"previous export"


def test_cancel_leaves_destination_and_binding_unread(
    saved_window, monkeypatch, tmp_path
):
    window, service, _, sidecar, _ = saved_window
    sidecar.unlink()
    monkeypatch.setattr(actions, "prompt_export_options", lambda _: None)
    dialog = Mock()
    service.export_figure(window, file_dialog=dialog)
    dialog.getSaveFileName.assert_not_called()


def test_binding_dialog_browse_is_explicit_and_not_reused(saved_window, monkeypatch):
    window, _, _, sidecar, _ = saved_window
    calls = 0

    def drive(dialog):
        nonlocal calls
        field = dialog.findChild(QLineEdit, "exportCdxmlBindingsPath")
        fmt = dialog.findChild(QComboBox, "exportFormatCombo")
        assert field.text() == ""
        fmt.setCurrentIndex(fmt.findData("cdxml"))
        if calls == 0:
            dialog.findChild(QPushButton, "exportCdxmlBindingsBrowse").click()
            assert field.text() == str(sidecar)
        calls += 1
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", drive)
    monkeypatch.setattr(
        dialogs.QFileDialog, "getOpenFileName", lambda *a: (str(sidecar), "")
    )
    assert dialogs.prompt_export_options(window).cdxml_label_bindings_path == str(
        sidecar
    )
    assert dialogs.prompt_export_options(window).cdxml_label_bindings_path is None


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b"NaN", b"{} {}", b"\xff", b"[" * 2000]
)
def test_shared_binding_reader_refuses_non_strict_json(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="strict JSON"):
        read_cdxml_label_bindings(path, "f" * 64)
