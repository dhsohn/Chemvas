"""Losing annotation projections must not edit their document records."""

from __future__ import annotations

import gc
import json
import weakref
from io import BytesIO
from unittest import mock

import pytest
from PIL import Image
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtTest import QTest

from chemvas.core.document_io import read_document
from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.export.layout_qa_service import check_canvas_layout
from chemvas.ui.history.history_commands import AddSceneItemsCommand
from chemvas.ui.history.history_operations import CanvasHistoryOperations
from chemvas.ui.molecule.structure_mutation_access import add_benzene_ring_for
from chemvas.ui.scene.image_actions import insert_image_bytes, update_image_properties
from tests.canvas_factory import build_canvas_view
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def _annotations(canvas, kind):
    service = canvas.services.scene_decoration_service
    if kind == "ring":
        for index in range(3):
            add_benzene_ring_for(canvas, QPointF(index * 100, 0))
        return canvas.runtime_state.ring_items()
    if kind == "mark":
        return [
            service.add_mark(QPointF(20.125 + i * 100, 30.25), kind=mark_kind)
            for i, mark_kind in enumerate(("plus", "radical", "circled_minus"))
        ]
    if kind == "note":
        controller = canvas.services.note_controller
        items = []
        for index in range(3):
            item = controller.create_text_note(
                QPointF(20.125 + index * 100, 30.25), f"note {index}"
            )
            item.setHtml(f"<p>note <b>{index}</b> H<sub>2</sub>O</p>")
            controller.apply_note_style(item)
            canvas.services.history_service.push(
                AddSceneItemsCommand.from_items([item.note_state()], [item])
            )
            items.append(item)
        return items
    if kind == "image":
        encoded = BytesIO()
        Image.new("RGB", (8, 4), "blue").save(encoded, "PNG")
        items = [insert_image_bytes(canvas, encoded.getvalue()) for _ in range(3)]
        for item in items:
            item.setSelected(False)
        return items
    if kind == "orbital":
        return [service.add_orbital(QPointF(i * 100, 30)) for i in range(3)]
    if kind == "arrow":
        return [
            service.add_arrow(
                QPointF(20.125 + i * 100, 30.25),
                QPointF(80.625 + i * 100, 71.0),
                arrow_kind,
            )
            for i, arrow_kind in enumerate(("arrow", "equilibrium", "curved_single"))
        ]
    if kind == "ts_bracket":
        return [
            service.add_ts_bracket(
                QRectF(20.125 + i * 100, 30.25, 60.5, 40.75), bracket_kind=bracket_kind
            )
            for i, bracket_kind in enumerate(
                ("square_pair", "double_dagger", "braces_pair")
            )
        ]
    return [
        service.add_shape(
            QRectF(20.125 + index * 100, 30.25, 60.5, 40.75),
            shape_kind=kind,
            stroke_style=stroke,
        )
        for index, (kind, stroke) in enumerate(
            zip(
                ("rect", "ellipse", "rounded_rect"),
                ("solid", "dashed", "dotted"),
                strict=True,
            )
        )
    ]


@pytest.fixture(
    params=["shape", "arrow", "ts_bracket", "image", "orbital", "note", "mark"]
)
def kind(request):
    return request.param


def _document(canvas, kind):
    return getattr(canvas.runtime_state, f"{kind}_state")


def _views(canvas, kind):
    return getattr(canvas.runtime_state.scene_items_state, f"{kind}_items")


def _ordered_views(canvas, kind):
    return canvas.runtime_state.scene_items(f"{kind}_items")


@pytest.mark.parametrize(
    "kind", ["shape", "arrow", "ts_bracket", "image", "orbital", "note", "mark", "ring"]
)
@pytest.mark.parametrize(
    "failure_phase", ["populate_document_scene", "restore_document_groups"]
)
def test_failed_document_replacement_preserves_annotation_owners_and_history(
    canvas, kind, failure_phase
):
    items = _annotations(canvas, kind)
    history = canvas.services.history_service
    history.undo()
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    document = _document(canvas, kind)
    records, order = document.records, document.order
    records_before, order_before = dict(records), list(order)
    views = _views(canvas, kind)
    views_before = dict(views)
    scene_before = tuple(canvas.scene().items())
    undo, redo = history.state.history, history.state.redo_stack
    undo_before, redo_before = tuple(undo), tuple(redo)
    assert undo_before and redo_before
    primary = RuntimeError("replacement failed after scene reset")

    with mock.patch(
        f"chemvas.ui.canvas.canvas_document_session_service.{failure_phase}",
        side_effect=primary,
    ):
        with pytest.raises(RuntimeError) as raised:
            session.apply_state(before)

    assert raised.value is primary
    assert session.snapshot_state() == before
    assert _document(canvas, kind) is document
    assert document.records is records and records == records_before
    assert document.order is order and order == order_before
    assert _views(canvas, kind) is views and views == views_before
    assert tuple(canvas.scene().items()) == scene_before
    assert history.state.history is undo and tuple(undo) == undo_before
    assert history.state.redo_stack is redo and tuple(redo) == redo_before
    history.redo()
    assert _ordered_views(canvas, kind) == items
    history.undo()
    assert session.snapshot_state() == before


@pytest.mark.parametrize("loss", ["detach", "destroy", "release"])
def test_projection_loss_preserves_saved_annotations_and_later_group_indices(
    canvas, kind, tmp_path, loss
):
    items = _annotations(canvas, kind)
    register_group_for(
        canvas, set(), [require_scene_record_id(item) for item in items[1:]]
    )
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    document = _document(canvas, kind)
    record_id = items[0].data(3)
    item = items.pop(0)
    if loss == "destroy":
        sip.delete(item)
    else:
        canvas.scene().removeItem(item)
    if loss == "release":
        _views(canvas, kind).pop(record_id)
        canvas.services.history_service.clear()
        reference = weakref.ref(item)
        del item
        gc.collect()
        assert reference() is None

    assert session.snapshot_state() == before
    assert record_id in document.order
    assert record_id in document.records
    assert check_canvas_layout(canvas)["ok"] is True
    destination = tmp_path / "projection-loss.chemvas"
    session.save_to_file(str(destination))
    assert read_document(destination).state[f"{kind}s"] == json.loads(
        json.dumps(before[f"{kind}s"])
    )
    assert read_document(destination).state["groups"] == before["groups"]
    session.apply_state(read_document(destination).state)
    assert session.snapshot_state() == before
    assert len(_ordered_views(canvas, kind)) == 3


def test_projection_lookup_order_does_not_control_saving_or_group_indices(canvas, kind):
    items = _annotations(canvas, kind)
    register_group_for(
        canvas, set(), [require_scene_record_id(item) for item in [items[0], items[2]]]
    )
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    views = _views(canvas, kind)
    entries = list(views.items())
    views.clear()
    views.update(reversed(entries))

    # Even querying Qt identity is unnecessary when writing annotation values.
    with mock.patch.object(items[0], "data", side_effect=AssertionError("Qt read")):
        assert session.snapshot_state() == before
    assert _ordered_views(canvas, kind) == items


@pytest.mark.parametrize("kind", ["image", "orbital"])
def test_saved_values_and_partial_edits_ignore_corrupted_projection_geometry(
    canvas, kind
):
    item = _annotations(canvas, kind)[0]
    if kind == "image":
        update_image_properties(
            canvas, item, {**item.image_state(), "opacity": 0.6, "z": -3.5}
        )
        state = item.image_state()
    else:
        item.apply_orbital_state({"scale": 1.5, "rotation": 30})
        state = item.orbital_state()
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    bounds = item.sceneBoundingRect()

    item.setPos(999, -555)
    item.setData(1, {"center": QPointF(-999, 999), "base_handle_dist": 900})
    if kind == "image":
        item.setRect(0, 0, 1, 1)
        item.setOpacity(0.1)
        item.setZValue(900)
    else:
        item.setScale(12)
        item.setRotation(135)
        item.setData(2, {"kind": "dxy"})

    assert session.snapshot_state() == before
    # An orbital position edit must keep the document's existing size/rotation,
    # even when omitted fields disagree with the corrupted projection.
    canvas.services.scene_item_controller.apply_scene_item_state(
        item,
        state if kind == "image" else {"kind": "orbital", "center": state["center"]},
    )
    assert session.snapshot_state() == before
    assert item.sceneBoundingRect() == bounds
    if kind == "image":
        assert item.opacity() == 0.6
        assert item.zValue() == -3.5
    else:
        assert item.scale() == 1.5
        assert item.rotation() == 30
        assert item.data(2)["kind"] == state["orbital_kind"]


def test_orbital_handle_edits_use_document_center_after_projection_corruption(canvas):
    item = _annotations(canvas, "orbital")[0]
    center = QPointF(*item.orbital_state()["center"])
    mutation = canvas.services.handle_mutation_service
    item.setData(1, {"center": QPointF(-1000, 1000), "base_handle_dist": 999})
    mutation.update_orbital_scale(item, center + QPointF(item.base_handle_dist * 2, 0))
    assert item.orbital_state()["scale"] == 2
    item.setData(1, {"center": QPointF(-1000, 1000)})
    mutation.update_orbital_rotate(item, center + QPointF(0, item.base_handle_dist))
    assert item.orbital_state()["rotation"] == 90
    assert item.orbital_state()["center"] == (center.x(), center.y())


@pytest.mark.parametrize("operation", ["insert", "paste"])
def test_image_budget_counts_document_images_after_projection_loss(
    canvas, monkeypatch, operation
):
    from chemvas.domain.document import images
    from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController

    items = _annotations(canvas, "image")
    items[1].setSelected(True)
    clipboard = SceneClipboardController(canvas)
    payload = clipboard.selection_payload_for_clipboard()
    data = images.image_bytes_from_state(items[0].image_state())
    sip.delete(items[0])
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    history = canvas.services.history_service
    history_before = (history.can_undo(), history.can_redo())
    monkeypatch.setattr(images, "MAX_DOCUMENT_IMAGES", 3)

    with pytest.raises(ValueError, match="Images must be an array of at most 3"):
        if operation == "insert":
            insert_image_bytes(canvas, data)
        else:
            clipboard.paste_selection_from_clipboard(
                payload_provider=lambda: (payload, json.dumps(payload))
            )

    assert session.snapshot_state() == before
    assert (history.can_undo(), history.can_redo()) == history_before


@pytest.mark.parametrize("deleted_indices", [(1,), (0, 2)])
def test_delete_undo_redo_restores_document_order_and_group_references(
    canvas, kind, deleted_indices
):
    items = _annotations(canvas, kind)
    register_group_for(
        canvas, set(), [require_scene_record_id(item) for item in [items[0], items[2]]]
    )
    session = canvas.services.canvas_document_session_service
    history = canvas.services.history_service
    before = session.snapshot_state()
    order = list(_document(canvas, kind).order)
    for index in deleted_indices:
        items[index].setSelected(True)

    canvas.services.scene_delete_controller.delete_selected_items()
    deleted = session.snapshot_state()
    assert deleted[f"{kind}s"] == [
        state
        for index, state in enumerate(before[f"{kind}s"])
        if index not in deleted_indices
    ]
    for _ in range(3):
        history.undo()
        assert session.snapshot_state() == before
        assert _document(canvas, kind).order == order
        assert _ordered_views(canvas, kind) == items
        history.redo()
        assert session.snapshot_state() == deleted
    history.undo()
    session.apply_state(session.snapshot_state())
    assert session.snapshot_state() == before


def test_failed_reattach_restores_preexisting_membership_and_order(canvas, kind):
    items = _annotations(canvas, kind)
    item = items[0]
    canvas.scene().removeItem(item)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    document = _document(canvas, kind)
    order = document.order
    views = _views(canvas, kind)

    def attach_then_fail(ports, item):
        ports.add_item(item)
        raise RuntimeError("attach failed after registration")

    with (
        mock.patch(
            "chemvas.ui.scene.scene_item_lifecycle_service._add_item_with_attach_ports",
            side_effect=attach_then_fail,
        ),
        pytest.raises(RuntimeError, match="attach failed after registration"),
    ):
        canvas.services.scene_item_controller.attach_scene_item(item)

    assert item.scene() is None
    assert document.order is order
    assert _views(canvas, kind) is views
    assert _ordered_views(canvas, kind) == items
    assert session.snapshot_state() == before


def test_failed_history_delete_restores_document_and_projection_containers(
    canvas, kind
):
    items = _annotations(canvas, kind)
    document = _document(canvas, kind)
    order, records = document.order, document.records
    views = _views(canvas, kind)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()

    def remove_then_fail(canvas, item):
        canvas.services.scene_item_controller.remove_scene_item(item)
        document.records.pop(item.data(3))
        raise RuntimeError("delete failed after removing the record")

    with (
        mock.patch(
            "chemvas.ui.history.history_operations.remove_scene_item",
            side_effect=remove_then_fail,
        ),
        pytest.raises(RuntimeError, match="delete failed"),
    ):
        CanvasHistoryOperations(canvas).remove_scene_items(
            [items[1].data(3)], [scene_item_state_for(canvas, items[1])]
        )

    assert document.order is order
    assert document.records is records
    assert _views(canvas, kind) is views
    assert _ordered_views(canvas, kind) == items
    assert session.snapshot_state() == before
    assert all(item.scene() is canvas.scene() for item in items)


def test_reset_of_empty_scene_keeps_redo_records(canvas, kind):
    item = _annotations(canvas, kind)[-1]
    history = canvas.services.history_service
    before = canvas.services.canvas_document_session_service.snapshot_state()
    for _ in range(3):
        history.undo()
    assert _document(canvas, kind).order == []

    canvas.services.canvas_scene_reset_service.clear_scene()
    for _ in range(3):
        history.redo()

    assert _ordered_views(canvas, kind)[-1] is item
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


def test_reset_of_annotations_without_projections_clears_document_and_history(
    canvas, kind
):
    items = _annotations(canvas, kind)
    for item in items:
        canvas.scene().removeItem(item)
    canvas.services.canvas_scene_reset_service.clear_scene()

    assert _document(canvas, kind).order == []
    assert _document(canvas, kind).records == {}
    assert _views(canvas, kind) == {}
    assert canvas.services.history_service.state.history == []


def test_shape_tool_resize_delete_undo_and_reopen_in_a_shown_window(drawing, tmp_path):
    _window, canvas = drawing
    mode = canvas.services.tool_mode_controller
    mode.set_shape_type("rect")
    mode.set_tool("shape")

    def drag(start, end):
        QTest.mousePress(
            canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(start)
        )
        QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(end), 30)
        QTest.mouseRelease(
            canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(end)
        )

    drag(QPointF(-100, -50), QPointF(-20, 30))
    drag(QPointF(30, -50), QPointF(110, 30))
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    assert len(before["shapes"]) == 2
    mode.set_tool("select")
    point = canvas.mapFromScene(QPointF(-60, -10))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    handle = next(
        h
        for h in canvas.runtime_state.handle_state.active_handles
        if h.data(1) == "shape_se"
    )
    start = handle.sceneBoundingRect().center()
    drag(start, start + QPointF(15, 10))
    resized = session.snapshot_state()
    assert resized["shapes"][0]["right"] > before["shapes"][0]["right"]
    assert resized["shapes"][0]["bottom"] > before["shapes"][0]["bottom"]
    history = canvas.services.history_service
    history.undo()
    assert session.snapshot_state() == before
    history.redo()
    assert session.snapshot_state() == resized
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert len(session.snapshot_state()["shapes"]) == 1
    history.undo()
    assert session.snapshot_state() == resized
    destination = tmp_path / "native-shapes.chemvas"
    session.save_to_file(str(destination))
    session.apply_state(read_document(destination).state)
    assert session.snapshot_state() == resized


@pytest.mark.parametrize("kind", ["arrow", "ts_bracket"])
def test_annotation_tools_delete_undo_and_reopen_in_a_shown_window(
    drawing, tmp_path, kind
):
    _window, canvas = drawing
    mode = canvas.services.tool_mode_controller
    mode.set_tool(kind)
    for offset in (-100, 30):
        start = canvas.mapFromScene(QPointF(offset, -50))
        end = canvas.mapFromScene(QPointF(offset + 80, 30))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), end, 30)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    assert len(before[f"{kind}s"]) == 2
    mode.set_tool("select")
    point = QPointF(-60, -10) if kind == "arrow" else QPointF(-100, -10)
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(point)
    )
    assert _ordered_views(canvas, kind)[0].isSelected()
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert len(session.snapshot_state()[f"{kind}s"]) == 1
    history = canvas.services.history_service
    history.undo()
    assert session.snapshot_state() == before
    history.redo()
    assert len(session.snapshot_state()[f"{kind}s"]) == 1
    history.undo()
    destination = tmp_path / f"native-{kind}s.chemvas"
    session.save_to_file(str(destination))
    session.apply_state(read_document(destination).state)
    assert session.snapshot_state() == before


def _assert_history_has_no_live_graphics(value, seen=None):
    from dataclasses import fields, is_dataclass

    from PyQt6.QtCore import QObject
    from PyQt6.QtWidgets import QGraphicsItem

    seen = set() if seen is None else seen
    if id(value) in seen:
        return
    seen.add(id(value))
    assert not isinstance(value, (QObject, QGraphicsItem))
    assert not callable(value), "history must not close over an item or canvas"
    if is_dataclass(value):
        for field in fields(value):
            _assert_history_has_no_live_graphics(getattr(value, field.name), seen)
    elif isinstance(value, dict):
        for key, entry in value.items():
            _assert_history_has_no_live_graphics(key, seen)
            _assert_history_has_no_live_graphics(entry, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for entry in value:
            _assert_history_has_no_live_graphics(entry, seen)


@pytest.mark.parametrize("fail_restore", [False, True])
def test_deleted_group_annotations_recreate_same_ids_after_collection(
    canvas, kind, fail_restore
):
    from chemvas.ui.annotations.projections import find_projection
    from chemvas.ui.history import history_operations
    from chemvas.ui.history.history_commands import DeleteSceneItemsCommand

    items = _annotations(canvas, kind)
    history = canvas.services.history_service
    history.clear()
    ids = [item.data(3) for item in items]
    for item in items:
        item.setZValue(7.125)
    del item
    register_group_for(canvas, set(), ids)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    refs = [weakref.ref(item) for item in items]
    command = DeleteSceneItemsCommand.capture(
        history.operations,
        [scene_item_state_for(canvas, item) for item in items],
        items,
    )
    command.redo(history.operations)
    history.push(command)
    del items
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert _document(canvas, kind).records == {}
    _assert_history_has_no_live_graphics(history.state.history)
    _assert_history_has_no_live_graphics(canvas.runtime_state.group_state.groups)
    deleted = session.snapshot_state()
    if fail_restore:
        restore = history_operations.restore_scene_item

        def fail_after_attach(view, item):
            restore(view, item)
            raise RuntimeError("recreated projection attach failed")

        with (
            mock.patch.object(
                history_operations, "restore_scene_item", side_effect=fail_after_attach
            ),
            pytest.raises(RuntimeError, match="recreated projection attach failed"),
        ):
            history.undo()
        assert session.snapshot_state() == deleted
        assert history.state.history == [command]
    history.undo()
    assert session.snapshot_state() == before
    assert _document(canvas, kind).order == ids
    assert all(find_projection(canvas, key).zValue() == 7.125 for key in ids)
    history.redo()
    assert session.snapshot_state() == deleted
    history.undo()
    assert session.snapshot_state() == before


def test_grouped_projection_loss_keeps_the_missing_members_reference(canvas, kind):
    items = _annotations(canvas, kind)
    register_group_for(canvas, set(), [item.data(3) for item in items])
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    for item in items:
        sip.delete(item)
    assert session.snapshot_state() == before
    assert len(before["groups"][0]["items"]) == 3


def test_geometry_history_recreates_destroyed_active_projection(canvas, kind):
    from chemvas.ui.annotations.projections import find_projection
    from chemvas.ui.history.history_commands import UpdateSceneItemCommand
    from chemvas.ui.scene.scene_clipboard_transaction_logic import (
        translated_scene_item_state,
    )

    item = _annotations(canvas, kind)[1]
    history = canvas.services.history_service
    history.clear()
    key = item.data(3)
    before = scene_item_state_for(canvas, item)
    after = translated_scene_item_state(before, dx=7.125, dy=-9.375, atom_id_map={})
    command = UpdateSceneItemCommand(key, before, after)
    command.redo(history.operations)
    history.push(command)
    _assert_history_has_no_live_graphics(history.state.history)
    sip.delete(item)
    history.undo()
    restored = find_projection(canvas, key)
    assert restored is not item
    assert restored.scene() is canvas.scene()
    assert scene_item_state_for(canvas, restored) == before
    history.redo()
    assert scene_item_state_for(canvas, restored) == after


def test_grouped_paste_redo_restores_selection_after_projection_collection(canvas):
    from chemvas.ui.annotations.projections import group_projections
    from chemvas.ui.selection.select_all_access import select_all_scene_items_for

    _annotations(canvas, "note")
    _annotations(canvas, "arrow")
    ids = [
        *canvas.runtime_state.note_state.order,
        *canvas.runtime_state.arrow_state.order,
    ]
    register_group_for(canvas, set(), ids)
    select_all_scene_items_for(canvas)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    clipboard = canvas.services.scene_clipboard_controller
    payload = clipboard.selection_payload_for_clipboard()
    clipboard.paste_selection_from_clipboard(payload_provider=lambda: (payload, "copy"))
    pasted = session.snapshot_state()
    group = list(canvas.runtime_state.group_state.groups.values())[-1]
    refs = [weakref.ref(item) for item in group_projections(canvas, group.item_ids)]
    selected = [item.isSelected() for item in group_projections(canvas, group.item_ids)]
    history = canvas.services.history_service
    _assert_history_has_no_live_graphics(history.state.history)
    history.undo()
    gc.collect()
    assert all(ref() is None for ref in refs)
    history.redo()
    assert session.snapshot_state() == pasted
    assert [
        item.isSelected() for item in group_projections(canvas, group.item_ids)
    ] == selected
    canvas.services.scene_delete_controller.delete_selected_items()
    assert session.snapshot_state() == before
    history.undo()
    assert session.snapshot_state() == pasted


def test_text_style_history_recreates_destroyed_note(canvas):
    from PyQt6.QtGui import QColor

    from chemvas.ui.annotations.projections import find_projection

    note = _annotations(canvas, "note")[1]
    key = note.data(3)
    history = canvas.services.history_service
    history.clear()
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    canvas.services.style_controller.set_text_color(QColor("#b52a72"))
    after = session.snapshot_state()
    _assert_history_has_no_live_graphics(history.state.history)
    sip.delete(note)
    history.undo()
    assert find_projection(canvas, key).scene() is canvas.scene()
    assert session.snapshot_state() == before
    history.redo()
    assert session.snapshot_state() == after
