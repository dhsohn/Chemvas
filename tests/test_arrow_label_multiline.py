"""Arrow-label line breaks agree across editing, native paint and documents."""

import pytest
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
)

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.annotations import arrow_label_html
from chemvas.ui.arrow_label_dialog import prompt_arrow_labels
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_ports import scene_decoration_service_for_access
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.graphics_items import ArrowLabelItem
from chemvas.ui.scene_decoration_access import add_arrow_for, edit_arrow_labels_for
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("braced", [False, True])
def test_native_label_keeps_line_breaks_and_existing_syntax(app, ending, braced):
    raw = f"DMSO, rt{ending}68%, 96% ee"
    expected = "DMSO, rt\n68%, 96% ee"
    if braced:
        raw = f"k_{{a{ending}b}} < 2"
        expected = "ka\nb < 2"
    item = ArrowLabelItem()
    item.setHtml(arrow_label_html(raw))
    item.boundingRect()
    assert item.toPlainText() == expected
    assert item.document().firstBlock().layout().lineCount() == 2
    if braced:
        assert "vertical-align:sub" in item.toHtml()
        assert "&lt;" in arrow_label_html(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("K_{2}CO_{3}", "K<sub>2</sub>CO<sub>3</sub>"),
        ("k_{cat{H}}", "k<sub>cat{H</sub>}"),
        ("t\\_Bu", "t\\<sub>Bu</sub>"),
    ],
)
def test_single_line_grammar_is_unchanged(raw, expected):
    assert arrow_label_html(raw) == expected


def _buttons(dialog):
    return {button.text(): button for button in dialog.findChildren(QPushButton)}


def _drive_modal(action, drive):
    errors = []
    called = []

    def callback():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            assert QTest.qWaitForWindowExposed(dialog, 2000)
            assert QTest.qWaitForWindowActive(dialog, 2000)
            QTest.qWait(20)
            called.append(True)
            drive(dialog)
        except Exception as error:
            errors.append(error)
        finally:
            if isinstance(dialog, QDialog) and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, callback)
    result = action()
    if errors:
        raise errors[0]
    assert called == [True]
    return result


def _fields(dialog):
    above = dialog.findChild(QPlainTextEdit, "arrowLabelAboveInput")
    below = dialog.findChild(QPlainTextEdit, "arrowLabelBelowInput")
    assert above is not None and below is not None
    return above, below


def test_dialog_enter_tab_backtab_and_explicit_ok(drawing):
    _window, canvas = drawing

    def drive(dialog):
        above, below = _fields(dialog)
        above.setFocus()
        assert above.hasFocus(), QApplication.focusWidget()
        QTest.keyClicks(above, "K_{2}CO_{3}")
        QTest.keyClick(above, Qt.Key.Key_Return)
        assert dialog.isVisible()
        QTest.keyClicks(above, "DMSO")
        assert above.hasFocus(), QApplication.focusWidget()
        QTest.keyClick(above, Qt.Key.Key_Tab)
        assert below.hasFocus(), QApplication.focusWidget()
        QTest.keyClicks(below, "68%, 96% ee")
        QTest.keyClick(below, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert above.hasFocus()
        preview = dialog.findChild(QLabel, "arrowLabelAbovePreview")
        assert preview.text() == "K<sub>2</sub>CO<sub>3</sub><br>DMSO"
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    assert _drive_modal(
        lambda: prompt_arrow_labels(canvas, above="", below=""), drive
    ) == {"above": "K_{2}CO_{3}\nDMSO", "below": "68%, 96% ee"}


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("character", ["x", "😀", "\n"])
def test_over_limit_input_is_retained_and_blocks_ok_until_shortened(
    drawing, side, character
):
    _window, canvas = drawing

    def drive(dialog):
        field = _fields(dialog)[side]
        raw = character * 201
        field.insertPlainText(raw)
        assert field.toPlainText() == raw
        counter = dialog.findChild(QLabel, f"{field.objectName()}Limit")
        assert "201/200" in counter.text()
        assert not _buttons(dialog)["OK"].isEnabled()
        dialog.adjustSize()
        assert dialog.height() <= dialog.screen().availableGeometry().height()
        field.setPlainText(character * 200)
        assert "200/200" in counter.text()
        assert _buttons(dialog)["OK"].isEnabled()
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    result = _drive_modal(
        lambda: prompt_arrow_labels(canvas, above="", below=""), drive
    )
    assert result["above" if side == 0 else "below"] == character * 200


@pytest.mark.parametrize(
    "raw,axis",
    [("W" * 200, "horizontal"), ("\n" * 199 + "Z", "vertical")],
    ids=["wide", "many-lines"],
)
def test_preview_can_scroll_to_last_character(drawing, raw, axis):
    _window, canvas = drawing

    def drive(dialog):
        above, _below = _fields(dialog)
        above.setPlainText(raw)
        preview = dialog.findChild(QLabel, "arrowLabelAbovePreview")
        preview.setStyleSheet("color: rgb(12, 34, 56); background: white;")
        area = preview.parentWidget().parentWidget()
        assert isinstance(area, QScrollArea)
        QApplication.processEvents()
        scrollbar = (
            area.horizontalScrollBar()
            if axis == "horizontal"
            else area.verticalScrollBar()
        )
        assert scrollbar.maximum() > 0
        scrollbar.setValue(scrollbar.maximum())
        QApplication.processEvents()
        image = area.viewport().grab().toImage()
        painted = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if max(image.pixelColor(x, y).getRgb()[:3]) < 180
        )
        assert painted > 10  # The final W/Z is reachable, not a blank clipped area.
        assert dialog.height() <= dialog.screen().availableGeometry().height()
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    assert (
        _drive_modal(lambda: prompt_arrow_labels(canvas, above="", below=""), drive)[
            "above"
        ]
        == raw
    )


@pytest.mark.parametrize("count", [200, 201])
def test_original_crlf_counts_toward_character_limit(drawing, count):
    _window, canvas = drawing
    raw = "X" * (count - 3) + "\r\nZ"

    def drive(dialog):
        above, _below = _fields(dialog)
        assert len(above.toPlainText()) == count - 1
        counter = dialog.findChild(QLabel, "arrowLabelAboveInputLimit")
        assert f"{count}/200" in counter.text()
        assert _buttons(dialog)["OK"].isEnabled() == (count <= 200)
        if count > 200:
            above.setPlainText("shortened\nlabel")
            assert _buttons(dialog)["OK"].isEnabled()
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    assert _drive_modal(
        lambda: prompt_arrow_labels(canvas, above=raw, below=""), drive
    )["above"] == (raw if count <= 200 else "shortened\nlabel")


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("cancel", [False, True])
def test_untouched_old_newlines_and_cancel_preserve_document_and_history(
    drawing, ending, cancel
):
    _window, canvas = drawing
    arrow = add_arrow_for(canvas, QPointF(-40, 0), QPointF(40, 0), "arrow")
    raw = f"DMSO, rt{ending}68%, 96% ee"
    service = scene_decoration_service_for_access(canvas)
    assert service.set_arrow_labels(arrow, {"below": raw})
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()

    def drive(dialog):
        _above, below = _fields(dialog)
        assert below.toPlainText() == "DMSO, rt\n68%, 96% ee"
        if cancel:
            below.setPlainText("different\nlabel")
            QTest.keyClick(below, Qt.Key.Key_Escape)
        else:
            QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    assert not _drive_modal(lambda: edit_arrow_labels_for(canvas, arrow), drive)
    assert snapshot_canvas_state_for(canvas) == before
    assert before["arrows"][0]["labels"]["below"] == raw
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("raw", ["A\nB\n", " A\r\nB ", "A\rB\r"])
@pytest.mark.parametrize("edit_other", [False, True])
def test_loaded_label_preserves_edge_whitespace_when_only_other_side_changes(
    drawing, tmp_path, raw, edit_other
):
    _window, canvas = drawing
    add_arrow_for(canvas, QPointF(-40, 0), QPointF(40, 0), "arrow")
    state = snapshot_canvas_state_for(canvas)
    state["arrows"][0]["labels"] = {"above": raw}
    path = tmp_path / "external.chemvas"
    write_document(path, state, CANVAS_FILE_VERSION)
    documents = canvas.services.document.canvas_document_session_service
    documents.apply_state(read_document(path).state)
    (arrow,) = arrow_items_for(canvas)
    add_arrow_for(canvas, QPointF(70, 80), QPointF(110, 80), "arrow")
    history = canvas.services.history_service
    history.undo()
    assert history.can_redo()
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()

    def drive(dialog):
        if edit_other:
            _fields(dialog)[1].setPlainText("new\nlabel")
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    assert (
        _drive_modal(lambda: edit_arrow_labels_for(canvas, arrow), drive) == edit_other
    )
    after = snapshot_canvas_state_for(canvas)
    assert after["arrows"][0]["labels"]["above"] == raw
    if edit_other:
        assert after["arrows"][0]["labels"]["below"] == "new\nlabel"
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
    else:
        assert after == before
        history.verify_stack_snapshot(stacks)
    assert documents.save_to_file(str(path)) == []
    documents.apply_state(read_document(path).state)
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("raw", ["\nA\n", " A\nB ", " \n\t"])
def test_new_multiline_edges_are_preserved_and_whitespace_only_removes_label(
    drawing, tmp_path, raw
):
    _window, canvas = drawing
    arrow = add_arrow_for(canvas, QPointF(-40, 0), QPointF(40, 0), "arrow")
    service = scene_decoration_service_for_access(canvas)
    assert service.set_arrow_labels(arrow, {"above": "old"})
    before = snapshot_canvas_state_for(canvas)

    def drive(dialog):
        _fields(dialog)[0].setPlainText(raw)
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    assert _drive_modal(lambda: edit_arrow_labels_for(canvas, arrow), drive)
    after = snapshot_canvas_state_for(canvas)
    assert after["arrows"][0].get("labels", {}) == (
        {"above": raw} if raw.strip() else {}
    )
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    documents = canvas.services.document.canvas_document_session_service
    path = tmp_path / "edited.chemvas"
    assert documents.save_to_file(str(path)) == []
    documents.apply_state(read_document(path).state)
    assert snapshot_canvas_state_for(canvas) == after


def test_actual_arrow_double_click_multiline_export_save_reopen_and_undo(
    drawing, tmp_path
):
    _window, canvas = drawing
    canvas.services.input.tool_mode_controller.set_tool("arrow")
    start = canvas.mapFromScene(QPointF(-70, 0))
    end = canvas.mapFromScene(QPointF(70, 0))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    (arrow,) = arrow_items_for(canvas)
    canvas.services.input.tool_mode_controller.set_tool("select")
    before = snapshot_canvas_state_for(canvas)

    def drive(dialog):
        above, below = _fields(dialog)
        above.setPlainText("K_{2}CO_{3}\nDMSO")
        below.setFocus()
        QTest.keyClicks(below, "68%, 96% ee")
        QTest.keyClick(below, Qt.Key.Key_Return)
        QTest.keyClicks(below, "rt")
        QTest.mouseClick(_buttons(dialog)["OK"], Qt.MouseButton.LeftButton)

    _drive_modal(
        lambda: QTest.mouseDClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            pos=canvas.mapFromScene(QPointF()),
        ),
        drive,
    )
    after = snapshot_canvas_state_for(canvas)
    assert after["arrows"][0]["labels"] == {
        "above": "K_{2}CO_{3}\nDMSO",
        "below": "68%, 96% ee\nrt",
    }
    for child in arrow.childItems():
        assert child.toPlainText().count("\n") == 1
        assert child.document().firstBlock().layout().lineCount() == 2
        if child.data(1) == "above":
            assert child.sceneBoundingRect().bottom() < 0
        else:
            assert child.sceneBoundingRect().top() > 0
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    stacks = history.capture_stack_snapshot()
    documents = canvas.services.document.canvas_document_session_service
    for fmt in ("svg", "pdf", "png"):
        output = tmp_path / f"multiline.{fmt}"
        documents.export_figure(str(output), fmt=fmt, sizing="col1", dpi=300)
        assert output.stat().st_size > 0
        if fmt == "svg":
            assert b"<text" not in output.read_bytes()
        if fmt == "png":
            image = QImage(str(output))
            assert not image.isNull()
            painted_rows = [
                y
                for y in range(image.height())
                if any(
                    image.pixelColor(x, y).alpha() > 128
                    and image.pixelColor(x, y).lightness() < 128
                    for x in range(image.width())
                )
            ]
            bands = sum(
                index == 0 or y > painted_rows[index - 1] + 1
                for index, y in enumerate(painted_rows)
            )
            assert bands == 5  # Two lines above, the arrow, two lines below.
        assert snapshot_canvas_state_for(canvas) == after
        history.verify_stack_snapshot(stacks)
    path = tmp_path / "multiline.chemvas"
    assert documents.save_to_file(str(path)) == []
    saved = read_document(path).state
    assert saved["arrows"][0]["labels"] == after["arrows"][0]["labels"]
    documents.apply_state(saved)
    assert snapshot_canvas_state_for(canvas) == after
    (restored,) = arrow_items_for(canvas)
    assert all(
        child.document().firstBlock().layout().lineCount() == 2
        for child in restored.childItems()
    )
