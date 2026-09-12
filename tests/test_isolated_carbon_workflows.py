"""A carbon retained after a mark edit remains visible and directly editable."""

import os
from shutil import copyfile
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer
from PyQt6.QtGui import QCursor, QImage, QKeySequence, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMenu, QToolButton

from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_format_access import clipboard_selection_mime_for
from chemvas.ui.canvas_scene_items_state import mark_items_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)
from chemvas.ui.mark_item_access import apply_mark_color_for, mark_center_for
from chemvas.ui.mark_reassignment_dialog import MarkReassignmentDialog
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.structure_mutation_access import add_atom_for


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    from chemvas.bootstrap.main_window import build_main_window

    window = build_main_window()
    window.resize(1150, 780)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 220)
    canvas.centerOn(0, 0)
    _tool(window, "select")
    app.processEvents()
    yield window, canvas
    canvas.scene().clearFocus()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _tool(window, name):
    action = tool_action_for_window(window, name)
    button = next(
        item
        for item in window.findChildren(QToolButton)
        if item.defaultAction() is action
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _click(canvas, pos, button=Qt.MouseButton.LeftButton):
    QTest.mouseClick(canvas.viewport(), button, pos=canvas.mapFromScene(pos))
    QApplication.processEvents()


def _hover_key(canvas, scene_pos, key):
    viewport = canvas.viewport()
    position = canvas.mapFromScene(scene_pos)
    global_position = viewport.mapToGlobal(position)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(position),
        QPointF(global_position),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Wayland need not allow QTest cursor warping. Deliver the real widget move
    # event, then keep the key handler's fresh cursor sample at that same event
    # position. This models input; it does not bypass hover or shortcut owners.
    original_cursor_sampler = QCursor.pos
    with patch("chemvas.ui.hover.QCursor.pos", return_value=global_position):
        QApplication.sendEvent(viewport, event)
        QTest.keyClick(viewport, key)
    assert QCursor.pos == original_cursor_sampler


def _seed(drawing, kind="plus"):
    window, canvas = drawing
    owner = add_atom_for(canvas, "C", 0, 0)
    mark = add_mark_for_atom_for(canvas, owner, QPointF(30, -30), kind=kind)
    apply_mark_color_for(canvas, mark, "#Ab2374")
    center = mark_center_for(canvas, mark)
    move_item_for(canvas, mark, 30 - center.x(), -30 - center.y())
    assert mark_center_for(canvas, mark) == QPointF(30, -30)
    assert not canvas.model.atoms[owner].explicit_label
    assert owner not in atom_items_for(canvas)
    canvas.services.history_service.clear()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    return owner, mark


def _visible_carbon(canvas, owner):
    atom = canvas.model.atoms[owner]
    assert atom.element == "C"
    assert atom.explicit_label
    label = atom_items_for(canvas)[owner]
    assert label.isVisible()
    assert label.toPlainText() == "C"
    assert not label.glyph_path().isEmpty()
    return label


def _history_roundtrip(canvas, before):
    history = canvas.services.history_service
    after = snapshot_canvas_state_for(canvas)
    assert len(history.state.history) == 1
    for _ in range(2):
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
    return after


def _save_reopen_edit(drawing, owner, tmp_path):
    window, canvas = drawing
    _visible_carbon(canvas, owner)
    before = snapshot_canvas_state_for(canvas)
    session = canvas.services.document.canvas_document_session_service
    first, second = tmp_path / "live.png", tmp_path / "reopened.png"
    session.export_figure(str(first), fmt="png")
    image = QImage(str(first))
    assert not image.isNull()
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    assert any(rgba.constBits().asstring(rgba.sizeInBytes())[3::4])
    actions = services_for_window(window).document_action_service
    path = tmp_path / "visible-carbon.chemvas"
    assert actions.save_canvas_to_path(window, str(path))
    # A different synthetic filename prevents Open from merely activating the
    # already-open saved path. Read its identical bytes into a fresh canvas.
    reopen_path = tmp_path / "reopened-carbon.chemvas"
    copyfile(path, reopen_path)
    assert actions.load_canvas_from_path(window, str(reopen_path))
    original_canvas = canvas
    canvas = active_canvas_for_window(window)
    assert canvas is not original_canvas
    session = canvas.services.document.canvas_document_session_service
    assert snapshot_canvas_state_for(canvas) == before
    label = _visible_carbon(canvas, owner)
    session.export_figure(str(second), fmt="png")
    assert image == QImage(str(second))
    # A new user can find the retained atom from its visible glyph and edit it.
    _tool(window, "select")
    assert (
        canvas.services.input.pointer_controller.tool_controller.active.name == "select"
    )
    label = _visible_carbon(canvas, owner)
    _click(canvas, label.sceneBoundingRect().center())
    assert label.isSelected()
    _hover_key(
        canvas,
        QPointF(canvas.model.atoms[owner].x, canvas.model.atoms[owner].y),
        Qt.Key.Key_N,
    )
    assert canvas.model.atoms[owner].element == "N"
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    _visible_carbon(canvas, owner)


@pytest.mark.parametrize("kind", ["plus", "radical"])
@pytest.mark.parametrize("route", ["delete", "cut", "eraser"])
def test_real_mark_removal_retains_visible_carbon_and_one_exact_undo(
    drawing, app, tmp_path, monkeypatch, kind, route
):
    window, canvas = drawing
    owner, mark = _seed(drawing, kind)
    before = snapshot_canvas_state_for(canvas)
    center = mark_center_for(canvas, mark)
    clipboard = Mock()
    if route == "cut":
        # Exercise real Cut and MIME generation, without touching the desktop
        # clipboard when this same test runs on a native compositor.
        monkeypatch.setattr(
            SceneClipboardController, "_clipboard", lambda _self: clipboard
        )
    if route == "eraser":
        _tool(window, "delete")
        _click(canvas, center)
    else:
        _click(canvas, center)
        assert mark.isSelected()
        if route == "cut":
            QTest.keySequence(
                canvas.viewport(), QKeySequence(QKeySequence.StandardKey.Cut)
            )
        else:
            QTest.keyClick(canvas.viewport(), Qt.Key.Key_Delete)
    app.processEvents()
    if route == "cut":
        clipboard.setMimeData.assert_called_once()
        mime = clipboard.setMimeData.call_args.args[0]
        assert mime.hasFormat(clipboard_selection_mime_for(canvas))
    assert not mark_items_for(canvas)
    assert set(canvas.model.atoms) == {owner}
    assert not canvas.model.atom_annotations
    _visible_carbon(canvas, owner)
    _history_roundtrip(canvas, before)
    _save_reopen_edit(drawing, owner, tmp_path)


@pytest.mark.parametrize(
    "kind,key", [("plus", Qt.Key.Key_Minus), ("minus", Qt.Key.Key_Plus)]
)
def test_real_opposite_charge_shortcut_retains_carbon(
    drawing, app, tmp_path, kind, key
):
    _window, canvas = drawing
    owner, _mark = _seed(drawing, kind)
    before = snapshot_canvas_state_for(canvas)
    _hover_key(canvas, QPointF(), key)
    app.processEvents()
    assert not mark_items_for(canvas)
    assert not canvas.model.atom_annotations
    _visible_carbon(canvas, owner)
    _history_roundtrip(canvas, before)
    _save_reopen_edit(drawing, owner, tmp_path)


def test_reported_bond_charge_atom_delete_charge_cancel_flow(drawing, app, tmp_path):
    window, canvas = drawing
    _tool(window, "bond")
    _click(canvas, QPointF())
    assert len(canvas.model.atoms) == 2
    owner, other = sorted(canvas.model.atoms)
    atom = canvas.model.atoms[owner]
    owner_position = QPointF(atom.x, atom.y)
    _hover_key(canvas, owner_position, Qt.Key.Key_Plus)
    assert len(mark_items_for(canvas)) == 1
    assert mark_items_for(canvas)[0].data(1)["atom_id"] == owner
    _tool(window, "select")
    neighbor = canvas.model.atoms[other]
    _click(canvas, QPointF(neighbor.x, neighbor.y))
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Delete)
    assert set(canvas.model.atoms) == {owner}
    assert not any(canvas.model.bonds)
    assert not canvas.model.atoms[owner].explicit_label
    assert len(mark_items_for(canvas)) == 1
    canvas.services.history_service.clear()
    before = snapshot_canvas_state_for(canvas)
    _hover_key(canvas, owner_position, Qt.Key.Key_Minus)
    app.processEvents()
    assert not mark_items_for(canvas)
    _visible_carbon(canvas, owner)
    _history_roundtrip(canvas, before)
    _save_reopen_edit(drawing, owner, tmp_path)


def test_eraser_cancel_restores_implicit_carbon_mark_and_history(drawing, app):
    window, canvas = drawing
    owner, mark = _seed(drawing)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    _tool(window, "delete")
    position = canvas.mapFromScene(mark_center_for(canvas, mark))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    _visible_carbon(canvas, owner)
    assert not history.can_undo()
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    app.processEvents()
    assert snapshot_canvas_state_for(canvas) == before
    assert history.capture_stack_snapshot() == stacks
    assert not canvas.model.atoms[owner].explicit_label
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)


def test_rebonding_does_not_hide_the_retained_explicit_carbon(drawing, app):
    window, canvas = drawing
    owner, mark = _seed(drawing)
    _click(canvas, mark_center_for(canvas, mark))
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Delete)
    _visible_carbon(canvas, owner)
    before = snapshot_canvas_state_for(canvas)
    _tool(window, "bond")
    start = canvas.mapFromScene(QPointF())
    end = canvas.mapFromScene(QPointF(45, 0))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert any(bond and owner in {bond.a, bond.b} for bond in canvas.model.bonds)
    _visible_carbon(canvas, owner)
    after = snapshot_canvas_state_for(canvas)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    _visible_carbon(canvas, owner)


def _reassign_through_menu(canvas, app, mark, target, accept):
    errors, completed = [], []

    def choose_atom():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, MarkReassignmentDialog)
            dialog.atoms.setCurrentIndex(dialog.atoms.findData(target))
            button = (
                QDialogButtonBox.StandardButton.Ok
                if accept
                else QDialogButtonBox.StandardButton.Cancel
            )
            QTest.mouseClick(dialog.buttons.button(button), Qt.MouseButton.LeftButton)
            completed.append("dialog")
        except Exception as error:
            errors.append(repr(error))
        finally:
            if isinstance(dialog, QDialog) and dialog.isVisible():
                dialog.reject()

    def choose_action():
        menu = app.activePopupWidget()
        try:
            assert isinstance(menu, QMenu)
            action = next(
                action
                for action in menu.actions()
                if action.text() == "Reassign to atom…"
            )
            menu.setActiveAction(action)
            QTimer.singleShot(20, choose_atom)
            QTest.keyClick(menu, Qt.Key.Key_Return)
            completed.append("menu")
        except Exception as error:
            errors.append(repr(error))
            if isinstance(menu, QMenu):
                menu.close()

    def timeout():
        errors.append("Reassignment did not finish")
        modal = app.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.reject()
        popup = app.activePopupWidget()
        if popup is not None:
            popup.close()

    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(timeout)
    watchdog.start(5000)
    QTimer.singleShot(0, choose_action)
    try:
        _click(canvas, mark_center_for(canvas, mark), Qt.MouseButton.RightButton)
    finally:
        watchdog.stop()
    assert not errors
    assert sorted(completed) == ["dialog", "menu"]


@pytest.mark.parametrize("accept", [False, True])
@pytest.mark.parametrize("kind", ["plus", "radical"])
def test_real_reassignment_promotes_only_after_accepting_new_owner(
    drawing, app, tmp_path, accept, kind
):
    window, canvas = drawing
    owner, mark = _seed(drawing, kind)
    target = add_atom_for(canvas, "O", 100, 30)
    canvas.services.history_service.clear()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    before = snapshot_canvas_state_for(canvas)
    position, color = mark.pos(), mark.data(1)["color"]
    _reassign_through_menu(canvas, app, mark, target, accept)
    assert mark.pos() == position and mark.data(1)["color"] == color
    if not accept:
        assert snapshot_canvas_state_for(canvas) == before
        assert not canvas.services.history_service.can_undo()
        assert not canvas.model.atoms[owner].explicit_label
        return
    assert mark.data(1)["atom_id"] == target
    assert owner not in canvas.model.atom_annotations
    assert canvas.model.atom_annotations[target] == (
        {"formal_charge": 1} if kind == "plus" else {"radical_electrons": 1}
    )
    _visible_carbon(canvas, owner)
    _history_roundtrip(canvas, before)
    _save_reopen_edit(drawing, owner, tmp_path)


@pytest.mark.parametrize("move_to_atom", [False, True])
def test_eraser_stationary_frames_do_not_erase_newly_revealed_carbon(
    drawing, app, move_to_atom
):
    window, canvas = drawing
    owner, mark = _seed(drawing)
    center = mark_center_for(canvas, mark)
    # Closer to the mark than the old atom dot, but inside the future C's hit
    # footprint. Coincident centers intentionally pick the atom, not the mark.
    move_item_for(canvas, mark, 3.0 - center.x(), -center.y())
    before = snapshot_canvas_state_for(canvas)
    _tool(window, "delete")
    position = canvas.mapFromScene(mark_center_for(canvas, mark))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    _visible_carbon(canvas, owner)
    for _ in range(2):
        QApplication.sendEvent(
            canvas.viewport(),
            QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(position),
                QPointF(canvas.viewport().mapToGlobal(position)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        _visible_carbon(canvas, owner)
    if move_to_atom:
        # Changing the pointer position onto the atom is a real continued
        # eraser gesture, and must not be blocked by the stationary-frame guard.
        position = canvas.mapFromScene(QPointF())
        QApplication.sendEvent(
            canvas.viewport(),
            QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(position),
                QPointF(canvas.viewport().mapToGlobal(position)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        assert owner not in canvas.model.atoms
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        _history_roundtrip(canvas, before)
        assert owner not in canvas.model.atoms
        return
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    _visible_carbon(canvas, owner)
    _history_roundtrip(canvas, before)
    # A subsequent intentional eraser click can still remove the visible atom.
    label = _visible_carbon(canvas, owner)
    _click(canvas, label.sceneBoundingRect().center())
    assert owner not in canvas.model.atoms
    canvas.services.history_service.undo()
    _visible_carbon(canvas, owner)
