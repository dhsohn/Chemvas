from chemvas.domain.document import AnnotationCollection

"""Immutable live pixels are not repeatedly decoded by scene editing."""

import json
import math
from io import BytesIO
from unittest import mock

import pytest
from PIL import Image
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import image_state_from_bytes, validate_image_states
from chemvas.domain.document import images as image_policy
from chemvas.ui.annotations.items import ImageItem
from chemvas.ui.scene.image_actions import insert_image_bytes
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()


def _png(color):
    stream = BytesIO()
    Image.new("RGB", (24, 12), color).save(stream, format="PNG")
    return stream.getvalue()


def test_successive_insert_inspects_only_the_new_source(canvas):
    items = []
    for color in ("red", "blue", "green", "orange", "purple"):
        data = _png(color)
        with mock.patch.object(
            image_policy,
            "_inspect_image_bytes",
            wraps=image_policy._inspect_image_bytes,
        ) as inspect:
            items.append(insert_image_bytes(canvas, data))
        # The incoming bytes and ImageItem materialization remain strict.
        assert inspect.call_count == 2
        assert all(call.args[0] == data for call in inspect.call_args_list)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    for _ in items:
        history.undo()
    assert (
        "images" not in canvas.services.canvas_document_session_service.snapshot_state()
    )
    for _ in items:
        history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


def test_native_paste_revalidates_incoming_images_not_existing(canvas):
    for color in ("red", "blue", "green"):
        insert_image_bytes(canvas, _png(color))
    assert canvas.services.selection.select_all()
    controller = canvas.services.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    assert payload is not None
    before = canvas.services.canvas_document_session_service.snapshot_state()
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        assert controller.paste_selection_from_clipboard(
            payload_provider=lambda: (payload, json.dumps(payload))
        )
    assert inspect.call_count == 6
    pasted = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == pasted


def test_aggregate_budget_refuses_before_new_raster_decode_or_history(
    canvas, monkeypatch
):
    insert_image_bytes(canvas, _png("red"))
    assert canvas.services.selection.select_all()
    controller = canvas.services.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    stack = canvas.services.history_service.capture_stack_snapshot()
    monkeypatch.setattr(image_policy, "MAX_DOCUMENT_IMAGES", 1)
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        with pytest.raises(ValueError, match="at most 1"):
            controller.paste_selection_from_clipboard(
                payload_provider=lambda: (payload, json.dumps(payload))
            )
    inspect.assert_not_called()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(stack)


@pytest.mark.parametrize(
    "change",
    [{"data_base64": "!!!!"}, {"pixel_width": 25}, {"mime_type": "image/jpeg"}],
)
def test_untrusted_paste_still_validates_all_incoming_sources(canvas, change):
    insert_image_bytes(canvas, _png("red"))
    assert canvas.services.selection.select_all()
    controller = canvas.services.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    assert payload is not None
    payload["scene_items"][0].update(change)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    stack = canvas.services.history_service.capture_stack_snapshot()
    with pytest.raises(ValueError):
        controller.paste_selection_from_clipboard(
            payload_provider=lambda: (payload, json.dumps(payload))
        )
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(stack)


def test_whole_document_validation_remains_strict_for_every_image():
    states = [image_state_from_bytes(_png(color)) for color in ("red", "blue", "green")]
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        validate_image_states(states)
    assert inspect.call_count == 3


def test_rotation_preview_and_history_do_not_decode_unchanged_sources(canvas):
    items = [
        canvas.services.scene_item_controller.create_scene_item_from_state(
            image_state_from_bytes(_png(color), x=index * 90, width=48, height=24)
        )
        for index, color in enumerate(("red", "blue"))
    ]
    assert canvas.services.selection.select_all()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    pixels = [item.image() for item in items]
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    controller = canvas.services.scene_transform_controller
    session = controller.begin_rotation_drag(QPointF(300, 0))
    assert session is not None
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        for index in range(1, 11):
            angle = 0.06 * index
            controller.update_rotation_drag(
                session,
                session.center + QPointF(200 * math.cos(angle), 200 * math.sin(angle)),
            )
    assert inspect.call_count == 0
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert after != before
    history.verify_stack_snapshot(stacks)
    command = controller.rotation_drag_command(session)
    assert command is not None
    assert history.push(command)
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        history.undo()
        assert [item.image_state() for item in items] == before["images"]
        history.redo()
        assert [item.image_state() for item in items] == after["images"]
    assert inspect.call_count == 0
    history.verify_stack_snapshot(stacks, history=(*stacks.history, command))
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    assert [item.image() for item in items] == pixels
    for old, new in zip(before["images"], after["images"], strict=True):
        assert {key: value for key, value in old.items() if key not in {"x", "y"}} == {
            key: value for key, value in new.items() if key not in {"x", "y"}
        }


def test_image_constructor_still_decodes_and_rejects_false_source_metadata(app):
    state = image_state_from_bytes(_png("red"))
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        item = ImageItem(state, document=AnnotationCollection())
    assert inspect.call_count == 1
    assert item.image_state() == state
    with pytest.raises(ValueError, match="dimensions do not match"):
        ImageItem({**state, "pixel_width": 25}, document=AnnotationCollection())
