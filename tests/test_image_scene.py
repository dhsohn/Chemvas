import json
import os
from unittest import mock

import pytest

from chemvas.domain.document import AnnotationCollection
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QCoreApplication,
    QEvent,
    QIODevice,
    QPoint,
    QPointF,
    QRectF,
    Qt,
)
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    build_document_payload,
    extract_document_state,
    image_bytes_from_state,
    image_state_from_bytes,
)
from chemvas.domain.document import images as image_policy
from chemvas.features.selection import ROTATION_HANDLE_TYPE
from chemvas.ui.annotations.items import ImageItem
from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas.canvas_group_state import group_state_for
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas.canvas_scene_items_state import image_items_for
from chemvas.ui.history.history_commands import (
    DeleteSceneItemsCommand,
    UpdateSceneItemCommand,
)
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.scene.scene_group_operations import group_selection_for
from chemvas.ui.scene.scene_item_access import (
    create_scene_item_from_state,
    remove_scene_item,
)
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from chemvas.ui.selection.selection_state import selection_outlines_for
from chemvas.ui.transactions import document_transaction
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)
    app.processEvents()


def image_bytes(fmt="PNG"):
    image = QImage(12, 8, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    # Distinct edge pixels stand in for an axis label and a scale bar: neither
    # edge may be trimmed, including transparent margins.
    image.setPixelColor(0, 0, QColor("red"))
    image.setPixelColor(11, 7, QColor("blue"))
    image.setPixelColor(6, 4, QColor(0, 255, 0, 96))
    output = QByteArray()
    buffer = QBuffer(output)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, fmt, 100)
    buffer.close()
    return bytes(output)


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_full_raster_bytes_and_native_document_roundtrip(canvas, fmt):
    original = image_bytes(fmt)
    state = image_state_from_bytes(original, x=40, y=60, width=120, opacity=0.75)
    item = create_scene_item_from_state(canvas, state)
    assert isinstance(item, ImageItem)
    assert item.sceneBoundingRect() == QRectF(40, 60, 120, 80)
    assert image_items_for(canvas) == [item]

    snapshot = snapshot_canvas_document_state(canvas)
    payload = build_document_payload(snapshot, CANVAS_FILE_VERSION)
    restored = extract_document_state(json.loads(json.dumps(payload)))
    canvas.services.canvas_document_session_service.apply_state(restored)
    reopened = image_items_for(canvas)[0]
    assert reopened.image_state() == state
    assert image_bytes_from_state(reopened.image_state()) == original
    assert (reopened.image().width(), reopened.image().height()) == (12, 8)


def test_paint_preserves_full_image_and_alpha(app):
    item = ImageItem(
        image_state_from_bytes(image_bytes()), document=AnnotationCollection()
    )
    rendered = QImage(12, 8, QImage.Format.Format_ARGB32)
    rendered.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rendered)
    item.paint(painter, None)
    painter.end()
    assert rendered.pixelColor(0, 0) == QColor("red")
    assert rendered.pixelColor(11, 7) == QColor("blue")
    assert rendered.pixelColor(6, 4) == QColor(0, 255, 0, 96)
    assert item.boundingRect() == QRectF(0, 0, 12, 8)


def test_selection_move_properties_delete_and_history(canvas):
    operations = canvas.services.history_service.operations
    item = create_scene_item_from_state(canvas, image_state_from_bytes(image_bytes()))
    history = canvas.services.history_service
    assert select_all_scene_items_for(canvas)
    assert item.isSelected()
    assert any(
        outline.data(2).get("object_kind") == "image"
        for outline in selection_outlines_for(canvas)
    )
    transform = canvas.services.scene_transform_controller
    assert transform.translate_selected_items(20, 30)
    assert (item.image_state()["x"], item.image_state()["y"]) == (20, 30)
    history.undo()
    assert (item.image_state()["x"], item.image_state()["y"]) == (0, 0)
    history.redo()
    before = item.image_state()
    after = {
        **before,
        "width": 48.0,
        "height": 16.0,
        "opacity": 0.5,
        "lock_aspect": False,
    }
    command = UpdateSceneItemCommand(require_scene_record_id(item), before, after)
    command.redo(operations)
    history.push(command)
    assert item.image_state() == after
    history.undo()
    assert item.image_state() == before
    history.redo()
    deletion = DeleteSceneItemsCommand.capture(operations, [after], [item])
    remove_scene_item(canvas, item)
    history.push(deletion)
    assert not image_items_for(canvas)
    history.undo()
    assert image_items_for(canvas) == [item]
    assert item.image_state() == after
    history.redo()
    assert not image_items_for(canvas)
    assert "images" not in snapshot_canvas_document_state(canvas)


def test_native_selection_copy_paste_keeps_images_and_groups(canvas):
    first = create_scene_item_from_state(canvas, image_state_from_bytes(image_bytes()))
    second = create_scene_item_from_state(
        canvas, image_state_from_bytes(image_bytes("JPEG"), x=50)
    )
    assert select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    clipboard = canvas.services.scene_clipboard_controller
    assert clipboard.copy_selection_to_clipboard()
    payload, payload_json = clipboard.clipboard_selection_payload()
    assert payload is not None
    assert len(payload["scene_items"]) == 2
    assert clipboard.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, payload_json)
    )
    pasted = [item for item in image_items_for(canvas) if item not in (first, second)]
    assert len(pasted) == 2
    assert {item.image_state()["data_base64"] for item in pasted} == {
        first.image_state()["data_base64"],
        second.image_state()["data_base64"],
    }
    assert all(item.image_state()["y"] > 0 for item in pasted)
    snapshot = snapshot_canvas_document_state(canvas)
    assert len(snapshot["groups"]) == 2
    assert all(
        kind == "images" for group in snapshot["groups"] for kind, _ in group["items"]
    )
    history = canvas.services.history_service
    history.undo()
    assert image_items_for(canvas) == [first, second]
    assert len(group_state_for(canvas).groups) == 1
    history.redo()
    assert len(image_items_for(canvas)) == 4


def test_geometry_failure_restores_exact_image_and_registration(canvas):
    item = create_scene_item_from_state(canvas, image_state_from_bytes(image_bytes()))
    before = item.image_state()
    with pytest.raises(RuntimeError, match="injected"):
        with document_transaction(
            canvas, history_service=canvas.services.history_service
        ):
            item.apply_image_state(
                {**before, "width": 240.0, "opacity": 0.25, "lock_aspect": False}
            )
            item.moveBy(300, -20)
            remove_scene_item(canvas, item)
            raise RuntimeError("injected after geometry and registration changes")
    assert image_items_for(canvas) == [item]
    assert item.scene() is canvas.scene()
    assert scene_item_state_for(canvas, item) == before


def test_source_replacement_fails_without_altering_pixels(app):
    item = ImageItem(
        image_state_from_bytes(image_bytes()), document=AnnotationCollection()
    )
    before = item.image_state()
    with pytest.raises(ValueError, match="source cannot be replaced"):
        item.apply_image_state(image_state_from_bytes(image_bytes("JPEG")))
    assert item.image_state() == before


@pytest.mark.parametrize(
    "change",
    [
        {"width": 0},
        {"height": float("nan")},
        {"x": float("inf")},
        {"y": True},
        {"opacity": 1.01},
        {"lock_aspect": 1},
        {"pixel_width": True},
        {"pixel_width": 13},
        {"pixel_height": 9},
        {"mime_type": "image/jpeg"},
        {"data_base64": "AAAA"},
        {"data_base64": "!!!!"},
        {"kind": "note"},
        {"unexpected": 1},
    ],
)
def test_invalid_image_update_preserves_geometry_source_and_pixels(app, change):
    item = ImageItem(
        image_state_from_bytes(image_bytes(), x=20, y=30, width=120),
        document=AnnotationCollection(),
    )
    before = item.image_state()
    pixels = item.image()
    with pytest.raises(ValueError):
        item.apply_image_state({**before, **change})
    assert item.image_state() == before
    assert item.image() == pixels


@pytest.mark.parametrize("finish", ["release", "escape"])
def test_rotation_pointer_preview_preserves_images_and_single_history(
    canvas, app, finish, request
):
    canvas.resize(800, 600)
    canvas.services.tool_controller.set_active("select")
    request.addfinalizer(app.processEvents)
    request.addfinalizer(canvas.services.tool_controller.prepare_for_document_edit)
    # Images keep upright pixels; a molecular selection supplies the real knob
    # while the images' positions rotate with the mixed selection.
    add_bond_between_points_for(canvas, QPointF(-20, 0), QPointF(20, 0))
    items = [
        create_scene_item_from_state(
            canvas,
            image_state_from_bytes(image_bytes(fmt), x=x, y=20, width=72),
        )
        for fmt, x in (("PNG", -90), ("JPEG", 90))
    ]
    canvas.show()
    canvas.centerOn(0, 0)
    app.processEvents()
    assert select_all_scene_items_for(canvas)
    before = snapshot_canvas_document_state(canvas)
    pixels = [item.image() for item in items]
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    knob = next(
        item for item in canvas.scene().items() if item.data(1) == ROTATION_HANDLE_TYPE
    )
    start = canvas.mapFromScene(knob.sceneBoundingRect().center())
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    assert canvas.services.tool_controller.active._rotation_session is not None
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        for delta in (QPoint(15, 10), QPoint(30, 20), QPoint(45, 25)):
            position = start + delta
            # Deliver a real viewport event without relying on compositor cursor warps.
            event = QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(position),
                QPointF(canvas.viewport().mapToGlobal(position)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(canvas.viewport(), event)
    preview = snapshot_canvas_document_state(canvas)
    assert preview != before
    history.verify_stack_snapshot(stacks)
    if finish == "escape":
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    app.processEvents()
    assert [item.image() for item in items] == pixels
    if finish == "escape":
        assert snapshot_canvas_document_state(canvas) == before
        history.verify_stack_snapshot(stacks)
    else:
        assert snapshot_canvas_document_state(canvas) == preview
        command = history.capture_stack_snapshot().history[-1]
        history.verify_stack_snapshot(stacks, history=(*stacks.history, command))
        history.undo()
        assert snapshot_canvas_document_state(canvas) == before
        history.redo()
        assert snapshot_canvas_document_state(canvas) == preview
    assert inspect.call_count == 0


@pytest.mark.parametrize("tool", ["select", "move"])
def test_pointer_drag_and_keyboard_delete_use_native_history(canvas, app, tool):
    canvas.resize(800, 600)
    canvas.services.tool_controller.set_active(tool)
    item = create_scene_item_from_state(
        canvas, image_state_from_bytes(image_bytes(), x=40.0, y=50.0, width=120.0)
    )
    canvas.show()
    canvas.centerOn(item)
    app.processEvents()
    start = canvas.mapFromScene(item.sceneBoundingRect().center())
    delta = QPoint(30, 20)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start + delta)
    app.processEvents()
    if tool == "select":
        assert item.isSelected()
    assert (item.image_state()["x"], item.image_state()["y"]) == (70.0, 70.0)
    history = canvas.services.history_service
    history.undo()
    assert (item.image_state()["x"], item.image_state()["y"]) == (40.0, 50.0)
    history.redo()
    item.setSelected(True)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert not image_items_for(canvas)
    history.undo()
    assert image_items_for(canvas) == [item]
    assert (item.image_state()["x"], item.image_state()["y"]) == (70.0, 70.0)
