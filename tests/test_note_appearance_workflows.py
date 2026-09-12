"""Document-wide note appearance agrees in the canvas, history and saved file."""

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QAction, QTextOption
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox

from chemvas.core.document_io import read_document
from chemvas.ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.note_appearance_dialog import NoteAppearanceDialog
from chemvas.ui.scene_item_access import create_scene_item_from_state
from tests.test_active_gesture_document_edits import populate, start_drag
from tests.test_active_gesture_document_edits import qt_errors as qt_errors
from tests.test_keyboard_focus_workflows import fresh_window as fresh_window
from tests.test_note_editing_workflows import app as app


@pytest.mark.parametrize("failure", [None, "push_false", "undo"])
def test_preset_preserves_qt_default_alignment_on_undo_and_failure(
    fresh_window, monkeypatch, failure
):
    _window, canvas = fresh_window
    set_text_style_for(canvas, "text_alignment", Qt.AlignmentFlag.AlignRight)
    notes = _notes(canvas)
    original_options = []
    for note in notes:
        option = note.document().defaultTextOption()
        tab = QTextOption.Tab()
        tab.position = 67.25
        tab.type = QTextOption.TabType.DelimiterTab
        tab.delimiter = ":"
        option.setTabs([tab])
        option.setUseDesignMetrics(True)
        option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        option.setFlags(QTextOption.Flag.IncludeTrailingSpaces)
        note.document().setDefaultTextOption(option)
        original_options.append(QTextOption(option))
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    if failure == "push_false":
        with monkeypatch.context() as patch:
            patch.setattr(history, "push", lambda _command: False)
            with pytest.raises(RuntimeError, match="did not commit"):
                _style(canvas).apply_text_preset_paper_bold()
        history.verify_stack_snapshot(stacks)
    else:
        _style(canvas).apply_text_preset_paper_bold()
        if failure == "undo":
            after = snapshot_canvas_state_for(canvas)
            stacks = history.capture_stack_snapshot()
            controller = canvas.services.interaction.note_controller
            original_update = controller.update_note_box

            def fail(item):
                original_update(item)
                raise RuntimeError("alignment rollback probe")

            with monkeypatch.context() as patch:
                patch.setattr(controller, "update_note_box", fail)
                with pytest.raises(RuntimeError, match="alignment rollback probe"):
                    history.undo()
            assert snapshot_canvas_state_for(canvas) == after
            history.verify_stack_snapshot(stacks)
            assert all(
                note.document().defaultTextOption().alignment()
                == Qt.AlignmentFlag.AlignLeft
                for note in notes
            )
        history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert all(
        note.document().defaultTextOption().alignment() == Qt.AlignmentFlag.AlignRight
        for note in notes
    )
    for note, option in zip(notes, original_options, strict=True):
        actual = note.document().defaultTextOption()
        assert actual.tabs() == option.tabs()
        assert actual.flags() == option.flags()
        assert actual.textDirection() == option.textDirection()
        assert actual.useDesignMetrics() == option.useDesignMetrics()


@pytest.mark.parametrize("kind", ["note", "rotation", "handle"])
def test_appearance_menu_cancels_active_gesture_before_dialog(
    fresh_window, monkeypatch, kind
):
    window, canvas = fresh_window
    point, item = populate(canvas, kind)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    end = start_drag(canvas, kind, point, item)
    assert canvas.services.tool_controller.active.has_active_gesture

    def inspect(dialog):
        assert snapshot_canvas_state_for(canvas) == before
        assert not canvas.services.tool_controller.active.has_active_gesture
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(NoteAppearanceDialog, "exec", inspect)
    _appearance_action(window).trigger()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("failure", ["push_false", "raise"])
def test_default_font_failure_is_visible_and_exact(fresh_window, monkeypatch, failure):
    from tests.test_note_formatting_workflows import _font_menu

    window, canvas = fresh_window
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    warnings = []

    def push(_command):
        if failure == "raise":
            raise RuntimeError("font history failure")
        return False

    monkeypatch.setattr(history, "push", push)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    _font_menu(window, "Courier New")
    assert len(warnings) == 1 and warnings[0][1] == "Text Font"
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)


def _notes(canvas):
    return [
        create_scene_item_from_state(
            canvas,
            {"kind": "note", "text": "Condition\nSecond line", "x": x, "y": 0},
        )
        for x in (0, 150)
    ]


@pytest.mark.parametrize("accept", [True, False])
def test_editing_note_then_actual_appearance_menu_keeps_exact_undo_steps(
    fresh_window, app, accept
):
    from tests.test_note_formatting_workflows import _main_menu

    window, canvas = fresh_window
    notes = _notes(canvas)
    note = notes[0]
    before = snapshot_canvas_state_for(canvas)
    controller = canvas.services.interaction.note_controller
    controller.begin_note_edit(note)
    QTest.keyClicks(canvas, "typed")
    edited_text = note.toPlainText()
    assert "typed" in edited_text
    done = []

    def accept_dialog():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, NoteAppearanceDialog):
            QTimer.singleShot(0, accept_dialog)
            return
        dialog.checks["note_box_enabled"].setChecked(True)
        buttons = dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(
            buttons.button(
                QDialogButtonBox.StandardButton.Ok
                if accept
                else QDialogButtonBox.StandardButton.Cancel
            ),
            Qt.MouseButton.LeftButton,
        )
        done.append(True)

    QTimer.singleShot(0, accept_dialog)
    _main_menu(window, "Edit", "Note Appearance...")
    assert done == [True]
    assert note.toPlainText() == edited_text
    history = canvas.services.history_service
    assert len(history.state.history) == (2 if accept else 1)
    if accept:
        history.undo()
        assert note.toPlainText() == edited_text
        assert not text_style_state_for(canvas).note_box_enabled
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


def _style(canvas):
    return canvas.services.scene_operations.style_controller


@pytest.mark.parametrize("preset", ["acs", "paper_thin", "paper_bold"])
def test_existing_preset_updates_all_notes_with_one_exact_undo(
    fresh_window, tmp_path, preset
):
    _window, canvas = fresh_window
    notes = _notes(canvas)
    before = snapshot_canvas_state_for(canvas)
    getattr(_style(canvas), f"apply_text_preset_{preset}")()
    history = canvas.services.history_service
    assert len(history.state.history) == 1
    style = text_style_state_for(canvas)
    for item in notes:
        box = item.data(20)
        assert (box is not None and box.isVisible()) == (
            style.note_box_enabled or style.note_border_enabled
        )
        assert item.document().firstBlock().blockFormat().lineHeight() == int(
            style.text_line_spacing * 100
        )
    after = snapshot_canvas_state_for(canvas)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    path = tmp_path / "notes.chemvas"
    session = canvas.services.document.canvas_document_session_service
    assert session.save_to_file(str(path)) == []
    session.apply_state(read_document(path).state)
    assert snapshot_canvas_state_for(canvas) == after


def test_note_appearance_fields_are_global_but_preserve_character_formats(fresh_window):
    _window, canvas = fresh_window
    notes = _notes(canvas)
    notes[0].setHtml(
        '<p><span style="color:#cc2200; font-weight:700">TS</span><sub>2</sub></p>'
    )
    before_text = [item.toPlainText() for item in notes]
    before = snapshot_canvas_state_for(canvas)
    _style(canvas).set_note_appearance(
        {
            "note_box_enabled": True,
            "note_box_color": "#224466",
            "note_box_alpha": 0.35,
            "note_border_enabled": True,
            "note_border_color": "#884422",
            "note_border_width": 2.5,
            "note_padding": 9.5,
            "text_line_spacing": 1.25,
        }
    )
    for item in notes:
        box = item.data(20)
        assert box.isVisible()
        assert box.brush().color().name() == "#224466"
        assert box.brush().color().alphaF() == pytest.approx(0.35, abs=1e-5)
        assert box.pen().color().name() == "#884422"
        assert box.pen().widthF() == 2.5
        assert box.rect() == item.boundingRect().adjusted(-9.5, -9.5, 9.5, 9.5)
        assert item.document().firstBlock().blockFormat().lineHeight() == 125
    assert [item.toPlainText() for item in notes] == before_text
    assert "#cc2200" in notes[0].toHtml()
    assert "font-weight:700" in notes[0].toHtml()
    assert "vertical-align:sub" in notes[0].toHtml()
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before


def test_font_default_does_not_restyle_existing_notes_and_undo_is_exact(fresh_window):
    _window, canvas = fresh_window
    notes = _notes(canvas)
    before_html = [item.toHtml() for item in notes]
    before = snapshot_canvas_state_for(canvas)
    _style(canvas).set_text_font_family_default("DejaVu Serif")
    assert [item.toHtml() for item in notes] == before_html
    assert text_style_state_for(canvas).text_font_family == "DejaVu Serif"
    after = snapshot_canvas_state_for(canvas)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    item = canvas.services.interaction.note_controller.create_text_note(
        QPointF(), "New"
    )
    assert item.font().family() == "DejaVu Serif"


@pytest.mark.parametrize("failure", ["second_note", "push_raise", "push_false"])
def test_note_appearance_failure_restores_settings_notes_and_history(
    fresh_window, monkeypatch, failure
):
    _window, canvas = fresh_window
    _notes(canvas)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    original_style = text_style_state_for(canvas)
    with monkeypatch.context() as patch:
        if failure == "second_note":
            controller = canvas.services.interaction.note_controller
            original_apply = controller.apply_note_appearance
            calls = []

            def fail(item, *, line_spacing):
                original_apply(item, line_spacing=line_spacing)
                calls.append(item)
                if len(calls) == 2:
                    raise RuntimeError("note paint failed")

            patch.setattr(controller, "apply_note_appearance", fail)
        else:

            def refuse(_command):
                if failure == "push_false":
                    return False
                raise RuntimeError("history failed")

            patch.setattr(history, "push", refuse)
        with pytest.raises(RuntimeError):
            _style(canvas).set_note_appearance(
                {"note_box_enabled": True, "text_line_spacing": 1.25}
            )
    assert text_style_state_for(canvas) is original_style
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)
    _style(canvas).set_note_appearance({"note_box_enabled": True})
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


def test_note_style_undo_failure_is_exact_and_retryable(fresh_window, monkeypatch):
    _window, canvas = fresh_window
    _notes(canvas)
    before = snapshot_canvas_state_for(canvas)
    _style(canvas).set_note_appearance({"note_box_enabled": True, "note_padding": 10.0})
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    controller = canvas.services.interaction.note_controller
    original_update = controller.update_note_box
    calls = []

    def fail(item):
        original_update(item)
        calls.append(item)
        if len(calls) == 2:
            raise RuntimeError("note paint failed")

    with monkeypatch.context() as patch:
        patch.setattr(controller, "update_note_box", fail)
        with pytest.raises(RuntimeError, match="note paint failed"):
            history.undo()
    assert snapshot_canvas_state_for(canvas) == after
    history.verify_stack_snapshot(stacks)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize(
    "name,value",
    [
        ("note_box_enabled", 1),
        ("note_border_enabled", "yes"),
        ("note_box_color", "red"),
        ("note_border_color", "#ffffff00"),
        ("note_box_alpha", 1.1),
        ("note_box_alpha", -0.1),
        ("note_border_width", 0.4),
        ("note_padding", 1.9),
        ("text_line_spacing", 0.79),
        ("text_line_spacing", float("inf")),
        ("note_padding", float("nan")),
        ("text_font_size", 18),
    ],
)
def test_invalid_appearance_is_rejected_without_mutation(fresh_window, name, value):
    _window, canvas = fresh_window
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    with pytest.raises(ValueError):
        _style(canvas).set_note_appearance({name: value})
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)


def _appearance_action(window):
    return next(
        action
        for action in window.findChildren(QAction)
        if action.text() == "Note Appearance..."
    )


@pytest.mark.parametrize("outcome", ["cancel", "noop", "accept", "push_false"])
def test_menu_appearance_dialog_and_error_surface(fresh_window, monkeypatch, outcome):
    window, canvas = fresh_window
    notes = _notes(canvas)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    warnings = []

    def edit(dialog):
        if outcome != "noop":
            dialog.checks["note_box_enabled"].setChecked(True)
        return (
            QDialog.DialogCode.Rejected
            if outcome == "cancel"
            else QDialog.DialogCode.Accepted
        )

    monkeypatch.setattr(NoteAppearanceDialog, "exec", edit)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    if outcome == "push_false":
        monkeypatch.setattr(history, "push", lambda _command: False)
    _appearance_action(window).trigger()
    if outcome == "accept":
        assert all(item.data(20).isVisible() for item in notes)
        history.undo()
    else:
        history.verify_stack_snapshot(stacks)
    assert snapshot_canvas_state_for(canvas) == before
    assert bool(warnings) == (outcome == "push_false")


def test_dialog_noop_preserves_rounding_and_existing_large_values(fresh_window):
    _window, canvas = fresh_window
    values = _style(canvas).note_appearance() | {
        "note_box_alpha": 0.123456789,
        "note_padding": 2_000_000.123456789,
        "text_line_spacing": 1.123456789,
    }
    dialog = NoteAppearanceDialog(values)
    assert dialog.appearance_values() == values
    dialog.numbers["note_border_width"].setValue(2)
    assert dialog.appearance_values() == values | {"note_border_width": 2}
    dialog.close()


def test_real_note_appearance_dialog_input_and_no_false_followup_edit(
    fresh_window, app
):
    window, canvas = fresh_window
    notes = _notes(canvas)
    before = snapshot_canvas_state_for(canvas)
    completed = []

    def edit():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, NoteAppearanceDialog)
            for name in ("note_box_enabled", "note_border_enabled"):
                check = dialog.checks[name]
                QTest.mouseClick(
                    check, Qt.MouseButton.LeftButton, pos=QPoint(8, check.height() // 2)
                )
                assert check.isChecked()
            padding = dialog.numbers["note_padding"]
            padding.setFocus()
            padding.selectAll()
            QTest.keyClicks(padding, "10")
            buttons = dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(
                buttons.button(QDialogButtonBox.StandardButton.Ok),
                Qt.MouseButton.LeftButton,
            )
            completed.append(True)
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, edit)
    _appearance_action(window).trigger()
    assert completed == [True]
    assert all(item.data(20).isVisible() for item in notes)
    assert text_style_state_for(canvas).note_padding == 10
    history = canvas.services.history_service
    after = snapshot_canvas_state_for(canvas)
    assert len(history.state.history) == 1
    controller = canvas.services.interaction.note_controller
    controller.begin_note_edit(notes[0])
    controller.finish_note_edit()
    assert len(history.state.history) == 1
    assert snapshot_canvas_state_for(canvas) == after
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
