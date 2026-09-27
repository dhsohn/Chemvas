"""Visible Qt workflows for image rejection."""

from io import BytesIO

import pytest
from PIL import Image
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from chemvas.ui.canvas.canvas_document_state import (
    snapshot_canvas_document_state,
)
from chemvas.ui.scene import image_actions
from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas


@pytest.mark.parametrize("image_format", ["BMP", "TIFF", "WEBP"])
def test_visible_insert_image_refusal_preserves_drawing_and_history(
    canvas, app, tmp_path, monkeypatch, image_format
):
    output = BytesIO()
    Image.new("RGB", (3, 2), "white").save(output, format=image_format)
    path = tmp_path / "misnamed.png"
    path.write_bytes(output.getvalue())
    before = snapshot_canvas_document_state(canvas)
    state = canvas.runtime_state.history_state
    stacks = list(state.history), list(state.redo_stack)
    monkeypatch.setattr(
        image_actions.QFileDialog, "getOpenFileName", lambda *_: (str(path), "")
    )
    monkeypatch.setattr(image_actions, "active_canvas_for_window", lambda _: canvas)
    messages = []

    def close_warning():
        dialog = app.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            messages.append(dialog.text())
            QTest.keyClick(dialog, Qt.Key.Key_Return)

    timer = QTimer(canvas)
    timer.timeout.connect(close_warning)
    timer.start(50)
    try:
        image_actions.insert_image_for_window(canvas)
    finally:
        timer.stop()
    assert len(messages) == 1
    assert "Only PNG and JPEG" in messages[0]
    assert "convert" in messages[0]
    assert snapshot_canvas_document_state(canvas) == before
    assert (state.history, state.redo_stack) == stacks
    assert path.read_bytes() == output.getvalue()
