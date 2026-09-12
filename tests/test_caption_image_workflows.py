"""Visible Qt workflows for painted caption spacing and image rejection."""

from io import BytesIO

import pytest
from PIL import Image
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox

from chemvas.core.document_io import read_document
from chemvas.ui import image_actions
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_document_state import (
    document_item_lists_for,
    snapshot_canvas_document_state,
)
from chemvas.ui.canvas_history_state import history_state_for
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.scheme_layout_dialog import SchemeLayoutDialog, arrange_grouped_canvas
from tests.test_native_geometry_backlog import app as app
from tests.test_native_geometry_backlog import canvas as canvas
from tests.test_scheme_layout_caption_boxes import _source


def _assert_box_gaps(canvas):
    notes = document_item_lists_for(canvas)["notes"]
    for column in range(2):
        bottom = max(
            piece.sceneBoundingRect().bottom()
            for bond_id in range(column * 6, column * 6 + 6)
            for piece in bond_items_for(canvas)[bond_id]
        )
        for level in range(2):
            bounds = notes[column * 2 + level].data(20).sceneBoundingRect()
            assert bounds.top() >= bottom + (10 if level == 0 else 4) - 1e-8
            bottom = bounds.bottom()


@pytest.mark.parametrize("alignment", ["row", "structure"])
def test_visible_arrange_button_box_spacing_undo_save_reopen(
    canvas, app, tmp_path, alignment
):
    source = _source()
    source["groups"] = [
        {"atoms": list(range(6)), "items": [["notes", 0], ["notes", 1]]},
        {"atoms": list(range(6, 12)), "items": [["notes", 2], ["notes", 3]]},
    ]
    documents = canvas.services.document.canvas_document_session_service
    documents.apply_state(source)
    before = snapshot_canvas_document_state(canvas)
    dialog = SchemeLayoutDialog(
        before,
        parent=canvas,
        arrange=lambda request: arrange_grouped_canvas(canvas, before, request),
    )
    for column, entry in enumerate(dialog.group_widgets):
        entry.row.setValue(1)
        entry.captions.setText(f"{column * 2 + 1},{column * 2 + 2}")
    dialog.caption_alignment.setCurrentIndex(
        dialog.caption_alignment.findData(alignment)
    )
    dialog.show()
    app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    QTest.mouseClick(
        buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton
    )
    app.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error_label.text()
    _assert_box_gaps(canvas)
    arranged = snapshot_canvas_document_state(canvas)
    history = history_service_for_access(canvas)
    history.undo()
    assert snapshot_canvas_document_state(canvas) == before
    history.redo()
    assert snapshot_canvas_document_state(canvas) == arranged
    output = tmp_path / "boxed-caption.chemvas"
    assert documents.save_to_file(str(output)) == []
    documents.apply_state(read_document(output).state)
    _assert_box_gaps(canvas)
    dialog.close()


@pytest.mark.parametrize("image_format", ["BMP", "TIFF", "WEBP"])
def test_visible_insert_image_refusal_preserves_drawing_and_history(
    canvas, app, tmp_path, monkeypatch, image_format
):
    output = BytesIO()
    Image.new("RGB", (3, 2), "white").save(output, format=image_format)
    path = tmp_path / "misnamed.png"
    path.write_bytes(output.getvalue())
    before = snapshot_canvas_document_state(canvas)
    state = history_state_for(canvas)
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
