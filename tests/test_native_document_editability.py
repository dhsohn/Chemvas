from __future__ import annotations

import json
import os
from contextlib import contextmanager

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_scene_items_state import note_items_for, selected_notes_for
from chemvas.ui.canvas_service_ports import canvas_window_document_session_service
from chemvas.ui.layout_qa_service import check_canvas_layout
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def write_synthetic_native(path, *, outside=False):
    if outside:
        composition = {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": 1000.0, "y": 0.0},
                {"id": 1, "element": "C", "x": 1040.0, "y": 0.0},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
        }
    else:
        composition = {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": -80.0, "y": 0.0},
                {"id": 1, "element": "OMe", "x": -40.0, "y": 0.0},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
            "notes": [
                {"text": "Editable caption", "x": -95.0, "y": 55.0},
            ],
            "arrows": [
                {
                    "kind": "arrow",
                    "start": [40.0, 0.0],
                    "end": [100.0, 0.0],
                    "labels": {"above": "THF"},
                },
            ],
        }
    state = compose_document_state(composition)
    if not outside:
        state["groups"] = [{"atoms": [0, 1], "items": [["notes", 0]]}]
    # Save a canonical native fixture through the same scene/document session
    # writer used by the GUI; subsequent opens must not reflow its geometry.
    with offscreen_canvas(state, command="native-editability-fixture") as (
        _canvas,
        session,
    ):
        assert not session.save_to_file(str(path))
    return read_document(path)


def snapshot(canvas):
    state, warnings = canvas_window_document_session_service(
        canvas
    ).snapshot_state_with_warnings()
    assert not warnings
    return json.loads(json.dumps(state))


def editing_content(state):
    # Qt may canonicalize paragraph CSS on its first document read. This
    # contract pins actual drawing coordinates/text, not equivalent HTML syntax.
    return {
        "model": state["model"],
        "groups": state.get("groups", []),
        "arrows": state["arrows"],
        "notes": [
            {key: note[key] for key in ("text", "x", "y")} for note in state["notes"]
        ],
    }


@contextmanager
def opened_native(path):
    window = build_main_window()
    window.resize(1120, 760)
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowExposed(window, 5000)
    if QApplication.platformName() != "offscreen":
        assert QTest.qWaitForWindowActive(window, 5000)
    actions = services_for_window(window).document_action_service
    assert actions.load_canvas_from_path(window, str(path))
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 200)
    canvas.centerOn(0.0, 0.0)
    QApplication.processEvents()
    QTest.qWait(30)
    try:
        yield window, canvas, actions
    finally:
        canvas.scene().clearFocus()
        services_for_window(window).canvas_document_service.mark_clean(canvas)
        window.close()
        QApplication.processEvents()
        QTest.qWait(20)


def click_tool(window, name):
    action = tool_action_for_window(window, name)
    button = next(
        button
        for button in window.findChildren(QToolButton)
        if button.defaultAction() is action
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def click_scene(canvas, point):
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(point)
    )
    QApplication.processEvents()


def key(canvas, value, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(canvas, value, modifiers)
    QApplication.processEvents()


def redo(canvas):
    # The native Wayland theme uses Ctrl+Shift+Z; offscreen may use Ctrl+Y.
    # Exercise the platform's actual shortcut, not a direct history mutation.
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
    QApplication.processEvents()


def exercise_saved_editable_document(directory, *, capture=False):
    original_path = directory / "original.chemvas"
    edited_path = directory / "edited.chemvas"
    original = write_synthetic_native(original_path)
    original_bytes = original_path.read_bytes()
    original_mtime = original_path.stat().st_mtime_ns
    with opened_native(original_path) as (window, canvas, actions):
        loaded = snapshot(canvas)
        assert editing_content(loaded) == editing_content(original.state)
        assert check_canvas_layout(canvas, sheet_only=True)["ok"]
        click_tool(window, "select")
        origin = canvas.mapFromScene(QPointF(-60.0, 0.0))
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=origin)
        QApplication.processEvents()
        assert note_items_for(canvas)[0] in selected_notes_for(canvas)
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=origin)
        QTest.mouseMove(canvas.viewport(), origin + QPoint(40, 20), 30)
        QTest.mouseRelease(
            canvas.viewport(), Qt.MouseButton.LeftButton, pos=origin + QPoint(40, 20)
        )
        QApplication.processEvents()
        dragged = snapshot(canvas)
        for atom_id, atom in loaded["model"]["atoms"].items():
            moved = dragged["model"]["atoms"][atom_id]
            assert moved["x"] == pytest.approx(atom["x"] + 20.0)
            assert moved["y"] == pytest.approx(atom["y"] + 10.0)
        assert dragged["notes"][0]["x"] == pytest.approx(-75.0)
        assert dragged["notes"][0]["y"] == pytest.approx(65.0)
        assert dragged["arrows"] == loaded["arrows"]
        assert dragged["groups"] == loaded["groups"]
        key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert editing_content(snapshot(canvas)) == editing_content(loaded)
        redo(canvas)
        assert editing_content(snapshot(canvas)) == editing_content(dragged)

        click_tool(window, "note")
        note = note_items_for(canvas)[0]
        click_scene(canvas, note.sceneBoundingRect().center())
        assert note.hasFocus()
        key(canvas, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(canvas, " revised")
        assert note.toPlainText() == "Editable caption revised"
        key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert note.toPlainText() == "Editable caption"
        redo(canvas)
        assert note.toPlainText() == "Editable caption revised"
        click_tool(window, "select")
        click_scene(canvas, QPointF(180.0, 120.0))
        committed = snapshot(canvas)
        key(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert editing_content(snapshot(canvas)) == editing_content(dragged)
        redo(canvas)
        assert editing_content(snapshot(canvas)) == editing_content(committed)
        assert check_canvas_layout(canvas, sheet_only=True)["ok"]
        assert actions.save_canvas_to_path(window, str(edited_path))
        assert not window.isWindowModified()
        saved = read_document(edited_path)
        assert editing_content(saved.state) == editing_content(committed)
        if capture:
            assert window.grab().save(str(directory / "edited_window.png"))

    with opened_native(edited_path) as (window, canvas, _actions):
        reopened = snapshot(canvas)
        assert editing_content(reopened) == editing_content(saved.state)
        assert check_canvas_layout(canvas, sheet_only=True)["ok"]
        if capture:
            assert window.grab().save(str(directory / "reopened_window.png"))
    assert original_path.read_bytes() == original_bytes
    assert original_path.stat().st_mtime_ns == original_mtime
    return {
        "source_model": original.state["model"],
        "saved_model": saved.state["model"],
        "saved_note": saved.state["notes"][0]["text"],
        "groups_preserved": saved.state["groups"] == original.state["groups"],
        "ungrouped_arrow_preserved": saved.state["arrows"] == original.state["arrows"],
        "source_file_unchanged": True,
        "drag_undo_redo": True,
        "text_undo_redo_and_committed_undo_redo": True,
        "saved_reopened_content_exact": True,
    }


def test_saved_outside_molecular_bond_is_rejected_without_open_normalization(tmp_path):
    path = tmp_path / "outside.chemvas"
    original = write_synthetic_native(path, outside=True)
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns
    with opened_native(path) as (_window, canvas, _actions):
        loaded = snapshot(canvas)
        assert editing_content(loaded) == editing_content(original.state)
        before_check = snapshot(canvas)
        report = check_canvas_layout(canvas, sheet_only=True)
        assert not report["ok"]
        assert report["counts"]["outside-sheet"] >= 1
        assert snapshot(canvas) == before_check
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime


def test_saved_in_sheet_document_supports_real_edit_undo_save_reopen(tmp_path):
    report = exercise_saved_editable_document(tmp_path)
    assert report["saved_note"] == "Editable caption revised"
