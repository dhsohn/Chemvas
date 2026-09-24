"""A shape is saved, undone and edited as its record, not as its paint."""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QGraphicsPathItem

from chemvas.domain.document import MoleculeModel
from chemvas.ui.annotations.records import (
    clear_shape_records_for,
    shape_id_for_item,
    shape_record_for,
)
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_scene_items_state import shape_items_for
from chemvas.ui.canvas_service_ports import insert_controller_for_access
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def _session(canvas):
    return canvas.services.document.canvas_document_session_service


def _document_with(canvas, shapes) -> dict:
    return {**_session(canvas).snapshot_state(), "shapes": shapes}


# What another tool might write: integer and reversed coordinates, a short
# uppercase colour, an opacity QColor cannot hold exactly and an edge QRectF
# does not read back exactly.
EXTERNAL_SHAPE = {
    "kind": "shape",
    "left": 390,
    "top": 130,
    "right": 347.43,
    "bottom": 155,
    "shape_kind": "ellipse",
    "stroke_style": "dashed",
    "fill": "#ABC",
    "fill_alpha": 0.25,
}
CANONICAL_SHAPE = {
    "kind": "shape",
    "left": 347.43,
    "top": 130.0,
    "right": 390.0,
    "bottom": 155.0,
    "shape_kind": "ellipse",
    "stroke_style": "dashed",
    "fill": "#aabbcc",
    "fill_alpha": 0.25,
}


def test_a_file_from_elsewhere_is_made_canonical_once_and_then_stays(canvas) -> None:
    session = _session(canvas)

    session.apply_state(_document_with(canvas, [EXTERNAL_SHAPE]))
    first_save = session.snapshot_state()

    assert first_save["shapes"] == [CANONICAL_SHAPE]
    # Exactly the stated values: not 0.2500038..., not 347.42999999999995.
    assert repr(first_save["shapes"][0]["fill_alpha"]) == "0.25"
    assert repr(first_save["shapes"][0]["left"]) == "347.43"

    session.apply_state(first_save)

    assert session.snapshot_state()["shapes"] == first_save["shapes"]


def test_a_file_chemvas_saved_comes_back_unchanged_even_with_qt_read_back_values(
    canvas,
) -> None:
    # Values an earlier release wrote after pushing them through Qt.
    saved_by_an_earlier_release = {
        **CANONICAL_SHAPE,
        "fill_alpha": 0.2500038146972656,
        "right": 347.42999999999995,
        "left": 10.200000000000003,
    }
    session = _session(canvas)

    session.apply_state(_document_with(canvas, [saved_by_an_earlier_release]))

    assert session.snapshot_state()["shapes"] == [saved_by_an_earlier_release]


def test_saving_does_not_ask_the_item_what_the_shape_is(canvas) -> None:
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    item = shape_items_for(canvas)[0]

    # Paint the item differently behind the record's back.
    item.setBrush(QBrush(QColor("#ff0000")))
    item.setData(1, {"rect": QRectF(0.0, 0.0, 1.0, 1.0), "shape_kind": "rect"})

    assert session.snapshot_state()["shapes"] == [CANONICAL_SHAPE]


def test_an_attached_shape_without_a_record_is_an_error_not_a_guess(canvas) -> None:
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    item = shape_items_for(canvas)[0]
    del canvas.runtime_state.shape_state.records[shape_id_for_item(item)]

    with pytest.raises(RuntimeError, match="no record"):
        session.snapshot_state()


def test_edits_are_arithmetic_on_the_record_and_undo_returns_the_exact_values(
    canvas,
) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    item = shape_items_for(canvas)[0]
    original = shape_record_for(canvas, item)
    transform = services.scene_operations.scene_transform_controller

    item.setSelected(True)
    for _ in range(10):
        assert transform.translate_selected_items(0.1, 0.3)

    moved = shape_record_for(canvas, item)
    expected_left = original.left
    for _ in range(10):
        expected_left += 0.1
    assert moved.left == expected_left
    assert moved.fill_alpha == 0.25

    services.handles.handle_mutation_service.update_shape_resize(
        item, "shape_se", QPointF(500.5, 400.25)
    )
    assert shape_record_for(canvas, item).right == 500.5
    assert shape_record_for(canvas, item).bottom == 400.25

    history = services.history_service
    while history.state.history:
        history.undo()

    assert shape_record_for(canvas, item) == original
    assert session.snapshot_state()["shapes"] == [CANONICAL_SHAPE]


def test_a_shape_drawn_with_the_tool_gets_its_record_from_how_it_was_drawn(
    canvas,
) -> None:
    service = canvas.services.scene_decoration.scene_decoration_service

    item = service.add_shape(
        QRectF(10.0, 20.0, 60.0, 40.0), shape_kind="rect", stroke_style="dotted"
    )

    assert _session(canvas).snapshot_state()["shapes"] == [
        {
            "kind": "shape",
            "left": 10.0,
            "top": 20.0,
            "right": 70.0,
            "bottom": 60.0,
            "shape_kind": "rect",
            "stroke_style": "dotted",
        }
    ]
    assert shape_record_for(canvas, item) is not None


def test_a_pasted_shape_keeps_the_stated_values(canvas) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    original = shape_items_for(canvas)[0]
    original.setSelected(True)
    clipboard = services.scene_operations.scene_clipboard_controller

    assert clipboard.copy_selection_to_clipboard()
    assert clipboard.paste_selection_from_clipboard()

    pasted = next(item for item in shape_items_for(canvas) if item is not original)
    record = shape_record_for(canvas, pasted)
    # The copy is offset, and its opacity is the stated one, not Qt's read-back.
    assert repr(record.fill_alpha) == "0.25"
    assert record.right - record.left == pytest.approx(
        CANONICAL_SHAPE["right"] - CANONICAL_SHAPE["left"], abs=1e-9
    )
    assert (record.shape_kind, record.stroke_style, record.fill) == (
        "ellipse",
        "dashed",
        "#aabbcc",
    )


def test_undoing_deletion_restores_shapes_with_the_stated_values(
    canvas,
) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    before = session.snapshot_state()["shapes"]
    shape_items_for(canvas)[0].setSelected(True)
    services.scene_operations.scene_delete_controller.delete_selected_items()
    assert session.snapshot_state()["shapes"] == []
    services.history_service.undo()

    assert session.snapshot_state()["shapes"] == before


def test_a_shape_item_without_a_record_cannot_join_the_document(canvas) -> None:
    item = QGraphicsPathItem()
    item.setData(0, "shape")

    with pytest.raises(RuntimeError, match="without a record"):
        canvas.services.scene_view.scene_item_controller.attach_scene_item(item)

    assert shape_items_for(canvas) == []
    assert item.scene() is None


def _insert_two_carbons(canvas) -> None:
    model = MoleculeModel()
    model.add_atom("C", 0.0, 0.0)
    model.add_atom("C", 40.0, 0.0)
    controller = insert_controller_for_access(canvas)
    with mock.patch.object(canvas.rdkit, "smiles_to_2d", return_value=model):
        controller.begin_smiles_insert("CC")
    controller.commit_smiles_insert(QPointF(50.0, 60.0))


def test_a_shape_deleted_before_a_structure_insertion_still_comes_back_on_undo(
    canvas,
) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    item = shape_items_for(canvas)[0]
    item.setSelected(True)
    services.scene_operations.scene_delete_controller.delete_selected_items()

    # A subsequent edit must retain the deleted item and its record for Undo.
    _insert_two_carbons(canvas)
    services.history_service.undo()
    services.history_service.undo()

    assert [shape.data(3) for shape in shape_items_for(canvas)] == [item.data(3)]
    assert session.snapshot_state()["shapes"] == [CANONICAL_SHAPE]


def test_a_shape_drawn_after_a_structure_insertion_never_takes_an_old_shape_id(
    canvas,
) -> None:
    services = canvas.services
    service = services.scene_decoration.scene_decoration_service
    old = service.add_shape(QRectF(10.0, 20.0, 60.0, 40.0), shape_kind="rect")
    old_record = shape_record_for(canvas, old)
    old.setSelected(True)
    services.scene_operations.scene_delete_controller.delete_selected_items()
    _insert_two_carbons(canvas)

    new = service.add_shape(
        QRectF(-300.0, -300.0, 20.0, 20.0), shape_kind="ellipse", stroke_style="dashed"
    )
    assert shape_id_for_item(new) != shape_id_for_item(old)

    for _ in range(3):
        services.history_service.undo()

    # The old rectangle is back, saved as itself and not as the newer ellipse.
    assert shape_items_for(canvas) == [old]
    assert shape_record_for(canvas, old) == old_record
    assert _session(canvas).snapshot_state()["shapes"][0]["shape_kind"] == "rect"


def test_a_failed_add_leaves_no_record(canvas) -> None:
    service = canvas.services.scene_decoration.scene_decoration_service
    service.add_shape(QRectF(10.0, 20.0, 60.0, 40.0))
    before_records = dict(canvas.runtime_state.shape_state.records)

    with (
        mock.patch(
            "chemvas.ui.scene_item_lifecycle_service.append_scene_item_for",
            side_effect=RuntimeError("attach failed"),
        ),
        pytest.raises(RuntimeError, match="attach failed"),
    ):
        service.add_shape(QRectF(200.0, 200.0, 30.0, 30.0))

    assert canvas.runtime_state.shape_state.records == before_records
    assert len(shape_items_for(canvas)) == 1


def test_clearing_the_records_never_hands_out_an_old_id_again(canvas) -> None:
    service = canvas.services.scene_decoration.scene_decoration_service
    first = service.add_shape(QRectF(10.0, 20.0, 60.0, 40.0))

    clear_shape_records_for(canvas)
    second = service.add_shape(QRectF(200.0, 20.0, 60.0, 40.0))

    assert shape_id_for_item(second) > shape_id_for_item(first)
