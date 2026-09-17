"""The shape store never lags the graphics items that still own shapes.

Reads have not moved to the store yet, so this is the whole contract of the
step: after every operation that can change a shape, each attached shape item
has a record, and the record says what the item says.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import normalized_shape, shape_from_state
from chemvas.ui.canvas_scene_items_state import shape_items_for
from chemvas.ui.canvas_shape_state import shape_state_for
from chemvas.ui.scene_item_state_serialization import shape_state_dict
from chemvas.ui.shape_record_access import (
    shape_id_for_item,
    shape_record_for,
    sync_shape_record_for,
)
from chemvas.ui.transactions import document_transaction
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    view = build_canvas_view()
    yield view
    view.close()
    app.processEvents()


def assert_store_matches_items(canvas) -> None:
    items = shape_items_for(canvas)
    ids = [shape_id_for_item(item) for item in items]
    assert None not in ids
    assert len(set(ids)) == len(ids)
    for item in items:
        expected = normalized_shape(shape_from_state(shape_state_dict(item)))
        assert shape_record_for(canvas, item) == expected


def _add_shape(canvas, rect=None, **kwargs):
    service = canvas.services.scene_decoration.scene_decoration_service
    item = service.add_shape(rect or QRectF(10.0, 20.0, 60.0, 40.0), **kwargs)
    assert item is not None
    return item


def _select_only(canvas, *items) -> None:
    canvas.scene().clearSelection()
    for item in items:
        item.setSelected(True)


def test_a_new_shape_gets_an_id_and_a_record(canvas) -> None:
    item = _add_shape(canvas, shape_kind="ellipse", stroke_style="dashed")

    record = shape_record_for(canvas, item)

    assert record is not None
    assert (record.left, record.top, record.right, record.bottom) == (
        10.0,
        20.0,
        70.0,
        60.0,
    )
    assert (record.shape_kind, record.stroke_style, record.fill) == (
        "ellipse",
        "dashed",
        None,
    )
    assert_store_matches_items(canvas)


def test_every_edit_and_its_undo_and_redo_keep_the_record_current(canvas) -> None:
    services = canvas.services
    history = services.history_service
    item = _add_shape(canvas)
    other = _add_shape(canvas, QRectF(200.0, 50.0, 30.0, 30.0), shape_kind="rect")
    first_id = shape_id_for_item(item)

    def check(step: str) -> None:
        try:
            assert_store_matches_items(canvas)
        except AssertionError as error:
            raise AssertionError(f"store and items disagree after: {step}") from error

    check("create")

    services.interaction.move_controller.move_item(item, 15.0, -5.0)
    check("move")

    services.handles.handle_mutation_service.update_shape_resize(
        item, "shape_se", QPointF(140.0, 120.0)
    )
    check("resize")

    services.scene_operations.canvas_color_mutation_service.apply_color_to_item(
        item, QColor("#2196f3")
    )
    check("fill")
    assert shape_record_for(canvas, item).fill is not None

    _select_only(canvas, item)
    services.input.tool_mode_controller.set_shape_stroke("dotted")
    check("stroke change")
    assert shape_record_for(canvas, item).stroke_style == "dotted"

    _select_only(canvas, item, other)
    services.scene_operations.scene_transform_controller.flip_selected_items(True)
    check("flip")
    services.scene_operations.scene_transform_controller.rotate_selected_items(90.0)
    check("rotate")
    services.scene_operations.scene_transform_controller.translate_selected_items(
        3.0, 4.0
    )
    check("translate selection")
    services.scene_operations.scene_transform_controller.align_selected_items("left")
    check("align")
    services.scene_operations.canvas_color_mutation_service.apply_color_to_items(
        [item, other], QColor("#4caf50")
    )
    check("fill several")
    assert shape_record_for(canvas, other).fill is not None

    steps = 0
    while history.state.history:
        history.undo()
        steps += 1
        check(f"undo {steps}")
    assert steps >= 5
    assert shape_items_for(canvas) == []

    for index in range(steps):
        history.redo()
        check(f"redo {index + 1}")

    # Undoing the creation and redoing it re-attaches the same item, so the id
    # and the record are the ones it had.
    assert item in shape_items_for(canvas)
    assert shape_id_for_item(item) == first_id


def test_copy_and_paste_gives_the_copy_its_own_record(canvas) -> None:
    services = canvas.services
    item = _add_shape(canvas, shape_kind="rounded_rect")
    services.scene_operations.canvas_color_mutation_service.apply_color_to_item(
        item, QColor("#ff8800")
    )
    _select_only(canvas, item)
    clipboard = services.scene_operations.scene_clipboard_controller

    assert clipboard.copy_selection_to_clipboard()
    assert clipboard.paste_selection_from_clipboard()

    items = shape_items_for(canvas)
    assert len(items) == 2
    assert_store_matches_items(canvas)
    pasted = next(shape for shape in items if shape is not item)
    assert shape_record_for(canvas, pasted).shape_kind == "rounded_rect"
    assert shape_record_for(canvas, pasted).fill == shape_record_for(canvas, item).fill


def test_deleting_a_shape_and_undoing_it_keeps_its_record(canvas) -> None:
    services = canvas.services
    item = _add_shape(canvas)
    before = shape_record_for(canvas, item)
    _select_only(canvas, item)

    services.scene_operations.scene_delete_controller.delete_selected_items()

    assert shape_items_for(canvas) == []
    assert_store_matches_items(canvas)

    services.history_service.undo()

    assert shape_items_for(canvas) == [item]
    assert shape_record_for(canvas, item) == before
    assert_store_matches_items(canvas)


def test_opening_a_document_fills_the_store_and_a_blank_one_empties_it(canvas) -> None:
    session = canvas.services.document.canvas_document_session_service
    _add_shape(canvas)
    _add_shape(canvas, QRectF(120.0, 10.0, 25.0, 25.0), shape_kind="rect")
    saved = session.snapshot_state()
    assert len(saved["shapes"]) == 2

    blank = {**saved, "shapes": []}
    session.apply_state(blank)

    assert shape_items_for(canvas) == []
    assert shape_state_for(canvas).records == {}

    session.apply_state(saved)

    assert len(shape_items_for(canvas)) == 2
    assert len(shape_state_for(canvas).records) == 2
    assert_store_matches_items(canvas)
    assert session.snapshot_state()["shapes"] == saved["shapes"]


def test_a_failed_open_puts_the_store_back(canvas) -> None:
    session = canvas.services.document.canvas_document_session_service
    item = _add_shape(canvas)
    before_records = dict(shape_state_for(canvas).records)
    before_next_id = shape_state_for(canvas).next_shape_id
    other = session.snapshot_state()
    other["shapes"] = [
        {**other["shapes"][0], "left": 300.0, "right": 340.0},
        {**other["shapes"][0], "top": 300.0, "bottom": 330.0, "shape_kind": "rect"},
    ]

    # The new document's shapes are already attached, and in the store, when a
    # later restore step fails.
    with (
        mock.patch(
            "chemvas.ui.canvas_document_session_service.restore_document_groups",
            side_effect=RuntimeError("late failure"),
        ),
        pytest.raises(RuntimeError, match="late failure"),
    ):
        session.apply_state(other)

    assert shape_items_for(canvas) == [item]
    assert shape_state_for(canvas).records == before_records
    assert shape_state_for(canvas).next_shape_id == before_next_id
    assert_store_matches_items(canvas)


def test_a_rolled_back_transaction_puts_the_store_back(canvas) -> None:
    services = canvas.services
    item = _add_shape(canvas)
    before_records = dict(shape_state_for(canvas).records)
    before_next_id = shape_state_for(canvas).next_shape_id

    with (
        pytest.raises(RuntimeError, match="gesture failed"),
        document_transaction(canvas, history_service=services.history_service),
    ):
        services.interaction.move_controller.move_item(item, 50.0, 60.0)
        _add_shape(canvas, QRectF(300.0, 300.0, 20.0, 20.0))
        assert shape_state_for(canvas).records != before_records
        raise RuntimeError("gesture failed")

    assert shape_items_for(canvas) == [item]
    assert shape_state_for(canvas).records == before_records
    assert shape_state_for(canvas).next_shape_id == before_next_id
    assert_store_matches_items(canvas)


def test_a_failed_fill_of_several_shapes_leaves_no_fill_in_the_records(canvas) -> None:
    services = canvas.services
    first = _add_shape(canvas)
    second = _add_shape(canvas, QRectF(200.0, 20.0, 60.0, 40.0))

    with (
        mock.patch.object(
            type(services.history_service),
            "push",
            side_effect=RuntimeError("push failed"),
        ),
        pytest.raises(RuntimeError, match="push failed"),
    ):
        services.scene_operations.canvas_color_mutation_service.apply_color_to_items(
            [first, second], QColor("#2196f3")
        )

    assert shape_state_dict(first).get("fill") is None
    assert shape_record_for(canvas, first).fill is None
    assert shape_record_for(canvas, second).fill is None
    assert_store_matches_items(canvas)


def test_a_failed_fill_of_one_shape_leaves_no_fill_in_its_record(canvas) -> None:
    services = canvas.services
    item = _add_shape(canvas)

    with (
        mock.patch.object(
            type(services.history_service),
            "push",
            side_effect=RuntimeError("push failed"),
        ),
        pytest.raises(RuntimeError, match="push failed"),
    ):
        services.scene_operations.canvas_color_mutation_service.apply_color_to_item(
            item, QColor("#2196f3")
        )

    assert shape_record_for(canvas, item).fill is None
    assert_store_matches_items(canvas)


def test_an_item_that_arrives_with_an_id_never_meets_a_fresh_one(canvas) -> None:
    item = _add_shape(canvas)
    shape_state_for(canvas).next_shape_id = 1

    sync_shape_record_for(canvas, item)
    other = _add_shape(canvas, QRectF(200.0, 20.0, 60.0, 40.0))

    assert shape_id_for_item(other) != shape_id_for_item(item)
    assert_store_matches_items(canvas)
