"""Image Properties can target one panel without breaking its native group."""

from io import BytesIO

import pytest
from PIL import Image
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QMessageBox,
)

from chemvas.core.document_io import read_document
from chemvas.domain.document import image_state_from_bytes
from chemvas.ui.canvas_group_state import group_state_for, register_group_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.image_actions import ImagePropertiesDialog
from chemvas.ui.scene_item_access import create_scene_item_from_state
from tests.test_active_gesture_document_edits import qt_errors as qt_errors
from tests.test_keyboard_focus_workflows import fresh_window as fresh_window
from tests.test_note_editing_workflows import app as app


def _panels(canvas, count=2):
    panels = []
    for index in range(count):
        output = BytesIO()
        Image.new("RGB", (80 + index, 40), (20, 80 + index, 160)).save(
            output, format="PNG"
        )
        panels.append(
            create_scene_item_from_state(
                canvas, image_state_from_bytes(output.getvalue(), x=120 * index)
            )
        )
    group_id = register_group_for(canvas, set(), panels)
    panels[0].setSelected(True)
    assert all(item.isSelected() for item in panels)
    return panels, group_id


def _action(window):
    return next(
        action
        for action in window.findChildren(QAction)
        if action.text() == "Image Properties..."
    )


@pytest.mark.parametrize("chosen", [0, 1])
def test_choose_grouped_panel_changes_only_target_and_reopens(
    fresh_window, monkeypatch, tmp_path, chosen
):
    window, canvas = fresh_window
    panels, group_id = _panels(canvas)
    original_group = group_state_for(canvas).groups[group_id]
    before = snapshot_canvas_state_for(canvas)
    calls = []

    def choose(_parent, title, label, values, current=0, editable=True):
        assert title == "Image Properties"
        assert "image" in label.lower()
        assert not editable
        assert len(values) == 2
        assert "80" in values[0] and "81" in values[1]
        assert "120" in values[1]
        calls.append(tuple(values))
        return values[chosen], True

    def edit(dialog):
        assert dialog.image_state() == panels[chosen].image_state()
        dialog.opacity.setValue(35)
        return QDialog.DialogCode.Accepted

    notices = []
    monkeypatch.setattr(QInputDialog, "getItem", choose)
    monkeypatch.setattr(ImagePropertiesDialog, "exec", edit)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args))
    _action(window).trigger()
    assert len(calls) == 1
    assert notices == []
    assert panels[chosen].opacity() == 0.35
    assert panels[1 - chosen].opacity() == 1
    assert all(item.isSelected() for item in panels)
    assert group_state_for(canvas).groups[group_id] is original_group
    after = snapshot_canvas_state_for(canvas)
    assert len(canvas.services.history_service.state.history) == 1
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    path = tmp_path / "panels.chemvas"
    session = canvas.services.document.canvas_document_session_service
    assert session.save_to_file(str(path)) == []
    session.apply_state(read_document(path).state)
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize(
    "outcome", ["choose_cancel", "properties_cancel", "noop", "push_false"]
)
def test_grouped_properties_cancel_noop_and_failure_are_exact(
    fresh_window, monkeypatch, outcome
):
    window, canvas = fresh_window
    panels, group_id = _panels(canvas)
    original_group = group_state_for(canvas).groups[group_id]
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    calls = []
    warnings = []

    def choose(_parent, _title, _label, values, current=0, editable=True):
        calls.append("choose")
        return values[1], outcome != "choose_cancel"

    def edit(dialog):
        calls.append("properties")
        if outcome == "properties_cancel":
            dialog.opacity.setValue(35)
            return QDialog.DialogCode.Rejected
        if outcome == "push_false":
            dialog.opacity.setValue(35)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QInputDialog, "getItem", choose)
    monkeypatch.setattr(ImagePropertiesDialog, "exec", edit)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    if outcome == "push_false":
        monkeypatch.setattr(history, "push", lambda _command: False)
    _action(window).trigger()
    assert calls == (
        ["choose"] if outcome == "choose_cancel" else ["choose", "properties"]
    )
    assert bool(warnings) == (outcome == "push_false")
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)
    assert group_state_for(canvas).groups[group_id] is original_group
    assert all(item.isSelected() for item in panels)


def test_single_image_still_opens_directly(fresh_window, monkeypatch):
    window, canvas = fresh_window
    panels, _group_id = _panels(canvas, count=1)
    calls = []
    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        lambda *args, **kwargs: pytest.fail("unexpected chooser"),
    )

    def edit(dialog):
        calls.append(dialog.image_state())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ImagePropertiesDialog, "exec", edit)
    _action(window).trigger()
    assert calls == [panels[0].image_state()]


def test_real_chooser_and_property_dialog_preserve_group(fresh_window, app):
    window, canvas = fresh_window
    panels, group_id = _panels(canvas)
    before = snapshot_canvas_state_for(canvas)
    original_group = group_state_for(canvas).groups[group_id]
    events = []

    def edit_panel():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, ImagePropertiesDialog)
            dialog.opacity.setFocus()
            dialog.opacity.selectAll()
            QTest.keyClicks(dialog.opacity, "35")
            buttons = dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(
                buttons.button(QDialogButtonBox.StandardButton.Ok),
                Qt.MouseButton.LeftButton,
            )
            events.append("edited")
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()

    def choose_panel():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, QInputDialog)
            combo = dialog.findChild(QComboBox)
            assert combo.count() == 2 and not combo.isEditable()
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key.Key_Down)
            assert combo.currentIndex() == 1
            buttons = dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(
                buttons.button(QDialogButtonBox.StandardButton.Ok),
                Qt.MouseButton.LeftButton,
            )
            events.append("chosen")
            QTimer.singleShot(0, edit_panel)
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, choose_panel)
    _action(window).trigger()
    assert events == ["chosen", "edited"]
    assert panels[0].opacity() == 1 and panels[1].opacity() == 0.35
    assert group_state_for(canvas).groups[group_id] is original_group
    assert all(item.isSelected() for item in panels)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
