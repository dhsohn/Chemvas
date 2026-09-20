"""Every attached TS bracket item draws its record, after every operation.

The record is what the bracket is; the item is redrawn from it in scene
coordinates and stays at the origin. After each operation that can change a
bracket, each attached item has a record and shows exactly that record.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas_scene_items_state import ts_bracket_items_for
from chemvas.ui.canvas_service_ports import insert_controller_for_access
from chemvas.ui.canvas_ts_bracket_state import ts_bracket_state_for
from chemvas.ui.scene_decoration_build_access import ts_bracket_path_for
from chemvas.ui.scene_item_state_serialization import scene_item_state_for
from chemvas.ui.transactions import document_transaction
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


def assert_store_matches_items(canvas) -> None:
    items = ts_bracket_items_for(canvas)
    ids = [ts_bracket_id_for_item(item) for item in items]
    assert None not in ids
    assert len(set(ids)) == len(ids)
    for item in items:
        record = ts_bracket_record_for(canvas, item)
        assert record is not None
        rect = ts_bracket_rect_of(record)
        assert item.pos() == QPointF(0.0, 0.0)
        assert item.path() == ts_bracket_path_for(canvas, rect, record.bracket_kind)
        assert item.data(1) is None
        assert item.data(2) is None


def _add_ts_bracket(canvas, rect=None, *, bracket_kind="square_pair"):
    service = canvas.services.scene_decoration.scene_decoration_service
    item = service.add_ts_bracket(
        rect or QRectF(10.0, 20.0, 120.0, 90.0), bracket_kind=bracket_kind
    )
    assert item is not None
    return item


def _select_only(canvas, *items) -> None:
    canvas.scene().clearSelection()
    for item in items:
        item.setSelected(True)


def _two_carbons() -> MoleculeModel:
    model = MoleculeModel()
    model.add_atom("C", 0.0, 0.0)
    model.add_atom("C", 40.0, 0.0)
    return model


def test_a_new_ts_bracket_gets_an_id_and_a_record(canvas) -> None:
    item = _add_ts_bracket(canvas, bracket_kind="double_dagger")

    record = ts_bracket_record_for(canvas, item)

    assert record is not None
    assert (record.left, record.top, record.right, record.bottom) == (
        10.0,
        20.0,
        130.0,
        110.0,
    )
    assert record.bracket_kind == "double_dagger"
    assert_store_matches_items(canvas)


def test_every_edit_and_its_undo_and_redo_keep_the_record_current(canvas) -> None:
    services = canvas.services
    history = services.history_service
    transform = services.scene_operations.scene_transform_controller
    item = _add_ts_bracket(canvas)
    other = _add_ts_bracket(
        canvas, QRectF(300.0, 50.0, 80.0, 100.0), bracket_kind="dagger"
    )
    first_id = ts_bracket_id_for_item(item)

    def check(step: str) -> None:
        try:
            assert_store_matches_items(canvas)
        except AssertionError as error:
            raise AssertionError(f"store and items disagree after: {step}") from error

    check("create")

    services.interaction.move_controller.move_item(item, 15.0, -5.0)
    check("move")
    assert ts_bracket_record_for(canvas, item).left == 25.0

    _select_only(canvas, item, other)
    transform.flip_selected_items(True)
    check("flip")
    transform.rotate_selected_items(90.0)
    check("rotate")
    transform.translate_selected_items(3.0, 4.0)
    check("translate selection")
    transform.align_selected_items("left")
    check("align")

    steps = 0
    while history.state.history:
        history.undo()
        steps += 1
        check(f"undo {steps}")
    assert steps >= 5
    assert ts_bracket_items_for(canvas) == []

    for index in range(steps):
        history.redo()
        check(f"redo {index + 1}")

    # Undoing the creation and redoing it re-attaches the same item, so the id
    # and the record are the ones it had.
    assert item in ts_bracket_items_for(canvas)
    assert ts_bracket_id_for_item(item) == first_id


def test_copy_and_paste_gives_the_copy_its_own_record(canvas) -> None:
    services = canvas.services
    item = _add_ts_bracket(canvas, bracket_kind="braces_pair")
    _select_only(canvas, item)
    clipboard = services.scene_operations.scene_clipboard_controller

    assert clipboard.copy_selection_to_clipboard()
    assert clipboard.paste_selection_from_clipboard()

    items = ts_bracket_items_for(canvas)
    assert len(items) == 2
    assert_store_matches_items(canvas)
    pasted = next(bracket for bracket in items if bracket is not item)
    assert ts_bracket_record_for(canvas, pasted).bracket_kind == "braces_pair"
    assert ts_bracket_id_for_item(pasted) != ts_bracket_id_for_item(item)


def test_deleting_a_ts_bracket_and_undoing_it_keeps_its_record(canvas) -> None:
    services = canvas.services
    item = _add_ts_bracket(canvas)
    before = ts_bracket_record_for(canvas, item)
    _select_only(canvas, item)

    services.scene_operations.scene_delete_controller.delete_selected_items()

    assert ts_bracket_items_for(canvas) == []

    services.history_service.undo()

    assert ts_bracket_items_for(canvas) == [item]
    assert ts_bracket_record_for(canvas, item) == before
    assert_store_matches_items(canvas)


def test_opening_a_document_fills_the_store_and_a_blank_one_empties_it(canvas) -> None:
    session = canvas.services.document.canvas_document_session_service
    _add_ts_bracket(canvas)
    _add_ts_bracket(canvas, QRectF(220.0, 10.0, 60.0, 80.0), bracket_kind="dagger")
    saved = session.snapshot_state()
    assert len(saved["ts_brackets"]) == 2

    session.apply_state({**saved, "ts_brackets": []})

    assert ts_bracket_items_for(canvas) == []
    assert ts_bracket_state_for(canvas).records == {}

    session.apply_state(saved)

    assert len(ts_bracket_items_for(canvas)) == 2
    assert len(ts_bracket_state_for(canvas).records) == 2
    assert_store_matches_items(canvas)
    assert session.snapshot_state()["ts_brackets"] == saved["ts_brackets"]


def test_a_failed_open_puts_the_store_back(canvas) -> None:
    session = canvas.services.document.canvas_document_session_service
    item = _add_ts_bracket(canvas)
    before_records = dict(ts_bracket_state_for(canvas).records)
    other = session.snapshot_state()
    other["ts_brackets"] = [
        {**other["ts_brackets"][0], "left": 300.0, "right": 420.0},
        {**other["ts_brackets"][0], "top": 300.0, "bottom": 390.0},
    ]

    # The new document's brackets are already attached, and in the store, when
    # a later restore step fails.
    with (
        mock.patch(
            "chemvas.ui.canvas_document_session_service.restore_document_groups",
            side_effect=RuntimeError("late failure"),
        ),
        pytest.raises(RuntimeError, match="late failure"),
    ):
        session.apply_state(other)

    assert ts_bracket_items_for(canvas) == [item]
    assert ts_bracket_state_for(canvas).records == before_records
    assert_store_matches_items(canvas)


def test_a_rolled_back_transaction_puts_the_store_back(canvas) -> None:
    services = canvas.services
    item = _add_ts_bracket(canvas)
    before_records = dict(ts_bracket_state_for(canvas).records)

    with (
        pytest.raises(RuntimeError, match="gesture failed"),
        document_transaction(canvas, history_service=services.history_service),
    ):
        services.interaction.move_controller.move_item(item, 50.0, 60.0)
        _add_ts_bracket(canvas, QRectF(300.0, 300.0, 60.0, 80.0))
        assert ts_bracket_state_for(canvas).records != before_records
        raise RuntimeError("gesture failed")

    assert ts_bracket_items_for(canvas) == [item]
    assert ts_bracket_state_for(canvas).records == before_records
    assert_store_matches_items(canvas)


def test_a_ts_bracket_deleted_before_a_structure_load_keeps_its_record(canvas) -> None:
    services = canvas.services
    item = _add_ts_bracket(canvas, bracket_kind="parentheses_pair")
    before = ts_bracket_record_for(canvas, item)
    _select_only(canvas, item)
    services.scene_operations.scene_delete_controller.delete_selected_items()

    # A structure load clears the scene but keeps history, and history still
    # holds the deleted item; its record has to outlive the load.
    insert_controller_for_access(canvas).smiles_service.load_model(_two_carbons(), "CC")
    assert ts_bracket_record_for(canvas, item) == before
    services.history_service.undo()
    services.history_service.undo()

    assert ts_bracket_items_for(canvas) == [item]
    assert ts_bracket_record_for(canvas, item) == before
    assert_store_matches_items(canvas)


def test_a_ts_bracket_drawn_after_a_structure_load_never_takes_an_old_id(
    canvas,
) -> None:
    services = canvas.services
    old = _add_ts_bracket(canvas, bracket_kind="square_pair")
    _select_only(canvas, old)
    services.scene_operations.scene_delete_controller.delete_selected_items()
    insert_controller_for_access(canvas).smiles_service.load_model(_two_carbons(), "CC")

    new = _add_ts_bracket(
        canvas, QRectF(-300.0, -300.0, 60.0, 80.0), bracket_kind="dagger"
    )

    assert ts_bracket_id_for_item(new) != ts_bracket_id_for_item(old)
    assert ts_bracket_record_for(canvas, old).bracket_kind == "square_pair"
    assert ts_bracket_record_for(canvas, new).bracket_kind == "dagger"


def test_a_new_document_never_hands_out_an_old_id_again(canvas) -> None:
    session = canvas.services.document.canvas_document_session_service
    old = _add_ts_bracket(canvas)
    blank = {**session.snapshot_state(), "ts_brackets": []}

    session.apply_state(blank)
    new = _add_ts_bracket(canvas)

    # The old item is unreachable once history is gone, but an id that is never
    # reused cannot alias even if something still held on to it.
    assert ts_bracket_id_for_item(new) != ts_bracket_id_for_item(old)
    assert ts_bracket_record_for(canvas, old) is None


def test_a_rolled_back_ts_bracket_does_not_give_its_id_to_the_next_one(
    canvas,
) -> None:
    services = canvas.services
    rolled_back = []

    with (
        pytest.raises(RuntimeError, match="gesture failed"),
        document_transaction(canvas, history_service=services.history_service),
    ):
        rolled_back.append(_add_ts_bracket(canvas, QRectF(300.0, 300.0, 60.0, 80.0)))
        raise RuntimeError("gesture failed")
    other = _add_ts_bracket(canvas, QRectF(300.0, 20.0, 60.0, 80.0))

    # The rolled-back item still carries the id it was given.
    assert ts_bracket_id_for_item(other) != ts_bracket_id_for_item(rolled_back[0])
    assert_store_matches_items(canvas)


def test_a_failed_add_leaves_no_record(canvas) -> None:
    services = canvas.services
    _add_ts_bracket(canvas)
    before_records = dict(ts_bracket_state_for(canvas).records)

    # The item is attached, and has its record, when the history push fails.
    with (
        mock.patch.object(
            type(services.history_service),
            "push",
            side_effect=RuntimeError("push failed"),
        ),
        pytest.raises(RuntimeError, match="push failed"),
    ):
        _add_ts_bracket(canvas, QRectF(300.0, 300.0, 60.0, 80.0))

    assert len(ts_bracket_items_for(canvas)) == 1
    assert ts_bracket_state_for(canvas).records == before_records


def test_restating_another_kind_of_item_leaves_the_bracket_store_alone(canvas) -> None:
    services = canvas.services
    shape = services.scene_decoration.scene_decoration_service.add_shape(
        QRectF(10.0, 20.0, 60.0, 40.0)
    )
    arrow = services.scene_decoration.scene_decoration_service.add_arrow(
        QPointF(0.0, 0.0), QPointF(80.0, 0.0), "arrow"
    )
    controller = services.scene_view.scene_item_controller

    for item in (shape, arrow):
        controller.apply_scene_item_state(item, scene_item_state_for(canvas, item))
        services.interaction.move_controller.move_item(item, 5.0, 5.0)

    assert ts_bracket_state_for(canvas).records == {}
    assert ts_bracket_id_for_item(arrow) is None
