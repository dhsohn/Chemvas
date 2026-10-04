"""Mark edits on a loaded annotation-only atom undo to the exact document.

Covers the charge shortcuts and Mark tool clicks.
"""

import json
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.window.main_window_config import MARK_TOOL_ACTION_SPECS
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    set_zoom_percent_for_window,
)

# Nitromethane drawn as charge-separated N+ / O- annotations with no marks.
POSITIONS = {10: (-40.0, 0.0), 11: (0.0, 0.0), 12: (20.0, -34.64), 13: (20.0, 34.64)}
LOADED_ANNOTATIONS = {11: {"formal_charge": 1}, 13: {"formal_charge": -1}}
# The annotation an atom carrying one mark of each kind has.
MARK_ANNOTATIONS = {
    "plus": {"formal_charge": 1},
    "minus": {"formal_charge": -1},
    "radical": {"radical_electrons": 1},
}


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def _write_nitromethane(path):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "C", "x": 0.0, "y": 0.0}],
            "bonds": [],
        }
    )
    model = MoleculeModel(
        atoms={
            atom_id: Atom(element, *POSITIONS[atom_id])
            for atom_id, element in ((10, "C"), (11, "N"), (12, "O"), (13, "O"))
        },
        bonds=[Bond(10, 11), Bond(11, 12, 2, "double"), Bond(11, 13)],
        atom_annotations={
            atom_id: dict(annotation)
            for atom_id, annotation in LOADED_ANNOTATIONS.items()
        },
    )
    state["model"] = serialize_model_state(model)
    assert state["marks"] == []
    write_document(path, state, CANVAS_FILE_VERSION)
    return read_document(path).state


@pytest.fixture
def loaded(app, tmp_path):
    from chemvas.bootstrap.main_window import build_main_window

    path = tmp_path / "nitromethane.chemvas"
    original = _write_nitromethane(path)
    window = build_main_window()
    window.resize(1150, 780)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    actions = window.services.document_action_service
    assert actions.load_canvas_from_path(window, str(path))
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 220)
    canvas.centerOn(0, 0)
    _tool(window, "select")
    app.processEvents()
    yield window, canvas, original
    canvas = active_canvas_for_window(window)
    canvas.scene().clearFocus()
    window.services.canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _tool(window, name):
    action = window.ui_references.tool_action_for_key(name)
    button = next(
        item
        for item in window.findChildren(QToolButton)
        if item.defaultAction() is action
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _hover_key(canvas, atom_id, key):
    viewport = canvas.viewport()
    position = canvas.mapFromScene(QPointF(*POSITIONS[atom_id]))
    global_position = viewport.mapToGlobal(position)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(position),
        QPointF(global_position),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Deliver the real widget move, and keep the key handler's cursor sample
    # at that position; hover and shortcut owners still decide the edit.
    original_cursor_sampler = QCursor.pos
    with patch("chemvas.ui.tools.hover.QCursor.pos", return_value=global_position):
        QApplication.sendEvent(viewport, event)
        QTest.keyClick(viewport, key)
    assert QCursor.pos == original_cursor_sampler
    QApplication.processEvents()


def _mark_tool(window, canvas, kind):
    _tool(window, "mark")
    tooltip = next(spec[4] for spec in MARK_TOOL_ACTION_SPECS if spec[2] == kind)
    button = next(
        item
        for item in window.findChildren(QToolButton)
        if item.toolTip() == tooltip and item.isVisible()
    )
    assert button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert canvas.runtime_state.tool_settings_state.mark_kind == kind


def _click_atom(canvas, atom_id):
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.mapFromScene(QPointF(*POSITIONS[atom_id])),
    )
    QApplication.processEvents()


def _snapshot(canvas):
    return canvas.services.canvas_document_session_service.snapshot_state()


def _loaded_snapshot(canvas, original):
    history = canvas.services.history_service
    assert not history.state.history and not history.state.redo_stack
    before = _snapshot(canvas)
    assert before["marks"] == []
    assert before["model"]["atom_annotations"] == LOADED_ANNOTATIONS
    assert (
        json.loads(json.dumps(before["model"]["atom_annotations"]))
        == original["model"]["atom_annotations"]
    )
    return before


def _assert_saved(window, path, expected, original):
    assert window.services.document_action_service.save_canvas_to_path(
        window, str(path)
    )
    saved = read_document(path).state
    assert saved == json.loads(json.dumps(expected))
    return saved


@pytest.mark.parametrize(
    ("atom_id", "key", "kind"),
    [
        (11, Qt.Key.Key_Plus, "plus"),
        (13, Qt.Key.Key_Minus, "minus"),
        (11, Qt.Key.Key_Minus, "minus"),
        (13, Qt.Key.Key_Plus, "plus"),
    ],
)
def test_one_charge_shortcut_undoes_to_the_loaded_annotations(
    loaded, tmp_path, atom_id, key, kind
):
    window, canvas, original = loaded
    history = canvas.services.history_service
    before = _loaded_snapshot(canvas, original)

    _hover_key(canvas, atom_id, key)
    after = _snapshot(canvas)
    assert len(history.state.history) == 1
    command = history.state.history[0]
    assert [(mark["atom_id"], mark["kind"]) for mark in after["marks"]] == [
        (atom_id, kind)
    ]
    other = 13 if atom_id == 11 else 11
    assert after["model"]["atom_annotations"][other] == LOADED_ANNOTATIONS[other]

    for _ in range(3):
        history.undo()
        assert _snapshot(canvas) == before
        assert not history.state.history
        assert len(history.state.redo_stack) == 1
        assert history.state.redo_stack[0] is command
        history.redo()
        assert _snapshot(canvas) == after
        assert not history.state.redo_stack
        assert len(history.state.history) == 1
        assert history.state.history[0] is command

    history.undo()
    saved = _assert_saved(window, tmp_path / "undone.chemvas", before, original)
    assert saved["marks"] == []
    assert saved["model"]["atom_annotations"] == original["model"]["atom_annotations"]
    history.redo()
    _assert_saved(window, tmp_path / "redone.chemvas", after, original)


def test_charge_then_cancel_undoes_each_step_exactly(loaded, tmp_path):
    window, canvas, original = loaded
    history = canvas.services.history_service
    before = _loaded_snapshot(canvas, original)

    _hover_key(canvas, 11, Qt.Key.Key_Plus)
    charged = _snapshot(canvas)
    assert [mark["kind"] for mark in charged["marks"]] == ["plus"]
    # The opposite key removes the shortcut's own mark rather than adding one.
    _hover_key(canvas, 11, Qt.Key.Key_Minus)
    cancelled = _snapshot(canvas)
    assert cancelled["marks"] == []
    assert len(history.state.history) == 2
    assert cancelled["model"]["atom_annotations"][13] == LOADED_ANNOTATIONS[13]

    for _ in range(3):
        history.undo()
        assert _snapshot(canvas) == charged
        history.undo()
        assert _snapshot(canvas) == before
        history.redo()
        assert _snapshot(canvas) == charged
        history.redo()
        assert _snapshot(canvas) == cancelled

    history.undo()
    history.undo()
    saved = _assert_saved(window, tmp_path / "undone.chemvas", before, original)
    assert saved["model"]["atom_annotations"] == original["model"]["atom_annotations"]


@pytest.mark.parametrize(
    ("atom_id", "kind"),
    [
        (11, "plus"),
        (13, "minus"),
        (11, "minus"),
        (13, "plus"),
        (11, "radical"),
    ],
)
def test_one_mark_tool_click_undoes_to_the_loaded_annotations(
    loaded, tmp_path, atom_id, kind
):
    window, canvas, original = loaded
    history = canvas.services.history_service
    _mark_tool(window, canvas, kind)
    before = _loaded_snapshot(canvas, original)

    _click_atom(canvas, atom_id)
    after = _snapshot(canvas)
    assert len(history.state.history) == 1
    command = history.state.history[0]
    assert [(mark["atom_id"], mark["kind"]) for mark in after["marks"]] == [
        (atom_id, kind)
    ]
    # The clicked atom's annotation follows the one mark it now carries.
    assert after["model"]["atom_annotations"][atom_id] == MARK_ANNOTATIONS[kind]
    other = 13 if atom_id == 11 else 11
    assert after["model"]["atom_annotations"][other] == LOADED_ANNOTATIONS[other]

    for _ in range(3):
        history.undo()
        assert _snapshot(canvas) == before
        assert not history.state.history
        assert len(history.state.redo_stack) == 1
        assert history.state.redo_stack[0] is command
        history.redo()
        assert _snapshot(canvas) == after
        assert not history.state.redo_stack
        assert len(history.state.history) == 1
        assert history.state.history[0] is command

    history.undo()
    saved = _assert_saved(window, tmp_path / "undone.chemvas", before, original)
    assert saved["marks"] == []
    assert saved["model"]["atom_annotations"] == original["model"]["atom_annotations"]
    history.redo()
    _assert_saved(window, tmp_path / "redone.chemvas", after, original)


def test_refused_mark_edit_keeps_the_loaded_annotations(loaded):
    # Direct public owner rather than a click: a refused push raises, and Qt
    # event delivery is not the subject. The annotation is synced before the
    # push, so the refusal must also restore the loaded value.
    _window, canvas, original = loaded
    history = canvas.services.history_service
    before = _loaded_snapshot(canvas, original)
    history.set_enabled(False)
    stacks = history.capture_stack_snapshot()

    with pytest.raises(RuntimeError, match="History is disabled"):
        add_mark_for_atom_for(canvas, 11, QPointF(*POSITIONS[11]), kind="minus")

    assert _snapshot(canvas) == before
    assert canvas.runtime_state.mark_items() == []
    history.verify_stack_snapshot(stacks)
    history.set_enabled(True)
