"""Text controls share one selection scope and preserve mixed rich text."""

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QToolButton,
)

from chemvas.core.document_io import read_document
from chemvas.ui.canvas_scene_items_state import selected_notes_for
from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.canvas_text_style_state import text_style_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import services_for_window
from chemvas.ui.selection_service_access import selection_service_from_canvas
from tests.test_note_editing_workflows import _tool
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _select(note, start, end):
    cursor = note.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    note.setTextCursor(cursor)


def _char_format(note, position):
    cursor = QTextCursor(note.document())
    cursor.setPosition(position)
    cursor.movePosition(
        QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
    )
    return cursor.charFormat()


def _format_range(note, start, end, fmt):
    cursor = QTextCursor(note.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)


def _button(window, tooltip):
    button = next(b for b in window.findChildren(QToolButton) if b.toolTip() == tooltip)
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def _choose_popup(menu, action, open_popup):
    errors = []
    chosen = []
    if action is not None:
        action.triggered.connect(lambda: chosen.append(action.text()))

    def choose():
        try:
            assert menu.isVisible()
            # Dispatch the popup's activation before the synthetic click hides
            # it; otherwise offscreen can deliver a stale activation afterward.
            QApplication.processEvents()
            if action is None:
                QTest.keyClick(menu, Qt.Key.Key_Escape)
            else:
                assert action.isEnabled()
                QTest.mouseClick(
                    menu,
                    Qt.MouseButton.LeftButton,
                    pos=menu.actionGeometry(action).center(),
                )
        except Exception as error:
            errors.append(error)
        finally:
            menu.close()

    QTimer.singleShot(0, choose)
    open_popup()
    QApplication.processEvents()
    if errors:
        raise errors[0]
    assert chosen == ([] if action is None else [action.text()])


def _font_menu(window, family):
    button = window.findChild(QToolButton, "toolButton_note")
    menu = button.menu()
    action = (
        None
        if family is None
        else next(action for action in menu.actions() if action.text() == family)
    )
    _choose_popup(
        menu,
        action,
        lambda: QTest.mouseClick(
            button,
            Qt.MouseButton.LeftButton,
            pos=QPoint(button.width() - 3, button.height() - 3),
        ),
    )


def _main_menu(window, title, command):
    bar = window.menuBar()
    menu_action = next(action for action in bar.actions() if action.text() == title)
    menu = menu_action.menu()
    action = next(action for action in menu.actions() if action.text() == command)
    _choose_popup(
        menu,
        action,
        lambda: QTest.mouseClick(
            bar, Qt.MouseButton.LeftButton, pos=bar.actionGeometry(menu_action).center()
        ),
    )


def _note(drawing, text="Scheme 1\nconditions"):
    window, canvas = drawing
    _tool(window, "note")
    controller = note_controller_for_access(canvas)
    note = controller.create_text_note(QPointF(-70, -20), text)
    controller.begin_note_edit(note)
    assert note.hasFocus()
    return controller, note


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("delta", [-1, 1])
def test_size_steps_each_selected_run_without_direction_or_other_format_loss(
    drawing, reverse, delta
):
    window, _canvas = drawing
    _controller, note = _note(drawing)
    title = QTextCharFormat()
    title.setFontPointSize(20)
    title.setFontWeight(QFont.Weight.Bold)
    title.setForeground(QColor("#123456"))
    body = QTextCharFormat()
    body.setFontPointSize(10)
    body.setFontItalic(True)
    body.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
    _format_range(note, 0, 8, title)
    _format_range(note, 9, 19, body)
    _select(note, 19 if reverse else 0, 0 if reverse else 19)
    before = note.toHtml()
    cursor_before = (note.textCursor().anchor(), note.textCursor().position())
    _button(window, "Increase font size" if delta > 0 else "Decrease font size")
    assert [_char_format(note, i).fontPointSize() for i in (0, 9)] == [
        20 + delta,
        10 + delta,
    ]
    assert _char_format(note, 0).fontWeight() == QFont.Weight.Bold
    assert _char_format(note, 0).foreground().color() == QColor("#123456")
    assert _char_format(note, 9).fontItalic()
    assert (
        _char_format(note, 9).verticalAlignment()
        == QTextCharFormat.VerticalAlignment.AlignSubScript
    )
    assert note.hasFocus()
    assert (note.textCursor().anchor(), note.textCursor().position()) == cursor_before
    QTest.keyClick(
        note.scene().views()[0], Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    assert note.toHtml() == before


@pytest.mark.parametrize("reverse", [False, True])
def test_font_family_changes_only_selected_text_and_keeps_cursor(drawing, reverse):
    controller, note = _note(drawing, "CH2Cl2 reflux")
    before = note.toHtml()
    original_family = _char_format(note, 5).fontFamilies()
    _select(note, 3 if reverse else 0, 0 if reverse else 3)
    selection = (note.textCursor().anchor(), note.textCursor().position())
    controller.set_text_font_family("Courier New")
    assert _char_format(note, 0).fontFamilies() == ["Courier New"]
    assert _char_format(note, 5).fontFamilies() == original_family
    assert (note.textCursor().anchor(), note.textCursor().position()) == selection
    assert note.hasFocus()
    note.document().undo()
    assert note.toHtml() == before


def test_actual_font_menu_preserves_selected_text_scope_and_editor(drawing):
    window, canvas = drawing
    _controller, note = _note(drawing, "CH2Cl2 reflux")
    _select(note, 3, 0)
    before = note.toHtml()
    family = _char_format(note, 5).fontFamilies()
    _font_menu(window, "Courier New")
    assert _char_format(note, 0).fontFamilies() == ["Courier New"]
    assert _char_format(note, 5).fontFamilies() == family
    assert (note.textCursor().anchor(), note.textCursor().position()) == (3, 0)
    assert note.hasFocus()
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toHtml() == before


@pytest.mark.parametrize("exit_route", ["tool", "other-widget"])
def test_font_popup_cancel_keeps_editor_until_a_real_focus_exit(drawing, exit_route):
    window, canvas = drawing
    controller, note = _note(drawing, "Caption")
    _select(note, 7, 7)
    QTest.keyClicks(canvas, " changed")
    _select(note, 3, 0)
    before = note.toHtml()
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    _font_menu(window, None)
    assert note.hasFocus()
    assert (note.textCursor().anchor(), note.textCursor().position()) == (3, 0)
    assert note.toHtml() == before
    history.verify_stack_snapshot(stack)
    if exit_route == "tool":
        _tool(window, "bond")
    else:
        window.findChild(QLineEdit, "contextSmilesInput").setFocus()
    assert not note.hasFocus()
    assert not note.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
    assert not controller.text_format_targets()
    assert len(history.state.history) == len(stack.history) + 1
    history.undo()
    assert note.toPlainText() == "Caption"
    history.redo()
    assert note.toHtml() == before


def test_real_edit_menu_undo_redo_does_not_commit_the_note_session(drawing):
    window, canvas = drawing
    _controller, note = _note(drawing, "Caption")
    _select(note, 7, 7)
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    QTest.keyClicks(canvas, " changed")
    _main_menu(window, "Edit", "Undo")
    assert note.toPlainText() == "Caption"
    _main_menu(window, "Edit", "Redo")
    assert note.toPlainText() == "Caption changed"
    assert note.hasFocus()
    history.verify_stack_snapshot(stack)


def test_real_file_menu_save_preserves_live_editing_and_serializes_text(
    drawing, tmp_path
):
    window, canvas = drawing
    _controller, note = _note(drawing, "Caption")
    path = tmp_path / "menu-saved.chemvas"
    actions = services_for_window(window).document_action_service
    assert actions.save_canvas_to_path(window, str(path))
    _select(note, 7, 7)
    QTest.keyClicks(canvas, " changed")
    _main_menu(window, "File", "Save")
    assert read_document(path).state["notes"][0]["text"] == "Caption changed"
    assert note.hasFocus()
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toPlainText() == "Caption"
    assert window.isWindowModified()


@pytest.mark.parametrize("command", ["Open...", "Close Window"])
def test_real_file_menu_cancel_keeps_note_text_and_document(
    drawing, monkeypatch, command
):
    window, canvas = drawing
    _controller, note = _note(drawing, "Caption")
    _select(note, 7, 7)
    QTest.keyClicks(canvas, " changed")
    before = snapshot_canvas_state_for(canvas)
    calls = []
    if command == "Open...":
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: calls.append(True) or ("", ""),
        )
    else:
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: (
                calls.append(True) or QMessageBox.StandardButton.Cancel
            ),
        )
    _main_menu(window, "File", command)
    assert calls == [True]
    assert window.isVisible()
    assert note.toPlainText() == "Caption changed"
    assert snapshot_canvas_state_for(canvas) == before


def test_real_font_menu_without_target_updates_only_future_note_default(drawing):
    window, canvas = drawing
    _tool(window, "note")
    controller = note_controller_for_access(canvas)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    count = len(history.state.history)
    _font_menu(window, "Courier New")
    assert text_style_state_for(canvas).text_font_family == "Courier New"
    assert len(history.state.history) == count + 1
    after = snapshot_canvas_state_for(canvas)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    note = controller.create_text_note(QPointF(0, 0), "New note")
    assert note.font().family() == "Courier New"


@pytest.mark.parametrize("selection", [(0, 0), (0, 10), (10, 0)])
def test_alignment_changes_current_or_selected_paragraphs_only(drawing, selection):
    window, _canvas = drawing
    _controller, note = _note(drawing, "title\nbody\nfooter")
    _select(note, *selection)
    before = note.toHtml()
    _button(window, "Align center")
    alignments = []
    block = note.document().firstBlock()
    while block.isValid():
        alignments.append(block.blockFormat().alignment())
        block = block.next()
    expected = [
        Qt.AlignmentFlag.AlignHCenter,
        Qt.AlignmentFlag.AlignLeft,
        Qt.AlignmentFlag.AlignLeft,
    ]
    if selection[0] != selection[1]:
        expected[1] = Qt.AlignmentFlag.AlignHCenter
    assert alignments == expected
    assert (note.textCursor().anchor(), note.textCursor().position()) == selection
    assert note.hasFocus()
    note.document().undo()
    assert note.toHtml() == before


FORMAT_BUTTONS = [
    ("Bold the selected text", "font-weight:700"),
    ("Italicize the selected text", "font-style:italic"),
    ("Superscript the selected text", "vertical-align:super"),
    ("Subscript the selected text", "vertical-align:sub"),
    ("Increase font size", "font-size:13pt"),
    ("Decrease font size", "font-size:11pt"),
    ("Align right", 'align="right"'),
]


@pytest.mark.parametrize("selection_route", ["note-registry", "qt-only", "both"])
@pytest.mark.parametrize("tooltip,html_marker", FORMAT_BUTTONS)
def test_all_text_buttons_reach_selected_notes_once_and_roundtrip(
    drawing, tmp_path, selection_route, tooltip, html_marker
):
    window, canvas = drawing
    controller, note = _note(drawing, "Caption")
    controller.finish_note_edit()
    selection = selection_service_from_canvas(canvas)
    selection.clear_note_selection()
    canvas.scene().clearSelection()
    if selection_route != "qt-only":
        selection.select_note(note, additive=False)
    if selection_route != "note-registry":
        note.setSelected(True)
    assert not note.hasFocus()
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    count = len(history.state.history)
    selected_before = (note.isSelected(), tuple(selected_notes_for(canvas)))
    _button(window, tooltip)
    assert html_marker in note.toHtml()
    assert len(history.state.history) == count + 1
    assert (note.isSelected(), tuple(selected_notes_for(canvas))) == selected_before
    after = snapshot_canvas_state_for(canvas)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    path = tmp_path / "formatted.chemvas"
    actions = services_for_window(window).document_action_service
    assert actions.save_canvas_to_path(window, str(path))
    canvas.services.document.canvas_document_session_service.apply_state(
        read_document(path).state
    )
    assert snapshot_canvas_state_for(canvas) == after


def test_actual_marquee_then_text_page_formats_without_sticky_note_selection(drawing):
    window, canvas = drawing
    controller, note = _note(drawing, "Marquee caption")
    controller.finish_note_edit()
    selection_service_from_canvas(canvas).clear_note_selection()
    _tool(window, "select")
    rect = note.sceneBoundingRect().adjusted(-15, -15, 15, 15)
    start, end = (
        canvas.mapFromScene(rect.topLeft()),
        canvas.mapFromScene(rect.bottomRight()),
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=10)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert note.isSelected() and not selected_notes_for(canvas)
    _tool(window, "note")
    assert not note.hasFocus()
    _button(window, "Bold the selected text")
    assert "font-weight:700" in note.toHtml()
    assert note.isSelected() and not selected_notes_for(canvas)
    # A new marquee replaces the Qt-only selection; formatting must not pin it.
    _tool(window, "select")
    start, end = (
        canvas.mapFromScene(QPointF(100, 100)),
        canvas.mapFromScene(QPointF(150, 140)),
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=10)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert not note.isSelected() and not selected_notes_for(canvas)
    assert not controller.text_format_targets()


@pytest.mark.parametrize("tooltip,_marker", FORMAT_BUTTONS)
def test_text_button_without_target_explains_how_to_apply_it(drawing, tooltip, _marker):
    window, canvas = drawing
    _tool(window, "note")
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service.capture_stack_snapshot()
    _button(window, tooltip)
    assert "Select a note or edit its text" in window.statusBar().currentMessage()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(history)


@pytest.mark.parametrize("phase", ["second-note", "history-raise", "history-false"])
def test_selected_note_formatting_failure_keeps_all_notes_and_history_exact(
    drawing, monkeypatch, phase
):
    _window, canvas = drawing
    controller, first = _note(drawing, "first")
    controller.finish_note_edit()
    second = controller.create_text_note(QPointF(0, 50), "second")
    selection_service_from_canvas(canvas).select_note(first, additive=False)
    second.setSelected(True)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    old_update = controller.update_note_box
    old_push = history.push

    def update(item):
        old_update(item)
        if item is second:
            raise RuntimeError("second note failed")

    def push(command):
        old_push(command)
        raise RuntimeError("history publication failed")

    if phase == "second-note":
        monkeypatch.setattr(controller, "update_note_box", update)
    else:
        monkeypatch.setattr(
            history, "push", push if phase == "history-raise" else lambda command: False
        )
    with pytest.raises(RuntimeError):
        controller.adjust_text_size(1)
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stack)
    assert first in selected_notes_for(canvas) and second.isSelected()


def test_partial_unicode_size_uses_inherited_size_and_preserves_unselected_text(
    drawing,
):
    _window, canvas = drawing
    controller, note = _note(drawing, "A😀한B")
    font = note.font()
    font.setPointSizeF(17)
    note.setFont(font)
    _select(note, 1, 4)  # UTF-16 positions: emoji (two units), then Hangul.
    before = note.toHtml()
    controller.adjust_text_size(1)
    assert _char_format(note, 1).fontPointSize() == 18
    assert _char_format(note, 3).fontPointSize() == 18
    assert _char_format(note, 0).fontPointSize() == 0
    assert _char_format(note, 4).fontPointSize() == 0
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert note.toHtml() == before


def test_no_selection_family_and_size_change_only_future_typed_text(drawing):
    _window, canvas = drawing
    controller, note = _note(drawing, "existing")
    _select(note, 8, 8)
    previous = _char_format(note, 0)
    controller.set_text_font_family("Courier New")
    controller.adjust_text_size(1)
    QTest.keyClicks(canvas, " added")
    assert _char_format(note, 0).fontFamilies() == previous.fontFamilies()
    assert _char_format(note, 0).fontPointSize() == previous.fontPointSize()
    assert _char_format(note, 9).fontFamilies() == ["Courier New"]
    assert _char_format(note, 9).fontPointSize() == 13


def test_selected_note_formatting_respects_intentionally_disabled_history(drawing):
    _window, canvas = drawing
    controller, note = _note(drawing, "Caption")
    controller.finish_note_edit()
    selection_service_from_canvas(canvas).select_note(note, additive=False)
    history = canvas.services.history_service
    history.set_enabled(False)
    before = history.capture_stack_snapshot()
    try:
        controller.toggle_text_bold()
        assert "font-weight:700" in note.toHtml()
        history.verify_stack_snapshot(before)
    finally:
        history.set_enabled(True)


@pytest.mark.parametrize("size,delta", [(6, -1), (96, 1)])
def test_clamped_selected_note_size_is_a_noop_and_keeps_redo(drawing, size, delta):
    _window, canvas = drawing
    controller, note = _note(drawing, "Caption")
    fmt = QTextCharFormat()
    fmt.setFontPointSize(size)
    _format_range(note, 0, 7, fmt)
    controller.finish_note_edit()
    selection_service_from_canvas(canvas).select_note(note, additive=False)
    controller.toggle_text_bold()
    assert "font-weight:700" in note.toHtml()
    history = canvas.services.history_service
    history.undo()
    assert "font-weight:700" not in note.toHtml()
    assert history.state.redo_stack
    before = snapshot_canvas_state_for(canvas)
    stack = history.capture_stack_snapshot()
    controller.adjust_text_size(delta)
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stack)
