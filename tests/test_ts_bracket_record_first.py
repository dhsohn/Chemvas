"""A TS bracket is saved, undone and edited as its record, not as its paint."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas_scene_items_state import ts_bracket_items_for
from chemvas.ui.canvas_service_ports import insert_controller_for_access
from chemvas.ui.canvas_ts_bracket_state import ts_bracket_state_for
from chemvas.ui.export_readability_service import _item_sizes
from chemvas.ui.scene_decoration_build_access import ts_bracket_path_for
from chemvas.ui.ts_bracket_record_access import (
    ts_bracket_id_for_item,
    ts_bracket_record_for,
    ts_bracket_rect_of,
)
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


def _document_with(canvas, ts_brackets) -> dict:
    return {**_session(canvas).snapshot_state(), "ts_brackets": ts_brackets}


# What another tool might write: integer and reversed coordinates, and an edge
# that QRectF's width arithmetic does not hand back exactly.
EXTERNAL_TS_BRACKET = {
    "kind": "ts_bracket",
    "left": 347.43,
    "top": 130,
    "right": 10.2,
    "bottom": 255,
    "bracket_kind": "double_dagger",
}
CANONICAL_TS_BRACKET = {
    "kind": "ts_bracket",
    "left": 10.2,
    "top": 130.0,
    "right": 347.43,
    "bottom": 255.0,
    "bracket_kind": "double_dagger",
}
# An ordered rectangle whose right edge QRectF hands back as 208.82999999999998.
DRIFTING_TS_BRACKET = {
    "kind": "ts_bracket",
    "left": 78.95,
    "top": 163.17,
    "right": 208.83,
    "bottom": 211.29,
    "bracket_kind": "square_pair",
}


def test_a_file_from_elsewhere_is_made_canonical_once_and_then_stays(canvas) -> None:
    session = _session(canvas)

    session.apply_state(_document_with(canvas, [EXTERNAL_TS_BRACKET]))
    first_save = session.snapshot_state()

    assert first_save["ts_brackets"] == [CANONICAL_TS_BRACKET]
    # Exactly the stated value: Qt's read-back wrote 10.199999999999989.
    assert repr(first_save["ts_brackets"][0]["left"]) == "10.2"

    session.apply_state(first_save)

    assert session.snapshot_state()["ts_brackets"] == first_save["ts_brackets"]


def test_a_file_chemvas_saved_comes_back_unchanged_even_with_qt_read_back_values(
    canvas,
) -> None:
    # A value an earlier release wrote after pushing the rectangle through Qt.
    saved_by_an_earlier_release = {**CANONICAL_TS_BRACKET, "left": 10.199999999999989}
    session = _session(canvas)

    session.apply_state(_document_with(canvas, [saved_by_an_earlier_release]))

    assert session.snapshot_state()["ts_brackets"] == [saved_by_an_earlier_release]


def test_saving_does_not_ask_the_item_what_the_bracket_is(canvas) -> None:
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_TS_BRACKET]))
    item = ts_bracket_items_for(canvas)[0]

    # Change the item behind the record's back.
    item.setPath(QPainterPath())
    item.moveBy(40.0, 40.0)
    item.setData(1, {"rect": QRectF(0.0, 0.0, 1.0, 1.0), "bracket_kind": "dagger"})

    assert session.snapshot_state()["ts_brackets"] == [CANONICAL_TS_BRACKET]

    # The next edit draws the item from its record again, at the origin.
    canvas.services.interaction.move_controller.move_item(item, 1.0, 1.0)
    record = ts_bracket_record_for(canvas, item)
    assert item.pos() == QPointF(0.0, 0.0)
    assert item.path() == ts_bracket_path_for(
        canvas, ts_bracket_rect_of(record), record.bracket_kind
    )


def test_an_attached_ts_bracket_without_a_record_is_an_error_not_a_guess(
    canvas,
) -> None:
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_TS_BRACKET]))
    item = ts_bracket_items_for(canvas)[0]
    del ts_bracket_state_for(canvas).records[ts_bracket_id_for_item(item)]

    with pytest.raises(RuntimeError, match="no record"):
        session.snapshot_state()


def test_moves_are_arithmetic_on_the_record_and_undo_returns_the_exact_values(
    canvas,
) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_TS_BRACKET]))
    item = ts_bracket_items_for(canvas)[0]
    original = ts_bracket_record_for(canvas, item)
    transform = services.scene_operations.scene_transform_controller

    item.setSelected(True)
    for _ in range(10):
        assert transform.translate_selected_items(0.1, 0.3)

    moved = ts_bracket_record_for(canvas, item)
    expected_left = original.left
    for _ in range(10):
        expected_left += 0.1
    assert moved.left == expected_left
    # The item is drawn in scene coordinates and never leaves the origin.
    assert item.pos() == QPointF(0.0, 0.0)
    assert item.path() == ts_bracket_path_for(
        canvas, ts_bracket_rect_of(moved), moved.bracket_kind
    )

    history = services.history_service
    while history.state.history:
        history.undo()

    assert ts_bracket_record_for(canvas, item) == original
    assert session.snapshot_state()["ts_brackets"] == [CANONICAL_TS_BRACKET]


def test_a_ts_bracket_drawn_with_the_tool_gets_its_record_from_how_it_was_drawn(
    canvas,
) -> None:
    service = canvas.services.scene_decoration.scene_decoration_service

    item = service.add_ts_bracket(
        QRectF(10.2, 20.0, 337.23, 90.0), bracket_kind="braces_pair"
    )

    rect = QRectF(10.2, 20.0, 337.23, 90.0)
    assert _session(canvas).snapshot_state()["ts_brackets"] == [
        {
            "kind": "ts_bracket",
            "left": rect.left(),
            "top": rect.top(),
            "right": rect.right(),
            "bottom": rect.bottom(),
            "bracket_kind": "braces_pair",
        }
    ]
    assert ts_bracket_record_for(canvas, item) is not None


def test_a_pasted_ts_bracket_keeps_the_stated_values(canvas) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_TS_BRACKET]))
    original = ts_bracket_items_for(canvas)[0]
    original.setSelected(True)
    clipboard = services.scene_operations.scene_clipboard_controller

    assert clipboard.copy_selection_to_clipboard()
    assert clipboard.paste_selection_from_clipboard()

    pasted = next(item for item in ts_bracket_items_for(canvas) if item is not original)
    record = ts_bracket_record_for(canvas, pasted)
    source = ts_bracket_record_for(canvas, original)
    # The copy is offset by the same amount on both edges, exactly.
    assert record.bracket_kind == "double_dagger"
    assert record.left - source.left == record.right - source.right
    assert ts_bracket_id_for_item(pasted) != ts_bracket_id_for_item(original)


def test_undoing_a_structure_load_recreates_ts_brackets_with_the_stated_values(
    canvas,
) -> None:
    services = canvas.services
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [DRIFTING_TS_BRACKET]))
    model = MoleculeModel()
    model.add_atom("C", 0.0, 0.0)
    model.add_atom("C", 40.0, 0.0)

    insert_controller_for_access(canvas).smiles_service.load_model(model, "CC")
    assert session.snapshot_state()["ts_brackets"] == []
    services.history_service.undo()

    # Undo re-creates the bracket from its state; the record is that state,
    # not what the new item reads back.
    assert session.snapshot_state()["ts_brackets"] == [DRIFTING_TS_BRACKET]


def test_an_edit_that_would_make_a_ts_bracket_unsaveable_is_refused(canvas) -> None:
    session = _session(canvas)
    session.apply_state(_document_with(canvas, [CANONICAL_TS_BRACKET]))
    item = ts_bracket_items_for(canvas)[0]
    move = canvas.services.interaction.move_controller.move_item
    move(item, 8e15, 0.0)
    record_before = ts_bracket_record_for(canvas, item)
    path_before = QPainterPath(item.path())

    # One more step would take the edges past the largest number a document
    # may hold (2**53 - 1).
    with pytest.raises(ValueError, match="Invalid TS bracket"):
        move(item, 8e15, 0.0)

    # The refused move touched neither the record nor the paint.
    assert ts_bracket_record_for(canvas, item) == record_before
    assert item.path() == path_before
    assert item.pos() == QPointF(0.0, 0.0)
    assert session.snapshot_state()["ts_brackets"][0]["left"] == record_before.left


def test_moving_a_dagger_keeps_the_size_of_its_glyph(canvas) -> None:
    # A box 25 tall asks for a 15.5 px glyph, right on a rounding edge, and
    # moving it by a mouse step leaves its height at 24.999999999999986.
    session = _session(canvas)
    dagger = {**CANONICAL_TS_BRACKET, "left": 100.0, "top": 110.0}
    dagger.update(right=130.0, bottom=135.0)
    session.apply_state(_document_with(canvas, [dagger]))
    item = ts_bracket_items_for(canvas)[0]
    size_before = item.export_glyph_run()[1].pixelSize()
    move = canvas.services.interaction.move_controller.move_item

    sizes = set()
    for step in range(1, 41):
        move(item, 0.0, step / 1.8)
        sizes.add(item.export_glyph_run()[1].pixelSize())

    assert sizes == {size_before}


def test_a_ts_bracket_item_that_arrives_without_a_record_is_adopted(canvas) -> None:
    from chemvas.ui.scene_decoration_build_access import build_ts_bracket_item_for

    item = build_ts_bracket_item_for(
        canvas, QRectF(10.0, 20.0, 120.0, 90.0), "braces_pair"
    )
    assert ts_bracket_record_for(canvas, item) is None

    canvas.services.scene_view.scene_item_controller.attach_scene_item(item)

    # Until the last step makes this an error, what the item says becomes
    # its record.
    assert _session(canvas).snapshot_state()["ts_brackets"] == [
        {
            "kind": "ts_bracket",
            "left": 10.0,
            "top": 20.0,
            "right": 130.0,
            "bottom": 110.0,
            "bracket_kind": "braces_pair",
        }
    ]


def test_a_dagger_can_come_back_onto_an_item_that_was_drawn_as_a_bracket(
    canvas,
) -> None:
    services = canvas.services
    item = services.scene_decoration.scene_decoration_service.add_ts_bracket(
        QRectF(10.0, 20.0, 120.0, 90.0), bracket_kind="square_pair"
    )
    dagger = {**_session(canvas).snapshot_state()["ts_brackets"][0]}
    dagger["bracket_kind"] = "double_dagger"

    services.scene_view.scene_item_controller.apply_scene_item_state(item, dagger)

    assert ts_bracket_record_for(canvas, item).bracket_kind == "double_dagger"
    # The export check measures the glyph through its construction font, which
    # an item first drawn as a stroked bracket has to be able to carry.
    assert list(_item_sizes(item))
