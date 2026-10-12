"""Saved v2 contact IDs are applied to the same detached drawing that is exported."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from unittest.mock import Mock

import pytest

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
)
from chemvas.ui.window import main_window_document_action_service as actions
from chemvas.ui.window.main_window_document_dialogs import FigureExportOptions
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.test_cdxml_documentary_contacts import (
    _contact_entry,
    _fph_bindings,
    _generic_ph_to_ar_state,
    _v2_payload,
)

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.fixture
def saved_contacts(tmp_path):
    state, p, h, ar = _generic_ph_to_ar_state()
    state["model"]["atoms"].update(
        {
            70: dict(
                element="C", x=-150, y=-120, color="#000000", explicit_label=False
            ),
            71: dict(
                element="C", x=-130, y=-120, color="#000000", explicit_label=False
            ),
        }
    )
    state["model"]["bonds"].insert(
        0, dict(a=70, b=71, order=1, style="single", color="#000000")
    )
    state["model"]["next_atom_id"] = 72
    state["notes"] = [
        dict(text="included", x=0, y=80),
        dict(text="outside", x=400, y=80),
    ]
    source = tmp_path / "source.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    service = actions.MainWindowDocumentActionService()
    window = build_main_window()
    assert service.load_canvas_from_path(window, str(source))
    canvas = active_canvas_for_window(window)
    assert canvas.services.scene_delete_controller.delete_bond(0) is not None
    save_messages = Mock()
    assert service.save_canvas_to_path(window, str(source), message_box=save_messages)
    save_messages.warning.assert_not_called()
    assert len(canvas.model.bonds) == 3 and canvas.model.bonds[0] is None
    assert len(read_document(source).state["model"]["bonds"]) == 2
    sidecar = tmp_path / "review.json"
    payload = _v2_payload(
        hashlib.sha256(source.read_bytes()).hexdigest(),
        bindings=_fph_bindings(ar, h),
        documentary_contacts=[_contact_entry(0, p, ar), _contact_entry(1, h, ar)],
    )
    sidecar.write_text(json.dumps(payload))
    windows = [window]
    yield dict(
        window=window,
        canvas=canvas,
        service=service,
        source=source,
        sidecar=sidecar,
        payload=payload,
        p=p,
        h=h,
        ar=ar,
        windows=windows,
    )
    for owned in windows:
        owned.services.canvas_document_service.mark_clean(
            active_canvas_for_window(owned)
        )
        owned.close()


def _export(fixture, monkeypatch, target, scope="sheet"):
    options = FigureExportOptions(
        fmt="cdxml",
        scope=scope,
        sizing="custom",
        dpi=300,
        background="white",
        target_width_mm=170,
        cdxml_label_bindings_path=str(fixture["sidecar"]),
    )
    monkeypatch.setattr(actions, "prompt_export_options", lambda _: options)
    dialog = Mock()
    dialog.getSaveFileName.return_value = (str(target), "")
    messages = Mock()
    fixture["service"].export_figure(
        fixture["window"], file_dialog=dialog, message_box=messages
    )
    return messages


def _select_contacts(fixture):
    canvas = fixture["canvas"]
    canvas.scene().clearSelection()
    for bond_id, bond in enumerate(canvas.model.bonds):
        if bond is not None and fixture["ar"] in (bond.a, bond.b):
            for item in canvas.runtime_state.bond_graphics_state.bond_items[bond_id]:
                item.setSelected(True)
    canvas.runtime_state.note_items()[0].setSelected(True)


@pytest.mark.parametrize("scope", ["sheet", "selection"])
def test_saved_contact_export_matches_reopen_without_mutating_editor(
    saved_contacts, monkeypatch, tmp_path, scope
):
    f = saved_contacts
    original_bytes = f["source"].read_bytes()
    sidecar_bytes = f["sidecar"].read_bytes()
    canvas = f["canvas"]
    model = canvas.model
    bond_objects = list(model.bonds)
    atom_objects = dict(model.atoms)
    if scope == "selection":
        _select_contacts(f)
    immediate = tmp_path / "immediate.cdxml"
    _export(f, monkeypatch, immediate, scope).warning.assert_not_called()
    root = ET.fromstring(immediate.read_bytes())
    assert len(root.findall(".//arrow")) == 2
    texts = "".join(root.itertext())
    assert "included" in texts
    assert ("outside" in texts) is (scope == "sheet")
    assert canvas.model is model
    assert all(a is b for a, b in zip(model.bonds, bond_objects, strict=True))
    assert all(model.atoms[k] is v for k, v in atom_objects.items())
    assert f["source"].read_bytes() == original_bytes
    assert f["sidecar"].read_bytes() == sidecar_bytes

    # Export never compacts the live model or replaces its undo commands.
    canvas.runtime_state.history_service.undo()
    assert canvas.model.bonds[0] is not None
    canvas.runtime_state.history_service.redo()
    assert canvas.model.bonds[0] is None
    f["window"].close()
    window = build_main_window()
    f["windows"].append(window)
    assert f["service"].load_canvas_from_path(window, str(f["source"]))
    f["window"] = window
    f["canvas"] = active_canvas_for_window(window)
    assert len(f["canvas"].model.bonds) == 2
    if scope == "selection":
        _select_contacts(f)
    reopened = tmp_path / "reopened.cdxml"
    _export(f, monkeypatch, reopened, scope).warning.assert_not_called()
    # Covers all serialized chemistry, coordinates, styles, groups and contacts.
    assert immediate.read_bytes() == reopened.read_bytes()
    assert f["source"].read_bytes() == original_bytes


@pytest.mark.parametrize(
    "problem", ["wrong_slot", "reversed_endpoints", "order", "style"]
)
def test_reviewed_contacts_keep_exact_endpoint_order_style_guards(
    saved_contacts, monkeypatch, tmp_path, problem
):
    f = saved_contacts
    payload = f["payload"]
    if problem == "wrong_slot":
        payload["documentary_contacts"][0]["bond_id"] = 1
        payload["documentary_contacts"][1]["bond_id"] = 0
    elif problem == "reversed_endpoints":
        entry = payload["documentary_contacts"][0]
        entry["a"], entry["b"] = entry["b"], entry["a"]
    else:
        bond = f["canvas"].model.bonds[1]
        if problem == "order":
            bond.order = 2
        else:
            bond.style = "single"
        assert f["service"].save_canvas_to_path(
            f["window"], str(f["source"]), message_box=Mock()
        )
        payload["source_sha256"] = hashlib.sha256(f["source"].read_bytes()).hexdigest()
    f["sidecar"].write_text(json.dumps(payload))
    output = tmp_path / "refused.cdxml"
    output.write_bytes(b"existing destination")
    messages = _export(f, monkeypatch, output)
    messages.warning.assert_called_once()
    warning = messages.warning.call_args.args[2]
    assert (
        "endpoints" in warning
        if problem in {"wrong_slot", "reversed_endpoints"}
        else "native_order or native_style" in warning
    )
    assert output.read_bytes() == b"existing destination"


@pytest.mark.parametrize("hidden", [True, False])
def test_binding_outside_visible_selection_still_refuses(
    saved_contacts, monkeypatch, tmp_path, hidden
):
    f = saved_contacts
    if hidden:
        f["canvas"].runtime_state.atom_graphics_state.atom_items[f["ar"]].hide()
        scope = "sheet"
    else:
        f["canvas"].runtime_state.note_items()[1].setSelected(True)
        scope = "selection"
    output = tmp_path / "refused.cdxml"
    messages = _export(f, monkeypatch, output, scope)
    messages.warning.assert_called_once()
    assert "hidden or outside" in messages.warning.call_args.args[2]
    assert not output.exists()


def test_prepared_snapshot_does_not_re_read_mutated_live_context(
    saved_contacts, monkeypatch, tmp_path
):
    f = saved_contacts
    original = tmp_path / "original.cdxml"
    _export(f, monkeypatch, original).warning.assert_not_called()
    prepared = f["service"]._reviewed_cdxml_snapshot(
        f["window"], str(f["sidecar"]), scope="sheet"
    )
    f["canvas"].model.atoms[f["ar"]].x += 100
    f["canvas"].model.bonds[1] = None
    f["payload"]["documentary_contacts"].clear()
    snapshot_result = tmp_path / "snapshot.cdxml"
    prepared.export(
        str(snapshot_result),
        dpi=300,
        background="white",
        sizing="custom",
        target_width_mm=170,
        max_height_mm=None,
        min_font_pt=None,
    )
    assert snapshot_result.read_bytes() == original.read_bytes()
    # A new GUI request must still refuse the now-dirty editor.
    dirty_result = tmp_path / "dirty.cdxml"
    _export(f, monkeypatch, dirty_result).warning.assert_called_once()
    assert not dirty_result.exists()


@pytest.mark.parametrize("membership", ["atom", "note", "outside"])
def test_saved_groups_keep_scope_aware_refusal(
    saved_contacts, monkeypatch, tmp_path, membership
):
    from chemvas.ui.canvas.canvas_group_state import register_group_for

    f = saved_contacts
    canvas = f["canvas"]
    notes = canvas.runtime_state.note_state.order
    if membership == "atom":
        register_group_for(canvas, {f["ar"]}, [])
    elif membership == "note":
        register_group_for(canvas, set(), [notes[0]])
    else:
        register_group_for(canvas, {70, 71}, [notes[1]])
    assert f["service"].save_canvas_to_path(
        f["window"], str(f["source"]), message_box=Mock()
    )
    source_bytes = f["source"].read_bytes()
    f["payload"]["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    f["sidecar"].write_text(json.dumps(f["payload"]))
    results = []
    for stage in ("immediate", "reopened"):
        _select_contacts(f)
        target = tmp_path / (stage + ".cdxml")
        messages = _export(f, monkeypatch, target, "selection")
        if membership == "outside":
            messages.warning.assert_not_called()
            results.append(target.read_bytes())
        else:
            messages.warning.assert_called_once()
            assert "group" in messages.warning.call_args.args[2]
            assert not target.exists()
        assert f["source"].read_bytes() == source_bytes
        if stage == "immediate":
            f["window"].close()
            window = build_main_window()
            f["windows"].append(window)
            assert f["service"].load_canvas_from_path(window, str(f["source"]))
            f["window"] = window
            f["canvas"] = active_canvas_for_window(window)
    if results:
        assert results[0] == results[1]


@pytest.mark.parametrize("include_unknown", [False, True])
def test_only_requested_scope_requires_saved_graphic_references(
    saved_contacts, monkeypatch, tmp_path, include_unknown
):
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

    f = saved_contacts
    item = QGraphicsRectItem(500, 200, 10, 10)
    item.setData(0, "unsupported_graphic")
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
    f["canvas"].scene().addItem(item)
    _select_contacts(f)
    item.setSelected(include_unknown)
    output = tmp_path / "selected.cdxml"
    messages = _export(f, monkeypatch, output, "selection")
    if include_unknown:
        messages.warning.assert_called_once()
        assert "saved document reference" in messages.warning.call_args.args[2]
        assert not output.exists()
    else:
        messages.warning.assert_not_called()
        assert output.exists()
