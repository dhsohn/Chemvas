from __future__ import annotations

import json
import os
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, Qt, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_format_access import clipboard_selection_mime_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.scene_clipboard_access import clipboard_paste_count_for
from chemvas.ui.scene_clipboard_controller import SceneClipboardController
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module", autouse=True)
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.close()
    view.deleteLater()
    app.processEvents()


def _payload(**changes):
    payload = dict(
        format="chemvas-selection",
        version=2,
        atoms=[],
        bonds=[],
        rings=[],
        marks=[],
        scene_items=[dict(kind="note", text="synthetic", x=0, y=0)],
    )
    return json.dumps(payload | changes).encode()


@pytest.mark.parametrize(
    "data,reason",
    [
        (_payload(version=3), "version"),
        (_payload(version=1), "version"),
        (_payload(version=2.0), "version"),
        (b'{"format":', "damaged"),
        (b"\xff", "UTF-8"),
        (b"{}" * 1025, "too large"),
        (_payload(format="unrelated"), "format"),
        (_payload(atoms=[{"id": 1}]), "invalid"),
    ],
    ids=[
        "new-version",
        "old-version",
        "float-version",
        "truncated",
        "invalid-utf8",
        "oversized",
        "wrong-format",
        "invalid-content",
    ],
)
@pytest.mark.parametrize("with_image", [False, True])
def test_refused_native_clipboard_shows_reason_without_fallback_or_mutation(
    canvas, data, reason, with_image
):
    mime = QMimeData()
    mime.setData(clipboard_selection_mime_for(canvas), data)
    if with_image:
        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        image.fill(0xFF123456)
        mime.setImageData(image)
    controller = SceneClipboardController(canvas)
    clipboard = Mock(mimeData=Mock(return_value=mime))
    state = snapshot_canvas_document_state(canvas)
    history = canvas_services_for(canvas).history_service.capture_stack_snapshot()
    paste_count = clipboard_paste_count_for(canvas)
    with (
        patch.object(controller, "_clipboard", return_value=clipboard),
        patch(
            "chemvas.ui.scene_clipboard_logic.MAX_CLIPBOARD_SELECTION_PAYLOAD_BYTES",
            2048,
        ),
        patch("chemvas.ui.scene_clipboard_controller.QMessageBox.warning") as warning,
        patch(
            "chemvas.ui.scene_clipboard_controller.insert_image_bytes"
        ) as image_insert,
    ):
        assert not controller.paste_selection_from_clipboard()
    warning.assert_called_once()
    assert warning.call_args.args[1] == "Paste"
    assert reason in warning.call_args.args[2]
    image_insert.assert_not_called()
    assert snapshot_canvas_document_state(canvas) == state
    canvas_services_for(canvas).history_service.verify_stack_snapshot(history)
    assert clipboard_paste_count_for(canvas) == paste_count


def test_absent_native_mime_still_allows_image_paste(canvas):
    mime = QMimeData()
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(0xFF123456)
    mime.setImageData(image)
    controller = SceneClipboardController(canvas)
    with (
        patch.object(
            controller,
            "_clipboard",
            return_value=Mock(mimeData=Mock(return_value=mime)),
        ),
        patch("chemvas.ui.scene_clipboard_controller.QMessageBox.warning") as warning,
    ):
        assert controller.paste_selection_from_clipboard()
    warning.assert_not_called()
    assert len(canvas.runtime_state.scene_items_state.image_items) == 1


def test_valid_native_clipboard_pastes_editable_content(canvas):
    mime = QMimeData()
    mime.setData(clipboard_selection_mime_for(canvas), _payload())
    controller = canvas_services_for(canvas).scene_operations.scene_clipboard_controller
    with patch.object(
        controller, "_clipboard", return_value=Mock(mimeData=Mock(return_value=mime))
    ):
        assert controller.paste_selection_from_clipboard()
    notes = canvas.runtime_state.scene_items_state.note_items
    assert len(notes) == 1 and notes[0].toPlainText() == "synthetic"
    canvas_services_for(canvas).history_service.undo()
    assert not canvas.runtime_state.scene_items_state.note_items
    canvas_services_for(canvas).history_service.redo()
    assert (
        canvas.runtime_state.scene_items_state.note_items[0].toPlainText()
        == "synthetic"
    )


def test_qt_paste_shortcut_shows_real_refusal_dialog(canvas, app):
    canvas.show()
    canvas.setFocus()
    app.processEvents()
    mime = QMimeData()
    mime.setData(clipboard_selection_mime_for(canvas), _payload(version=3))
    app.clipboard().setMimeData(mime)
    state = snapshot_canvas_document_state(canvas)
    messages = []
    responder = QTimer(canvas)
    responder.setInterval(10)

    def accept_dialog():
        dialog = app.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            messages.append((dialog.windowTitle(), dialog.text(), dialog.isVisible()))
            dialog.accept()

    responder.timeout.connect(accept_dialog)
    responder.start()
    try:
        QTest.keyClick(
            canvas.viewport(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier
        )
    finally:
        responder.stop()
        app.clipboard().clear()
    assert len(messages) == 1
    assert messages[0][0] == "Paste" and "unsupported version" in messages[0][1]
    assert messages[0][2]
    assert snapshot_canvas_document_state(canvas) == state
