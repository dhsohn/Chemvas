"""Explicitly unspecified double bonds remain distinct in editable drawings."""

import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QLineF, QPointF, Qt
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document, write_document
from chemvas.core.molfile import parse_molfile, write_molfile
from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    deserialize_model_state,
    serialize_model_state_with_warnings,
    validate_clipboard_selection_payload,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.select_all_access import select_all_scene_items_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()


def _composition(order=2):
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [
            {"id": 0, "element": "C", "x": 0, "y": 0},
            {"id": 1, "element": "C", "x": 30, "y": 0},
        ],
        "bonds": [{"a": 0, "b": 1, "order": order, "style": "double_either"}],
    }


def test_serializer_preserves_explicit_unspecified_double_without_repairs():
    model = MoleculeModel(
        atoms={0: Atom("C", 0, 0), 1: Atom("C", 30, 0)},
        bonds=[Bond(0, 1, 2, "double_either")],
    )
    state, warnings = serialize_model_state_with_warnings(model)
    assert state["bonds"][0]["style"] == "double_either"
    assert warnings == []


def test_composition_and_native_accept_only_order_two():
    state = compose_document_state(_composition())
    assert (
        build_document_payload(state, CANVAS_FILE_VERSION)["state"]["model"]
        == state["model"]
    )
    for order in (1, 3):
        with pytest.raises(ValueError, match="order 2"):
            compose_document_state(_composition(order))
        invalid = deepcopy(state)
        invalid["model"]["bonds"][0]["order"] = order
        with pytest.raises(ValueError):
            build_document_payload(invalid, CANVAS_FILE_VERSION)


@pytest.mark.parametrize("order", [1, 2, 3])
def test_graph_patch_validates_unspecified_double_order(order):
    raw = _composition()
    raw["bonds"][0]["style"] = "double"
    state = compose_document_state(raw)
    request = {
        "format": "chemvas-graph-patch",
        "version": 1,
        "source_sha256": "a" * 64,
        "operations": [
            {
                "op": "update_bond",
                "a": 0,
                "b": 1,
                "changes": {"order": order, "style": "double_either"},
            }
        ],
    }
    if order != 2:
        with pytest.raises(ValueError, match="order 2"):
            apply_document_patch(
                state,
                request,
                source_sha256="a" * 64,
                document_version=CANVAS_FILE_VERSION,
            )
    else:
        result = apply_document_patch(
            state, request, source_sha256="a" * 64, document_version=CANVAS_FILE_VERSION
        )
        assert result.state["model"]["bonds"][0]["style"] == "double_either"


def test_canvas_draws_crossed_lines_instead_of_parallel_lines(canvas):
    # Bypass composition so this regression also independently exercises paint.
    raw = _composition()
    raw["bonds"][0]["style"] = "double"
    state = compose_document_state(raw)
    state["model"]["bonds"][0]["style"] = "double_either"
    canvas.services.document.canvas_document_session_service.apply_state(state)
    first, second = [item.line() for item in bond_items_for_id(canvas, 0)]
    kind, crossing = first.intersects(second)
    assert kind == QLineF.IntersectionType.BoundedIntersection
    assert crossing == QPointF(15, 0)


@pytest.mark.parametrize("end", [(8, 0), (0, 8), (5, 5), (-8, 0)])
def test_fully_label_trimmed_double_does_not_gain_a_crossbar(canvas, end):
    raw = _composition()
    for atom in raw["atoms"]:
        atom["element"] = "O"
    raw["atoms"][1].update(x=end[0], y=end[1])
    canvas.services.document.canvas_document_session_service.apply_state(
        compose_document_state(raw)
    )
    assert all(item.line().isNull() for item in bond_items_for_id(canvas, 0))


def _lines(canvas):
    return [
        (item.line().x1(), item.line().y1(), item.line().x2(), item.line().y2())
        for item in bond_items_for_id(canvas, 0)
    ]


def test_native_editable_svg_clipboard_and_history_preserve_unknown(canvas, tmp_path):
    documents = canvas.services.document.canvas_document_session_service
    documents.apply_state(compose_document_state(_composition()))
    before = documents.snapshot_state()
    expected_lines = _lines(canvas)
    document = tmp_path / "unspecified.chemvas"
    write_document(document, before, version=CANVAS_FILE_VERSION)
    restored = read_document(document).state
    assert restored == json.loads(json.dumps(before))
    assert restored["model"]["bonds"][0]["style"] == "double_either"
    documents.apply_state(restored)
    assert documents.snapshot_state() == before
    assert _lines(canvas) == expected_lines

    svg = tmp_path / "editable.svg"
    documents.export_figure(str(svg), fmt="svg", editable_svg=True)
    svg_state = extract_chemvas_document_from_svg(svg).state
    assert svg_state == json.loads(json.dumps(before))
    documents.apply_state(svg_state)
    assert _lines(canvas) == expected_lines

    select_all_scene_items_for(canvas)
    clipboard = canvas.services.scene_operations.scene_clipboard_controller
    payload = clipboard.selection_payload_for_clipboard()
    assert validate_clipboard_selection_payload(payload)
    assert payload["version"] == 2
    assert payload["bonds"][0]["style"] == "double_either"
    invalid = deepcopy(payload)
    invalid["bonds"][0]["order"] = 1
    assert not validate_clipboard_selection_payload(invalid)
    assert clipboard.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    after = documents.snapshot_state()
    assert len(after["model"]["bonds"]) == 2
    assert {bond["style"] for bond in after["model"]["bonds"]} == {"double_either"}
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == after


@pytest.mark.parametrize("style", ["double", "bold_in", "dotted_double"])
@pytest.mark.parametrize("reverse", [False, True])
def test_atom_merge_retains_unknown_over_same_order_display_style(
    canvas, style, reverse
):
    raw = _composition()
    raw["atoms"].append({"id": 2, "element": "C", "x": 0.2, "y": 0.2})
    raw["bonds"].insert(0, {"a": 2, "b": 1, "order": 2, "style": style})
    if reverse:
        raw["bonds"].reverse()
    canvas.services.document.canvas_document_session_service.apply_state(
        compose_document_state(raw)
    )
    merged, info = canvas.services.atom_label_service.merge_overlapping_atoms(0)
    assert merged == [2]
    assert len(info["deleted_bond_ids"]) == 1
    remaining = [bond for bond in canvas.model.bonds if bond is not None]
    assert len(remaining) == 1
    assert remaining[0].style == "double_either"


def test_desktop_mol_import_edit_undo_and_export(app, tmp_path, monkeypatch):
    state = compose_document_state(_composition())
    path = tmp_path / "external.mol"
    path.write_text(write_molfile(deserialize_model_state(state["model"])))
    original_bytes = path.read_bytes()
    window = build_main_window()
    window.resize(1100, 800)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    services = services_for_window(window)
    try:
        assert services.document_action_service.load_canvas_from_path(window, str(path))
        canvas = active_canvas_for_window(window)
        documents = canvas.services.document.canvas_document_session_service
        before = documents.snapshot_state()
        assert canvas.model.bonds[0].style == "double_either"
        first, second = [item.line() for item in bond_items_for_id(canvas, 0)]
        assert (
            first.intersects(second)[0] == QLineF.IntersectionType.BoundedIntersection
        )
        canvas.centerOn(first.center())
        canvas.setFocus()
        app.processEvents()
        position = canvas.mapFromScene(first.center())
        global_position = canvas.viewport().mapToGlobal(position)
        monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: global_position))
        QApplication.sendEvent(
            canvas.viewport(),
            QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(position),
                QPointF(global_position),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        # An explicit bond-type choice can remove unknown stereo; Undo restores it.
        QTest.keyClick(canvas, Qt.Key.Key_2)
        assert canvas.model.bonds[0].style == "double"
        canvas.services.history_service.undo()
        assert documents.snapshot_state() == before
        output = tmp_path / "exported.mol"
        documents.export_mol(str(output))
        assert parse_molfile(output.read_text()).bonds[0].style == "double_either"
        assert path.read_bytes() == original_bytes
    finally:
        services.canvas_document_service.mark_clean(active_canvas_for_window(window))
        window.close()
        app.processEvents()
