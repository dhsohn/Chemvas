"""A shape is saved, undone and edited as its record, not as its paint."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas_scene_items_state import shape_items_for
from chemvas.ui.canvas_service_ports import insert_controller_for_access
from chemvas.ui.canvas_shape_state import shape_state_for
from chemvas.ui.shape_record_access import shape_id_for_item, shape_record_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    view = build_canvas_view()
    yield view
    view.close()
    app.processEvents()


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
    del shape_state_for(canvas).records[shape_id_for_item(item)]

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


def test_undoing_a_structure_load_recreates_shapes_with_the_stated_values(
    canvas,
) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_SHAPE]))
    before = session.snapshot_state()["shapes"]
    model = MoleculeModel()
    model.add_atom("C", 0.0, 0.0)

    model.add_atom("C", 40.0, 0.0)
    insert_controller_for_access(canvas).smiles_service.load_model(model, "CC")
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
