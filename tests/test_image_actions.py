from __future__ import annotations

import os
from io import BytesIO

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document import image_bytes_from_state, image_state_from_bytes
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_scene_items_state import image_items_for
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.image_actions import (
    ImagePropertiesDialog,
    image_bytes_from_mime,
    insert_image_bytes,
    update_image_properties,
)
from chemvas.ui.scene_clipboard_controller import SceneClipboardController


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _png():
    image = Image.new("RGBA", (80, 40), (20, 80, 160, 128))
    image.putpixel((79, 39), (255, 0, 0, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _empty():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
        }
    )


def test_file_image_insert_properties_undo_redo_and_failed_history(monkeypatch):
    data = _png()
    with offscreen_canvas(_empty(), command="image-actions") as (canvas, _service):
        before = snapshot_canvas_document_state(canvas)
        item = insert_image_bytes(canvas, data)
        inserted = item.image_state()
        assert item.isSelected()
        assert image_bytes_from_state(inserted) == data
        assert inserted["width"] / inserted["height"] == 2
        history = history_service_for_access(canvas)
        history.undo()
        assert snapshot_canvas_document_state(canvas) == before
        history.redo()
        assert image_items_for(canvas) == [item]
        changed = {
            **inserted,
            "x": -10.25,
            "width": 310.5,
            "height": 80.25,
            "opacity": 0.35,
            "lock_aspect": False,
        }
        assert update_image_properties(canvas, item, changed)
        assert item.image_state() == changed
        history.undo()
        assert item.image_state() == inserted
        history.redo()
        assert item.image_state() == changed
        snapshot = snapshot_canvas_document_state(canvas)
        with monkeypatch.context() as patch:
            patch.setattr(history, "push", lambda _command: False)
            with pytest.raises(ValueError, match="History is disabled"):
                update_image_properties(canvas, item, {**changed, "width": 500})
            assert snapshot_canvas_document_state(canvas) == snapshot
            with pytest.raises(ValueError, match="History is disabled"):
                insert_image_bytes(canvas, data)
            assert snapshot_canvas_document_state(canvas) == snapshot


def test_properties_dialog_exact_noop_ratio_and_opacity():
    state = image_state_from_bytes(_png(), x=1.123456789, width=193.123456789)
    dialog = ImagePropertiesDialog(state)
    assert dialog.image_state() == state
    dialog.fields["width"].setValue(300)
    assert dialog.fields["height"].value() == 150
    dialog.fields["height"].setValue(100)
    assert dialog.fields["width"].value() == 200
    dialog.lock_aspect.setChecked(False)
    dialog.fields["height"].setValue(50)
    assert dialog.fields["width"].value() == 200
    dialog.opacity.setValue(37.5)
    result = dialog.image_state()
    assert result["opacity"] == 0.375
    assert result["lock_aspect"] is False
    assert image_bytes_from_state(result) == _png()
    dialog.close()


@pytest.mark.parametrize(
    "zoom,center", [(1, (0, 0)), (0.2, (0, 0)), (4, (380, 270)), (2, (3000, 3000))]
)
def test_initial_image_fits_sheet_even_in_wide_zoomed_or_panned_view(
    application, zoom, center
):
    from chemvas.ui.sheet_setup_access import sheet_rect_for

    output = BytesIO()
    Image.new("RGB", (2400, 800), "white").save(output, format="PNG")
    with offscreen_canvas(_empty(), command="image-insert-sheet") as (canvas, _service):
        canvas.resize(1600, 900)
        canvas.show()
        canvas.scale(zoom, zoom)
        canvas.centerOn(*center)
        application.processEvents()
        item = insert_image_bytes(canvas, output.getvalue())
        assert sheet_rect_for(canvas).contains(item.sceneBoundingRect())
        assert item.rect().width() / item.rect().height() == pytest.approx(3)
        assert image_bytes_from_state(item.image_state()) == output.getvalue()
        # Flush the live view's queued hover refresh before the CLI context
        # deletes it; that context normally never exposes a widget.
        application.processEvents()


def test_properties_noop_preserves_values_beyond_display_spin_range():
    state = image_state_from_bytes(_png(), x=2_000_000, width=0.000001)
    dialog = ImagePropertiesDialog(state)
    assert dialog.image_state() == state
    dialog.close()


def test_overbudget_paste_and_copy_preserve_document_history_and_clipboard(
    application, monkeypatch
):
    import json

    from chemvas.domain.document import images
    from chemvas.ui import scene_clipboard_controller

    messages = []
    monkeypatch.setattr(
        scene_clipboard_controller.QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(message),
    )
    with offscreen_canvas(_empty(), command="image-budget") as (canvas, _service):
        item = insert_image_bytes(canvas, _png())
        controller = SceneClipboardController(canvas)
        payload = controller.selection_payload_for_clipboard()
        before = snapshot_canvas_document_state(canvas)
        with monkeypatch.context() as patch:
            patch.setattr(images, "MAX_DOCUMENT_IMAGES", 1)
            with pytest.raises(
                ValueError, match="Images must be an array of at most 1"
            ):
                controller.paste_selection_from_clipboard(
                    payload_provider=lambda: (payload, json.dumps(payload))
                )
            assert snapshot_canvas_document_state(canvas) == before
        update_image_properties(
            canvas, item, {**item.image_state(), "width": 1_000_000}
        )
        oversized = snapshot_canvas_document_state(canvas)
        application.clipboard().setText("previous clipboard remains")
        assert not controller.copy_selection_to_clipboard()
        assert "too large" in messages[-1]
        assert application.clipboard().text() == "previous clipboard remains"
        assert snapshot_canvas_document_state(canvas) == oversized
        history_service_for_access(canvas).undo()
        assert snapshot_canvas_document_state(canvas) == before
        history_service_for_access(canvas).undo()
        assert image_items_for(canvas) == []
        application.clipboard().clear()


def test_native_clipboard_preserves_raw_bytes_and_memory_pixels(application):
    data = _png()
    mime = QMimeData()
    mime.setData("image/png", data)
    assert image_bytes_from_mime(mime) == data
    source = QImage.fromData(data)
    bitmap_mime = QMimeData()
    bitmap_mime.setImageData(source)
    encoded = image_bytes_from_mime(bitmap_mime)
    assert encoded is not None
    decoded = QImage.fromData(encoded).convertToFormat(QImage.Format.Format_RGBA8888)
    assert decoded == source.convertToFormat(QImage.Format.Format_RGBA8888)
    with offscreen_canvas(_empty(), command="image-clipboard") as (canvas, _service):
        application.clipboard().setMimeData(bitmap_mime)
        controller = SceneClipboardController(canvas)
        assert controller.paste_selection_from_clipboard()
        assert len(image_items_for(canvas)) == 1
        history_service_for_access(canvas).undo()
        assert image_items_for(canvas) == []
        application.clipboard().clear()


def test_malformed_clipboard_shows_reason_and_leaves_canvas_unchanged(
    application, monkeypatch
):
    from chemvas.ui import scene_clipboard_controller

    messages = []
    monkeypatch.setattr(
        scene_clipboard_controller.QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(message),
    )
    with offscreen_canvas(_empty(), command="image-invalid") as (canvas, _service):
        before = snapshot_canvas_document_state(canvas)
        mime = QMimeData()
        mime.setData("image/png", b"not a PNG")
        application.clipboard().setMimeData(mime)
        assert not SceneClipboardController(canvas).paste_selection_from_clipboard()
        assert messages
        assert snapshot_canvas_document_state(canvas) == before
        application.clipboard().clear()


def test_overlapping_native_note_and_image_paint_identically_after_reload_and_undo():
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainter

    from chemvas.ui.history_commands import DeleteSceneItemsCommand
    from chemvas.ui.scene_item_access import (
        create_scene_item_from_state,
        remove_scene_item,
    )

    state = _empty()
    state["notes"] = [{"text": "SCALE BAR", "x": 5, "y": 5}]
    with offscreen_canvas(state, command="image-layer") as (canvas, service):
        opaque = BytesIO()
        Image.new("RGB", (80, 40), "white").save(opaque, format="PNG")
        item = create_scene_item_from_state(
            canvas, image_state_from_bytes(opaque.getvalue())
        )

        def render():
            result = QImage(80, 40, QImage.Format.Format_ARGB32)
            result.fill(0xFFFFFFFF)
            painter = QPainter(result)
            canvas.scene().render(painter, QRectF(0, 0, 80, 40), QRectF(0, 0, 80, 40))
            painter.end()
            return result

        before = render()
        deletion = DeleteSceneItemsCommand.capture(canvas, [item.image_state()], [item])
        remove_scene_item(canvas, item)
        history_service_for_access(canvas).push(deletion)
        history_service_for_access(canvas).undo()
        assert render() == before
        saved = snapshot_canvas_document_state(canvas)
        service.apply_state(saved)
        assert render() == before
