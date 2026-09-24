"""Shared shown-window fixtures and Qt input helpers for GUI workflows."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.selection import ROTATION_HANDLE_TYPE
from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_scene_items_state import note_items_for
from chemvas.ui.history.history_commands import AddSceneItemsCommand
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.scene.scene_decoration_access import add_arrow_for
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from chemvas.ui.tools.handle_state import active_handles_for
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.resize(1120, 700)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    window.raise_()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 5000)
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 180)
    canvas.centerOn(0, 0)
    QTest.qWait(30)
    yield window, canvas
    canvas.scene().clearFocus()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _tool(window, name):
    action = tool_action_for_window(window, name)
    button = next(
        b for b in window.findChildren(QToolButton) if b.defaultAction() is action
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _click(canvas, scene_pos):
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(scene_pos)
    )
    QApplication.processEvents()


def _key(canvas, key, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(canvas, key, modifiers)
    QApplication.processEvents()


def _redo(canvas):
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
    QApplication.processEvents()


def _saved_note(drawing, tmp_path):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    QTest.keyClicks(canvas, "alpha beta gamma")
    note = note_items_for(canvas)[0]
    _tool(window, "select")
    _click(canvas, QPointF(160, 100))
    actions = services_for_window(window).document_action_service
    assert actions.save_canvas_to_path(window, str(tmp_path / "note.chemvas"))
    assert not window.isWindowModified()
    _tool(window, "note")
    _click(canvas, note.sceneBoundingRect().center())
    assert note.hasFocus()
    _key(canvas, Qt.Key.Key_End)
    return note


@pytest.fixture
def qt_errors(monkeypatch):
    errors = []
    # Qt otherwise aborts when a Python release handler raises. Keep the real
    # event route and report that failure as a normal regression assertion.
    monkeypatch.setattr(
        sys, "excepthook", lambda _type, error, _tb: errors.append(error)
    )
    return errors


def populate(canvas, kind):
    if kind == "note":
        item = canvas.services.tool_controller.context.create_text_note(
            QPointF(-30.3, -20.7), "editable note"
        )
        canvas.services.history_service.push(
            AddSceneItemsCommand.from_items(
                [scene_item_state_for(canvas, item)], [item]
            )
        )
        return item.sceneBoundingRect().center(), item
    if kind in {"arrow", "handle", "move"}:
        item = add_arrow_for(canvas, QPointF(-65.2, -13.7), QPointF(25.3, 8.9), "arrow")
        return QPointF(-20, -2.4), item
    add_bond_between_points_for(canvas, QPointF(-45.3, -20.7), QPointF(25.2, 15.8))
    atoms = list(canvas.model.atoms.values())
    return QPointF((atoms[0].x + atoms[1].x) / 2, (atoms[0].y + atoms[1].y) / 2), None


def start_drag(canvas, kind, point, item=None):
    name = (
        kind
        if kind in {"perspective", "bond", "delete", "move", "line", "shape"}
        else "select"
    )
    canvas.services.tool_mode_controller.set_tool(name)
    if kind != "move":
        select_all_scene_items_for(canvas)
    else:
        canvas.scene().clearSelection()
    if kind == "handle":
        canvas.services.handle_overlay_service.show_endpoint_handles(item)
        point = active_handles_for(canvas)[0].sceneBoundingRect().center()
    elif kind == "rotation":
        knob = next(
            item
            for item in canvas.scene().items()
            if item.data(1) == ROTATION_HANDLE_TYPE
        )
        point = knob.sceneBoundingRect().center()
    elif kind == "perspective":
        atom = next(iter(canvas.model.atoms.values()))
        point = QPointF(atom.x, atom.y)
    elif kind == "bond":
        atom = next(iter(canvas.model.atoms.values()))
        point = QPointF(atom.x, atom.y)
    elif kind in {"line", "shape"}:
        point = QPointF(90, 70)
    canvas.setFocus()
    start = canvas.mapFromScene(point)
    end = start + QPoint(60, 37)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), start + QPoint(25, 14), delay=20)
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    return end


def release(canvas, end):
    QTest.mouseMove(canvas.viewport(), end + QPoint(10, 5), delay=20)
    QTest.mouseRelease(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=end + QPoint(10, 5)
    )


@pytest.fixture
def fresh_window(app, qt_errors):
    window = build_main_window()
    window.resize(1120, 700)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    window.raise_()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 5000)
    app.processEvents()
    canvas = active_canvas_for_window(window)
    yield window, canvas
    canvas.scene().clearFocus()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()
    assert not qt_errors
