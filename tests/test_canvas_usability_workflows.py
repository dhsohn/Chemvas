import json
from shutil import copyfile

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog

from chemvas.bootstrap.window_registry import open_windows
from chemvas.features.annotations import sanitize_note_html
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_scene_items_state import (
    arrow_items_for,
    note_items_for,
    selected_notes_for,
    shape_items_for,
)
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    history_service_for_window,
    services_for_window,
)
from chemvas.ui.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene_clipboard_logic import build_selection_clipboard_payload
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict
from chemvas.ui.selection_collection_access import selection_status_count_for
from tests.test_note_editing_workflows import _click, _key, _tool
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _ctrl(canvas, key):
    _key(canvas, key, Qt.KeyboardModifier.ControlModifier)


def _drag(canvas, start, end, *, cancel=False):
    a, b = [canvas.mapFromScene(p) for p in (start, end)]
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=a)
    QTest.mouseMove(canvas.viewport(), b, 30)
    if cancel:
        _key(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=b)
    QApplication.processEvents()


def _note(window, canvas, text="Catalyst"):
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    QTest.keyClicks(canvas, text)
    note = note_items_for(canvas)[-1]
    _tool(window, "select")
    _click(canvas, QPointF(160, 130))
    return note


def _arrow(window, canvas):
    _tool(window, "arrow")
    _drag(canvas, QPointF(-20, -20), QPointF(60, -20))
    _tool(window, "select")
    return arrow_items_for(canvas)[-1]


def _save(window, canvas, path):
    assert services_for_window(window).document_action_service.save_canvas_to_path(
        window, str(path)
    )
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)


def test_note_spaces_survive_document_undo_redo(drawing, tmp_path):
    window, canvas = drawing
    text = "  k1 = 0.1   k2 = 0.2  "
    note = _note(window, canvas, text)
    _save(window, canvas, tmp_path / "spaces.chemvas")
    _tool(window, "note")
    _click(canvas, note.sceneBoundingRect().center())
    _key(canvas, Qt.Key.Key_End)
    QTest.keyClicks(canvas, " extra")
    _tool(window, "select")
    _ctrl(canvas, Qt.Key.Key_Z)
    assert note.toPlainText() == text
    assert not window.isWindowModified()
    _ctrl(canvas, Qt.Key.Key_Y)
    assert note.toPlainText() == text + " extra"


def test_note_spaces_survive_file_open(drawing, tmp_path, monkeypatch):
    window, canvas = drawing
    text = "  k1 = 0.1   k2 = 0.2  "
    _note(window, canvas, text)
    saved, reopened = tmp_path / "spaces.chemvas", tmp_path / "reopen.chemvas"
    _save(window, canvas, saved)
    copyfile(saved, reopened)
    assert json.loads(saved.read_text())["state"]["notes"][0]["text"] == text
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **kw: (str(reopened), "")
    )
    before = set(open_windows())
    _ctrl(canvas, Qt.Key.Key_O)
    opened = set(open_windows()) - before
    try:
        assert len(opened) == 1
        target = next(iter(opened))
        restored = active_canvas_for_window(target)
        assert note_items_for(restored)[0].toPlainText() == text
        assert not target.isWindowModified()
    finally:
        for target in opened:
            services_for_window(target).canvas_document_service.mark_clean(
                active_canvas_for_window(target)
            )
            target.close()


@pytest.mark.parametrize("kind", ["note", "shape"])
def test_unselected_annotation_moves_on_first_drag(drawing, tmp_path, kind):
    window, canvas = drawing
    if kind == "note":
        item = _note(window, canvas)
    else:
        _tool(window, "shape")
        _drag(canvas, QPointF(-70, 0), QPointF(-20, 40))
        _tool(window, "select")
        _click(canvas, QPointF(160, 130))
        item = shape_items_for(canvas)[-1]
    _save(window, canvas, tmp_path / "annotation.chemvas")
    baseline = snapshot_canvas_state_for(canvas)
    center = item.sceneBoundingRect().center()
    history = history_service_for_window(window)
    count = len(history.state.history)
    _drag(canvas, center, center + QPointF(30, 15))
    assert item.sceneBoundingRect().center() == center + QPointF(30, 15)
    assert len(history.state.history) == count + 1
    _ctrl(canvas, Qt.Key.Key_Z)
    assert snapshot_canvas_state_for(canvas) == baseline
    assert not window.isWindowModified()
    _ctrl(canvas, Qt.Key.Key_Y)
    assert item.sceneBoundingRect().center() == center + QPointF(30, 15)


@pytest.fixture
def clipboard(monkeypatch):
    class MemoryClipboard:
        value = None

        def mimeData(self):
            return self.value

        def setMimeData(self, value):
            self.value = value

    memory = MemoryClipboard()
    monkeypatch.setattr(SceneClipboardController, "_clipboard", lambda self: memory)
    return memory


@pytest.mark.parametrize("pressed_member", [0, 1])
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("previous_selection", ["blank", "arrow"])
def test_first_drag_moves_notes_only_group_as_unit(
    drawing, tmp_path, pressed_member, cancel, previous_selection
):
    window, canvas = drawing
    first = _note(window, canvas, "First")
    _tool(window, "note")
    _click(canvas, QPointF(40, 35))
    QTest.keyClicks(canvas, "Second")
    second = note_items_for(canvas)[-1]
    _tool(window, "select")
    _ctrl(canvas, Qt.Key.Key_A)
    _ctrl(canvas, Qt.Key.Key_G)
    group = next(iter(group_state_for(canvas).groups.values()))
    assert set(group.items) == {first, second}
    arrow = _arrow(window, canvas)
    _click(canvas, QPointF(160, 130))
    if previous_selection == "arrow":
        _click(canvas, QPointF(20, -20))
        assert arrow.isSelected()
    assert not selected_notes_for(canvas)
    _save(window, canvas, tmp_path / "note-group.chemvas")
    baseline = snapshot_canvas_state_for(canvas)
    arrow_before = arrow_state_dict(arrow)
    notes = (first, second)
    centers = [note.sceneBoundingRect().center() for note in notes]
    start = centers[pressed_member]
    delta = QPointF(30, 15)
    history = history_service_for_window(window)
    count = len(history.state.history)
    _drag(canvas, start, start + delta, cancel=cancel)
    assert set(selected_notes_for(canvas)) == set(notes)
    assert not arrow.isSelected()
    assert arrow_state_dict(arrow) == arrow_before
    assert set(group.items) == set(notes)
    if cancel:
        assert snapshot_canvas_state_for(canvas) == baseline
        assert len(history.state.history) == count
        assert not window.isWindowModified()
        return
    assert [note.sceneBoundingRect().center() for note in notes] == [
        center + delta for center in centers
    ]
    assert len(history.state.history) == count + 1
    moved = snapshot_canvas_state_for(canvas)
    _ctrl(canvas, Qt.Key.Key_Z)
    assert snapshot_canvas_state_for(canvas) == baseline
    assert not window.isWindowModified()
    _ctrl(canvas, Qt.Key.Key_Y)
    assert snapshot_canvas_state_for(canvas) == moved


def _copy_pair(window, canvas, *, grouped):
    _note(window, canvas)
    _arrow(window, canvas)
    _ctrl(canvas, Qt.Key.Key_A)
    if grouped:
        _ctrl(canvas, Qt.Key.Key_G)
    _ctrl(canvas, Qt.Key.Key_C)
    _ctrl(canvas, Qt.Key.Key_V)


@pytest.mark.parametrize("grouped", [False, True])
def test_blank_click_clears_all_pasted_note_selection(drawing, clipboard, grouped):
    window, canvas = drawing
    _copy_pair(window, canvas, grouped=grouped)
    _click(canvas, QPointF(160, 130))
    assert selection_status_count_for(canvas) == 0
    assert not selected_notes_for(canvas)
    assert not canvas.scene().selectedItems()


def test_selecting_new_target_does_not_drag_unrelated_note(drawing, clipboard):
    window, canvas = drawing
    _copy_pair(window, canvas, grouped=False)
    note = note_items_for(canvas)[-1]
    before = QPointF(note.pos())
    # Click a different arrow without first clicking the blank canvas.
    _drag(canvas, QPointF(20, -20), QPointF(90, -20))
    assert note.pos() == before
    assert not selected_notes_for(canvas)


def test_group_copy_paste_preserves_independent_group_and_undo(drawing, clipboard):
    window, canvas = drawing
    _copy_pair(window, canvas, grouped=True)
    assert len(group_state_for(canvas).groups) == 2
    pasted = snapshot_canvas_state_for(canvas)
    _ctrl(canvas, Qt.Key.Key_Z)
    assert len(group_state_for(canvas).groups) == 1
    assert len(note_items_for(canvas)) == 1
    _ctrl(canvas, Qt.Key.Key_Y)
    assert snapshot_canvas_state_for(canvas) == pasted
    _click(canvas, QPointF(160, 130))
    copied_note = note_items_for(canvas)[-1]
    original_note = note_items_for(canvas)[0]
    before = QPointF(copied_note.pos())
    original = QPointF(original_note.pos())
    _drag(canvas, QPointF(38, -2), QPointF(108, -2))
    assert copied_note.pos() == before + QPointF(70, 0)
    assert original_note.pos() == original


def test_escape_rolls_back_drag_without_history_or_dirty_change(drawing, tmp_path):
    window, canvas = drawing
    arrow = _arrow(window, canvas)
    _save(window, canvas, tmp_path / "arrow.chemvas")
    before = arrow_state_dict(arrow)
    history = history_service_for_window(window)
    count = len(history.state.history)
    _drag(canvas, QPointF(20, -20), QPointF(90, -5), cancel=True)
    assert arrow_state_dict(arrow) == before
    assert len(history.state.history) == count
    assert not window.isWindowModified()
    _drag(canvas, QPointF(20, -20), QPointF(90, -5))
    assert len(history.state.history) == count + 1


def test_escape_finishes_note_edit_and_restores_shortcuts(drawing):
    window, canvas = drawing
    _tool(window, "note")
    _click(canvas, QPointF(-80, 35))
    QTest.keyClicks(canvas, "Catalyst")
    note = note_items_for(canvas)[0]
    _key(canvas, Qt.Key.Key_Escape)
    assert not note.hasFocus()
    assert note.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction
    _key(canvas, Qt.Key.Key_E)
    assert note.toPlainText() == "Catalyst"
    assert canvas.services.tool_controller.active.name == "arrow"
    _ctrl(canvas, Qt.Key.Key_Z)
    assert not note_items_for(canvas)


@pytest.mark.parametrize("text", ["  a   b  ", "a\tb", "  a\n\n b  \n", " "])
def test_note_html_roundtrip_preserves_spacing_and_bold(app, text):
    doc = QTextDocument()
    doc.setPlainText(text)
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    fmt.setFontWeight(700)
    cursor.mergeCharFormat(fmt)
    html = sanitize_note_html(doc.toHtml())
    assert html is not None
    assert sanitize_note_html(html) == html
    restored = QTextDocument()
    restored.setHtml(html)
    assert restored.toPlainText() == text
    cursor = QTextCursor(restored)
    cursor.movePosition(QTextCursor.MoveOperation.Right)
    assert cursor.charFormat().fontWeight() == 700


def test_repeated_paste_remaps_mixed_groups_without_touching_originals(
    drawing, clipboard
):
    window, canvas = drawing
    _note(window, canvas)
    _arrow(window, canvas)
    _tool(window, "bond")
    _click(canvas, QPointF(-80, -35))
    _tool(window, "shape")
    _drag(canvas, QPointF(80, 40), QPointF(110, 65))
    _tool(window, "mark")
    _click(canvas, QPointF(90, 85))
    _tool(window, "select")
    _ctrl(canvas, Qt.Key.Key_A)
    _ctrl(canvas, Qt.Key.Key_G)
    baseline = snapshot_canvas_state_for(canvas)
    original = next(iter(group_state_for(canvas).groups.values()))
    assert len(original.atom_ids) == 2
    assert {item.data(0) for item in original.items} == {
        "note",
        "arrow",
        "shape",
        "mark",
    }
    _ctrl(canvas, Qt.Key.Key_C)
    _ctrl(canvas, Qt.Key.Key_V)
    _ctrl(canvas, Qt.Key.Key_V)
    groups = list(group_state_for(canvas).groups.values())
    assert len(groups) == 3
    assert len(set.union(*(g.atom_ids for g in groups))) == 6
    assert len({id(item) for g in groups for item in g.items}) == 12
    after = snapshot_canvas_state_for(canvas)
    _ctrl(canvas, Qt.Key.Key_Z)
    _ctrl(canvas, Qt.Key.Key_Z)
    assert snapshot_canvas_state_for(canvas) == baseline
    _ctrl(canvas, Qt.Key.Key_Y)
    _ctrl(canvas, Qt.Key.Key_Y)
    assert snapshot_canvas_state_for(canvas) == after
    _ctrl(canvas, Qt.Key.Key_A)
    _ctrl(canvas, Qt.Key.Key_C)
    _ctrl(canvas, Qt.Key.Key_V)
    groups = list(group_state_for(canvas).groups.values())
    assert len(groups) == 6
    assert len(set.union(*(g.atom_ids for g in groups))) == 12
    assert len({id(item) for g in groups for item in g.items}) == 24
    _ctrl(canvas, Qt.Key.Key_Z)
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("kind", ["note", "shape", "arrow"])
def test_escape_cancels_creation_preview_or_finishes_empty_note(drawing, kind):
    window, canvas = drawing
    _tool(window, kind)
    if kind == "note":
        _click(canvas, QPointF(-80, 35))
        _key(canvas, Qt.Key.Key_Escape)
    else:
        _drag(canvas, QPointF(-70, 0), QPointF(20, 40), cancel=True)
    assert not note_items_for(canvas)
    assert not shape_items_for(canvas)
    assert not arrow_items_for(canvas)
    assert not history_service_for_window(window).can_undo()
    assert not window.isWindowModified()


def test_grouped_paste_failure_restores_document_and_history(
    drawing, clipboard, monkeypatch
):
    from chemvas.ui import scene_clipboard_paste_service as paste

    window, canvas = drawing
    _copy_pair(window, canvas, grouped=True)
    before = snapshot_canvas_state_for(canvas)
    history = history_service_for_window(window)
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))

    def fail_record(*args, **kwargs):
        assert kwargs["added_groups"]
        raise RuntimeError("paste recording failed")

    monkeypatch.setattr(paste, "record_additions_for", fail_record)
    # Call the same controller directly so an injected exception does not cross
    # Qt's C++ event boundary; real key-driven paste is covered above.
    controller = canvas.services.scene_operations.scene_clipboard_controller
    with pytest.raises(RuntimeError, match="paste recording failed"):
        controller.paste_selection_from_clipboard()
    assert snapshot_canvas_state_for(canvas) == before
    assert (tuple(history.state.history), tuple(history.state.redo_stack)) == stacks


def test_copied_groups_survive_save_open(drawing, clipboard, tmp_path, monkeypatch):
    window, canvas = drawing
    _copy_pair(window, canvas, grouped=True)
    saved, reopened = tmp_path / "groups.chemvas", tmp_path / "reopen.chemvas"
    _save(window, canvas, saved)
    copyfile(saved, reopened)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **kw: (str(reopened), "")
    )
    before = set(open_windows())
    _ctrl(canvas, Qt.Key.Key_O)
    opened = set(open_windows()) - before
    try:
        assert len(opened) == 1
        target = next(iter(opened))
        restored = active_canvas_for_window(target)
        assert len(group_state_for(restored).groups) == 2
        _tool(target, "select")
        note = note_items_for(restored)[-1]
        pos = QPointF(note.pos())
        _drag(restored, QPointF(38, -2), QPointF(108, -2))
        assert note.pos() == pos + QPointF(70, 0)
    finally:
        for target in opened:
            services_for_window(target).canvas_document_service.mark_clean(
                active_canvas_for_window(target)
            )
            target.close()


def test_escape_cancels_arrow_endpoint_drag(drawing, tmp_path):
    window, canvas = drawing
    arrow = _arrow(window, canvas)
    _save(window, canvas, tmp_path / "handle.chemvas")
    _click(canvas, QPointF(20, -20))
    _click(canvas, QPointF(20, -20))
    handle = active_handles_for(canvas)[0]
    before = arrow_state_dict(arrow)
    start = handle.sceneBoundingRect().center()
    _drag(canvas, start, start + QPointF(30, 15), cancel=True)
    assert arrow_state_dict(arrow) == before
    assert not active_handles_for(canvas)
    assert not window.isWindowModified()


def test_partial_clipboard_selection_does_not_reference_uncopied_group_members(drawing):
    window, canvas = drawing
    note = _note(window, canvas)
    arrow = _arrow(window, canvas)
    payload = build_selection_clipboard_payload(
        selected_items=[arrow],
        explicit_atom_ids=set(),
        selected_bond_ids=set(),
        bonds=[],
        ring_items=[],
        marks_by_atom={},
        scene=canvas.scene(),
        atom_state_getter=lambda _: {},
        bond_state_getter=lambda _: {},
        scene_item_state_getter=lambda item: scene_item_state_for(canvas, item),
        version=2,
        groups=[(set(), [arrow, note])],
    )
    assert len(payload["scene_items"]) == 1
    assert "groups" not in payload


def test_escape_stops_marquee_even_while_mouse_remains_pressed(drawing):
    window, canvas = drawing
    _note(window, canvas)
    a, b, c = [
        canvas.mapFromScene(p)
        for p in (QPointF(-90, 0), QPointF(0, 65), QPointF(50, 90))
    ]
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=a)
    QTest.mouseMove(canvas.viewport(), b, 30)
    assert not canvas.rubberBandRect().isEmpty()
    _key(canvas, Qt.Key.Key_Escape)
    cancelled = canvas.rubberBandRect().isEmpty()
    QTest.mouseMove(canvas.viewport(), c, 30)
    continued = not canvas.rubberBandRect().isEmpty()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=c)
    assert cancelled and not continued
    assert canvas.dragMode() == canvas.DragMode.RubberBandDrag
    # The next marquee gesture must still be usable.
    _click(canvas, QPointF(160, 130))
    _drag(canvas, QPointF(-90, 0), QPointF(0, 65))
    assert selection_status_count_for(canvas) == 1
