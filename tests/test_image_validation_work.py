"""Existing embedded pixels are not repeatedly decoded on new insert/paste."""

import json
from io import BytesIO
from unittest import mock

import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import image_state_from_bytes, validate_image_states
from chemvas.domain.document import images as image_policy
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.image_actions import insert_image_bytes
from chemvas.ui.select_all_access import select_all_scene_items_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
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
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    for _ in items:
        history.undo()
    assert "images" not in snapshot_canvas_state_for(canvas)
    for _ in items:
        history.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_native_paste_revalidates_incoming_images_not_existing(canvas):
    for color in ("red", "blue", "green"):
        insert_image_bytes(canvas, _png(color))
    assert select_all_scene_items_for(canvas)
    controller = canvas.services.scene_operations.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    assert payload is not None
    before = snapshot_canvas_state_for(canvas)
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        assert controller.paste_selection_from_clipboard(
            payload_provider=lambda: (payload, json.dumps(payload))
        )
    assert inspect.call_count == 6
    pasted = snapshot_canvas_state_for(canvas)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == pasted


def test_aggregate_budget_refuses_before_new_raster_decode_or_history(
    canvas, monkeypatch
):
    insert_image_bytes(canvas, _png("red"))
    assert select_all_scene_items_for(canvas)
    controller = canvas.services.scene_operations.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    before = snapshot_canvas_state_for(canvas)
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
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(stack)


@pytest.mark.parametrize(
    "change",
    [{"data_base64": "!!!!"}, {"pixel_width": 25}, {"mime_type": "image/jpeg"}],
)
def test_untrusted_paste_still_validates_all_incoming_sources(canvas, change):
    insert_image_bytes(canvas, _png("red"))
    assert select_all_scene_items_for(canvas)
    controller = canvas.services.scene_operations.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    assert payload is not None
    payload["scene_items"][0].update(change)
    before = snapshot_canvas_state_for(canvas)
    stack = canvas.services.history_service.capture_stack_snapshot()
    with pytest.raises(ValueError):
        controller.paste_selection_from_clipboard(
            payload_provider=lambda: (payload, json.dumps(payload))
        )
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(stack)


def test_whole_document_validation_remains_strict_for_every_image():
    states = [image_state_from_bytes(_png(color)) for color in ("red", "blue", "green")]
    with mock.patch.object(
        image_policy, "_inspect_image_bytes", wraps=image_policy._inspect_image_bytes
    ) as inspect:
        validate_image_states(states)
    assert inspect.call_count == 3
