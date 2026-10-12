from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest import mock

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor, QTextDocument
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from chemvas.bootstrap.file_open import open_document
from chemvas.core.document_io import read_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    deserialize_model_state,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch
from chemvas.shell.window_registry import open_windows
from chemvas.ui.transactions.document import DocumentSavepoint
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.canvas_factory import build_canvas_view
from tests.gui_workflow_support import _click, _tool
from tests.gui_workflow_support import qt_errors as qt_errors


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


def _state(atoms, bonds=(), **fields):
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": index, "element": element, "x": x, "y": y}
                for index, (element, x, y) in enumerate(atoms)
            ],
            "bonds": [{"a": a, "b": b, "order": 1} for a, b in bonds],
            **fields,
        }
    )


def _patch(state, *operations):
    return apply_document_patch(
        state,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": "a" * 64,
            "operations": list(operations),
        },
        source_sha256="a" * 64,
        document_version=CANVAS_FILE_VERSION,
    ).payload["state"]


@pytest.mark.parametrize(
    ("atoms", "bonds", "settings"),
    [
        ([("C", 100, 100), ("O", 100, 100), ("C", 120, 100)], [(0, 2), (1, 2)], {}),
        ([("C", 72, 72), ("O", 92, 72)], [(0, 1)], {"bond_length_px": 400}),
        ([("N", 100, 100), ("O", 100, 100)], [], {}),
    ],
)
def test_open_and_save_preserve_overlapping_atoms(
    canvas, tmp_path, atoms, bonds, settings
):
    state = _state(atoms, bonds, settings=settings)
    original = deepcopy(state)
    documents = canvas.services.canvas_document_session_service

    documents.apply_state(state)
    output = tmp_path / "reopened.chemvas"
    assert documents.save_to_file(str(output)) == []

    assert state == original
    assert deserialize_model_state(
        read_document(output).state["model"]
    ) == deserialize_model_state(state["model"])
    documents.apply_state(read_document(output).state)
    assert documents.snapshot_state()["model"] == state["model"]


@pytest.mark.parametrize(
    ("bond", "removed_atoms"),
    [((0, 1), [0]), ((1, 2), []), ((3, 4), [4]), ((5, 6), [5]), ((7, 8), [7, 8])],
    ids=[
        "bare_carbon",
        "ring_member",
        "labelled_endpoint",
        "marked_endpoint",
        "both_endpoints",
    ],
)
def test_desktop_and_patch_bond_deletion_leave_the_same_document(
    canvas, bond, removed_atoms
):
    # A chain 0-1 into a ring 1-2-3, N-C at 3-4, and a marked carbon at 5-6.
    # Only 3 (a heteroatom) and 6 (marked) can stay when their bond goes.
    state = _state(
        [
            ("C", 60, 100),
            ("C", 80, 100),
            ("C", 100, 100),
            ("N", 90, 120),
            ("C", 110, 140),
            ("C", 200, 100),
            ("C", 220, 100),
            ("C", 300, 100),
            ("C", 320, 100),
        ],
        [(0, 1), (1, 2), (2, 3), (3, 1), (3, 4), (5, 6), (7, 8)],
    )
    state["ring_fills"] = [
        {
            "points": [[80, 100], [100, 100], [90, 120]],
            "atom_ids": [1, 2, 3],
            "color": "#ff0000",
            "alpha": 0.3,
        }
    ]
    state["marks"] = [
        {
            "kind": "radical",
            "text": None,
            "atom_id": 6,
            "dx": None,
            "dy": None,
            "x": 224,
            "y": 94,
        }
    ]
    state["groups"] = [{"atoms": [0, 2], "items": []}, {"atoms": [7], "items": []}]
    state["perspective"] = {
        "atom_coords_3d": {
            str(i): [x, y, 0]
            for i, (x, y) in enumerate(
                [
                    (60, 100),
                    (80, 100),
                    (100, 100),
                    (90, 120),
                    (110, 140),
                    (200, 100),
                    (220, 100),
                    (300, 100),
                    (320, 100),
                ]
            )
        },
        "projection_center_3d": [100, 100, 0],
        "projection_anchor_2d": [100, 100],
    }
    original = deepcopy(state)

    patched = _patch(state, {"op": "remove_bond", "a": bond[0], "b": bond[1]})
    assert state == original

    documents = canvas.services.canvas_document_session_service
    documents.apply_state(deepcopy(state))
    model = canvas.model
    bond_id = next(
        index
        for index, item in enumerate(model.bonds)
        if item is not None and {item.a, item.b} == set(bond)
    )
    controller = canvas.services.scene_delete_controller
    assert controller.delete_bond(bond_id, record=True) is not None
    desktop = documents.snapshot_state()

    for atom_id in removed_atoms:
        assert atom_id not in patched["model"]["atoms"]
    # The desktop snapshot spells points as float tuples; JSON is the shared
    # form both paths publish, so compare through it.
    desktop, patched = _json_form(desktop), _json_form(patched)
    for key in ("model", "ring_fills", "marks"):
        assert desktop[key] == patched[key], key
    # Emptied collections are omitted by both, so compare presence too.
    assert desktop.get("groups") == patched.get("groups")
    assert ("perspective" in desktop) == ("perspective" in patched)
    assert desktop.get("perspective", {}).get("atom_coords_3d") == patched.get(
        "perspective", {}
    ).get("atom_coords_3d")


def _json_form(state):
    return json.loads(json.dumps(state))


def test_patch_move_preserves_projected_depth_through_desktop_save(canvas, tmp_path):
    state = _state([("C", 100, 100), ("C", 120, 100)], [(0, 1)])
    state["perspective"] = {
        "atom_coords_3d": {"0": [100, 100, 0], "1": [112.5, 100, 60]},
        "projection_center_3d": [100, 100, 0],
        "projection_anchor_2d": [100, 100],
    }
    patched = _patch(state, {"op": "move_atom", "atom_id": 1, "x": 130, "y": 100})
    assert patched["perspective"]["atom_coords_3d"]["1"] == [118.75, 100, 60]

    documents = canvas.services.canvas_document_session_service
    documents.apply_state(patched)
    output = tmp_path / "perspective.chemvas"
    assert documents.save_to_file(str(output)) == []
    assert read_document(output).state["perspective"] == patched["perspective"]


def test_paste_overlapping_heteroatom_preserves_original_and_undo(canvas):
    state = _state([("C", 100, 100), ("N", 120, 100)], [(0, 1)])
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(state)
    before = documents.snapshot_state()
    payload = {
        "format": "chemvas-selection",
        "version": 2,
        "atoms": [
            {"id": 0, "element": "C", "x": 82, "y": 82},
            {"id": 1, "element": "O", "x": 102, "y": 82},
        ],
        "bonds": [{"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"}],
        "rings": [],
        "marks": [],
        "scene_items": [],
    }
    controller = canvas.services.scene_clipboard_controller
    assert controller.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, "overlapping-paste")
    )

    after = documents.snapshot_state()
    assert len(canvas.model.atoms) == 4
    assert canvas.model.atoms[1].element == "N"
    assert canvas.model.bonds[0].a == 0 and canvas.model.bonds[0].b == 1
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == after


@pytest.fixture
def document_windows(app, qt_errors):
    yield
    for window in list(open_windows()):
        services = window.services
        for canvas in window.tab_references.all_canvases():
            canvas.services.tool_controller.prepare_for_document_edit()
            canvas.scene().clearFocus()
            services.canvas_document_service.mark_clean(canvas)
        window.close()
    app.processEvents()
    assert not qt_errors


def _html_text_and_formats(html):
    document = QTextDocument()
    document.setHtml(html)
    cursor = QTextCursor(document)
    formats = []
    for position in range(document.characterCount() - 1):
        cursor.setPosition(position)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
        )
        char = cursor.charFormat()
        formats.append(
            (
                cursor.selectedText(),
                char.fontWeight(),
                char.fontItalic(),
                char.fontUnderline(),
                char.fontStrikeOut(),
                char.verticalAlignment(),
                char.foreground().color().name(),
                char.anchorHref(),
            )
        )
    return document.toPlainText(), formats


def _assert_frozen_v7_content(literal_state, live_state):
    expected = deepcopy(literal_state)
    expected["last_smiles_input"] = None
    # Native JSON represents atom IDs as strings and coordinates as arrays.
    actual = json.loads(json.dumps(live_state))
    for arrow in expected["arrows"]:
        arrow.setdefault("control", None)
        arrow.setdefault("double", False)
    # Shapes are saved from their records, so the opacity comes back as the
    # document stated it, not as QColor's 16-bit read-back of it.
    for before, after in zip(expected["notes"], actual["notes"], strict=True):
        # Qt and the existing HTML sanitizer canonicalize markup, not its text
        # or per-character formatting. No other frozen field is discarded.
        assert _html_text_and_formats(before["html"]) == _html_text_and_formats(
            after["html"]
        )
        before["html"] = after["html"]
    assert actual == expected


@pytest.mark.parametrize("name", ["minimal", "extended"])
def test_frozen_v7_gui_open_edit_undo_save_as_and_reopen(
    app, document_windows, tmp_path, name
):
    source = Path(__file__).parent / "fixtures" / "document-v7" / f"{name}.chemvas"
    original_bytes = source.read_bytes()
    literal = json.loads(original_bytes)
    assert literal["version"] == 7
    with (
        mock.patch.object(
            QMessageBox,
            "warning",
            side_effect=AssertionError("unexpected document warning"),
        ),
        mock.patch.object(
            QMessageBox,
            "question",
            side_effect=AssertionError("unexpected document confirmation"),
        ),
    ):
        # The application File Open entry reads the fixed file, not a document
        # generated with the current writer in test setup.
        open_document(str(source))
        assert len(open_windows()) == 1
        window = open_windows()[0]
        window.resize(1120, 700)
        window.activateWindow()
        assert QTest.qWaitForWindowExposed(window, 5000)
        assert QTest.qWaitForWindowActive(window, 5000)
        canvas = active_canvas_for_window(window)
        canvas.centerOn(0, 0)
        app.processEvents()
        services = window.services
        documents = canvas.services.canvas_document_session_service
        before = documents.snapshot_state()
        _assert_frozen_v7_content(literal["state"], before)
        assert services.canvas_document_service.file_path(canvas) == str(source)
        assert not services.canvas_document_service.is_dirty(canvas)
        history = canvas.services.history_service
        stacks = history.capture_stack_snapshot()

        _tool(window, "note")
        _click(canvas, QPointF(-100, -100))
        QTest.keyClicks(canvas, "v7 compatibility edit")
        _tool(window, "select")
        canvas.scene().clearFocus()
        app.processEvents()
        after = documents.snapshot_state()
        assert len(after["notes"]) == len(before["notes"]) + 1
        assert after["notes"][-1]["text"] == "v7 compatibility edit"
        without_edit = deepcopy(after)
        without_edit["notes"].pop()
        assert without_edit == before
        command = history.capture_stack_snapshot().history[-1]
        history.verify_stack_snapshot(stacks, history=(*stacks.history, command))
        assert services.canvas_document_service.is_dirty(canvas)
        QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert documents.snapshot_state() == before
        assert not services.canvas_document_service.is_dirty(canvas)
        history.redo()
        assert documents.snapshot_state() == after

        destination = tmp_path / f"{name}-edited.chemvas"
        file_menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.text() == "File"
        )
        with mock.patch.object(
            QFileDialog, "getSaveFileName", return_value=(str(destination), "")
        ) as chooser:
            next(
                action
                for action in file_menu.actions()
                if action.text() == "Save As..."
            ).trigger()
        chooser.assert_called_once()
        saved = read_document(destination)
        assert json.loads(destination.read_bytes())["version"] == CANVAS_FILE_VERSION
        assert json.loads(json.dumps(saved.state)) == json.loads(json.dumps(after))
        assert not services.canvas_document_service.is_dirty(canvas)
        assert services.canvas_document_service.file_path(canvas) == str(destination)
        window.close()
        app.processEvents()
        assert not open_windows()
        open_document(str(destination))
        assert len(open_windows()) == 1
        reopened = active_canvas_for_window(open_windows()[0])
        assert reopened is not canvas
        assert (
            reopened.services.canvas_document_session_service.snapshot_state() == after
        )
    assert source.read_bytes() == original_bytes


def test_graph_service_follows_document_replacement(canvas):
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(_state([("C", 0, 0), ("N", 30, 0)], [(0, 1)]))
    graph = canvas.services.graph_service
    original_model = canvas.model
    assert graph.bond_id_between(0, 1) == 0
    documents.apply_state(_state([("O", 0, 0), ("N", 30, 0), ("C", 60, 0)], [(0, 2)]))
    assert canvas.services.graph_service is graph
    assert canvas.model is not original_model
    assert graph.bond_id_between(0, 1) is None
    assert graph.bond_id_between(0, 2) == 0
    assert graph.connected_components({0, 1, 2}) == [{0, 2}, {1}]
    assert original_model.bond_for_id(0).b == 1


def test_render_services_follow_replaced_model(canvas):
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(_state([("C", 0, 0), ("C", 30, 0), ("C", 15, 30)], []))
    old_model = canvas.model
    bonds = canvas.services.canvas_bond_mutation_service
    rings = canvas.services.canvas_ring_fill_scene_service
    documents.apply_state(_state([("N", 60, 60), ("C", 90, 60), ("O", 75, 90)], []))
    bond_id = bonds.add_bond(0, 1)
    assert canvas.model.bond_for_id(bond_id) is not None
    assert not old_model.bonds
    ring = rings.create_ring_fill_item(
        [QPointF(60, 60), QPointF(90, 60), QPointF(75, 90)], [0, 1, 2]
    )
    canvas.model.atom_for_id(0).x = 65
    rings.update_ring_fills_for_atoms({0}, ring_items=(ring,))
    polygon = ring.polygon()
    assert polygon[0] == QPointF(65, 60)
    assert old_model.atom_for_id(0).x == 0
    bonds.remove_bond_by_id(bond_id)
    assert canvas.model.bond_for_id(bond_id) is None
    assert not old_model.bonds


def test_shortcuts_follow_replaced_model_through_saved_reopen(canvas, tmp_path):
    documents = canvas.services.canvas_document_session_service
    shortcuts = canvas.services.chemdraw_shortcut_service
    documents.apply_state(_state([("C", 0, 0), ("C", 30, 0)], [(0, 1)]))
    old_model = canvas.model
    documents.apply_state(_state([("N", 0, 0), ("O", 30, 0)], [(0, 1)]))
    before = documents.snapshot_state()
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.NoModifier, "3"
    )
    assert shortcuts.handle_bond_hotkey(event, 0)
    after = documents.snapshot_state()
    assert canvas.model.bond_for_id(0).order == 3
    assert old_model.bond_for_id(0).order == 1
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == after

    output = tmp_path / "shortcut-edited.chemvas"
    assert documents.save_to_file(str(output)) == []
    saved = read_document(output).state
    assert _json_form(saved) == _json_form(after)
    saved_model = canvas.model
    documents.apply_state(saved)
    assert canvas.model is not saved_model
    assert canvas.services.chemdraw_shortcut_service is shortcuts
    assert documents.snapshot_state() == after
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    assert not stacks.history and not stacks.redo_stack

    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.NoModifier, "2"
    )
    # Reopening replaces the model and clears history, while the same edit
    # services remain. Each subsequent operation owns one exact savepoint.
    with mock.patch.object(
        DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
    ) as captures:
        assert shortcuts.handle_bond_hotkey(event, 0)
        assert captures.call_count == 1
        edited_again = documents.snapshot_state()
        assert canvas.model.bond_for_id(0).order == 2
        assert saved_model.bond_for_id(0).order == 3
        assert old_model.bond_for_id(0).order == 1

        captures.reset_mock()
        history.undo()
        assert captures.call_count == 1
        assert documents.snapshot_state() == after
        captures.reset_mock()
        history.redo()
        assert captures.call_count == 1
        assert documents.snapshot_state() == edited_again

        # This shortcut is valid only for the live order-2 bond. Both retired
        # models have another order, so a stale provider would reject it.
        position_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier, "c"
        )
        captures.reset_mock()
        assert shortcuts.handle_bond_hotkey(position_event, 0)
        assert captures.call_count == 1
        assert canvas.model.bond_for_id(0).style == "double_center"
        history.undo()
        assert documents.snapshot_state() == edited_again
    assert read_document(output).state == saved
