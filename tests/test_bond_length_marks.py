from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsTextItem

from chemvas.core.document_io import read_document
from chemvas.core.history import (
    command_is_fully_covered_by_history_transaction,
    command_requires_exact_history_transaction,
)
from chemvas.features.export import export_scene
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_scene_items_state import mark_items_for
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    save_canvas_to_file_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.main_window_context_bar_widgets import bond_length_input
from chemvas.ui.mark_item_access import build_mark_item_for, mark_center_for
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_mark_for,
    add_mark_for_atom_for,
)
from chemvas.ui.scene_item_access import apply_scene_item_state
from chemvas.ui.scene_item_state import mark_state_dict_for, scene_item_state_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def drawing():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    first = add_atom_for(canvas, "N", 10.1, 20.3)
    second = add_atom_for(canvas, "C", 30.1, 20.3)
    add_bond_graphics_for(canvas, add_bond_for(canvas, first, second))
    yield canvas, first
    canvas.services.document.canvas_scene_reset_service.clear_scene()
    canvas.close()
    app.processEvents()


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "radical", "circled_plus", "circled_minus"]
)
def test_bound_mark_rescales_in_place_and_undo_redo_restores_exact_state(drawing, kind):
    canvas, atom_id = drawing
    atom = atom_for_id(canvas, atom_id)
    offset = QPointF(4.125, -6.375)
    item = add_mark_for_atom_for(
        canvas,
        atom_id,
        QPointF(atom.x, atom.y) + offset,
        kind=kind,
    )
    state = mark_state_dict_for(canvas, item)
    state.update(dx=offset.x(), dy=offset.y())
    apply_scene_item_state(canvas, item, state)
    # A real manual correction retains the exact graphics position; it need
    # not be reproduced bit-for-bit by atom + offset arithmetic.
    move_item_for(canvas, item, 0.1 - item.pos().x(), 0.3 - item.pos().y())
    item.setSelected(True)
    before = snapshot_canvas_state_for(canvas)
    before_position = QPointF(item.pos())
    original_data = dict(item.data(1))
    history = canvas.services.history_service

    canvas.services.scene_view.geometry_controller.set_bond_length(60.0)

    assert item.isSelected()
    assert item.data(1)["dx"] == original_data["dx"] * 3
    assert item.data(1)["dy"] == original_data["dy"] * 3
    center = mark_center_for(canvas, item)
    assert center.x() == pytest.approx(atom.x + original_data["dx"] * 3)
    assert center.y() == pytest.approx(atom.y + original_data["dy"] * 3)
    fresh = build_mark_item_for(canvas, kind)
    if isinstance(item, QGraphicsTextItem):
        assert item.font() == fresh.font()
    elif kind == "radical":
        assert item.rect() == fresh.rect()
    else:
        assert item.path() == fresh.path()
        assert item.pen().widthF() == fresh.pen().widthF()
    after = snapshot_canvas_state_for(canvas)
    after_position = QPointF(item.pos())
    after_mark = mark_state_dict_for(canvas, item)
    for _ in range(3):
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        assert item.pos() == before_position
        assert item.isSelected()
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
        assert item.pos() == after_position
        assert mark_state_dict_for(canvas, item) == after_mark


def test_manual_mark_correction_history_is_exact_near_atom_origin(drawing):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    history = canvas.services.history_service
    for delta in (0.01, 0.123456789, -0.1, 0.0007, -8.789):
        move_item_for(canvas, item, delta, -delta)
        before = snapshot_canvas_state_for(canvas)
        before_position = QPointF(item.pos())
        canvas.services.scene_view.geometry_controller.set_bond_length(33.7)
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        assert item.pos() == before_position


def test_bound_mark_with_legal_absolute_anchor_undo_preserves_missing_offsets(
    drawing, tmp_path
):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    state = mark_state_dict_for(canvas, item)
    state.update(dx=None, dy=None, x=42.123, y=-9.456)
    apply_scene_item_state(canvas, item, state)
    assert (
        save_canvas_to_file_for(canvas, str(tmp_path / "absolute-anchor.chemvas")) == []
    )
    before = snapshot_canvas_state_for(canvas)
    position = QPointF(item.pos())
    canvas.services.scene_view.geometry_controller.set_bond_length(60)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert item.pos() == position


@pytest.mark.parametrize(
    "phase", ["font-raise", "font-noop", "push-raise", "push-false"]
)
def test_partial_bond_length_failure_restores_mark_document_and_both_stacks(
    drawing, phase
):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    item.setSelected(True)
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    position, font = QPointF(item.pos()), item.font()
    stacks = history.capture_stack_snapshot()
    if phase == "font-noop":
        patch = mock.patch.object(item, "setFont", return_value=None)
    elif phase == "font-raise":
        patch = mock.patch.object(
            item, "setFont", side_effect=RuntimeError("injected font")
        )
    elif phase == "push-false":
        patch = mock.patch.object(history, "push", return_value=False)
    else:
        original_push = history.push

        def append_then_raise(command):
            original_push(command)
            raise RuntimeError("injected push")

        patch = mock.patch.object(history, "push", side_effect=append_then_raise)
    with patch, pytest.raises(RuntimeError):
        canvas.services.scene_view.geometry_controller.set_bond_length(60)
    assert snapshot_canvas_state_for(canvas) == before
    assert item.pos() == position
    assert item.font() == font
    assert item.isSelected()
    history.verify_stack_snapshot(stacks)
    canvas.services.scene_view.geometry_controller.set_bond_length(60)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("phase", ["undo", "redo"])
def test_bond_length_history_failure_restores_exact_current_frame_and_is_retryable(
    drawing, phase
):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    history = canvas.services.history_service
    canvas.services.scene_view.geometry_controller.set_bond_length(60)
    if phase == "redo":
        history.undo()
    before = snapshot_canvas_state_for(canvas)
    position, font = QPointF(item.pos()), item.font()
    stacks = history.capture_stack_snapshot()
    with mock.patch(
        "chemvas.ui.history_commands._apply_scene_item_state",
        side_effect=RuntimeError("injected replay"),
    ):
        with pytest.raises(RuntimeError, match="injected replay"):
            getattr(history, phase)()
    assert snapshot_canvas_state_for(canvas) == before
    assert item.pos() == position
    assert item.font() == font
    history.verify_stack_snapshot(stacks)
    getattr(history, phase)()


def test_disabled_history_retains_existing_non_recording_policy_and_command_coverage(
    drawing,
):
    canvas, atom_id = drawing
    item = add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    history = canvas.services.history_service
    dx = item.data(1)["dx"]
    history.set_enabled(False)
    stacks = history.capture_stack_snapshot()
    try:
        canvas.services.scene_view.geometry_controller.set_bond_length(60)
        assert item.data(1)["dx"] == dx * 3
        history.verify_stack_snapshot(stacks)
    finally:
        history.set_enabled(True)
    with mock.patch.object(history, "push", wraps=history.push) as push:
        canvas.services.scene_view.geometry_controller.set_bond_length(20)
    command = push.call_args.args[0]
    assert command_is_fully_covered_by_history_transaction(command)
    assert command_requires_exact_history_transaction(command)


def test_rescale_keeps_bound_mark_color_and_free_annotations_unchanged(drawing):
    canvas, atom_id = drawing
    bound = add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    bound.setDefaultTextColor(QColor("#12ab34"))
    free = add_mark_for(canvas, QPointF(110, 70), kind="plus")
    arrow = add_arrow_for(canvas, QPointF(80, 60), QPointF(160, 60), "forward")
    free_state = scene_item_state_for(canvas, free)
    arrow_state = scene_item_state_for(canvas, arrow)
    free_font, free_pos = free.font(), free.pos()
    canvas.services.scene_view.geometry_controller.set_bond_length(60)
    for _ in range(3):
        assert bound.defaultTextColor() == QColor("#12ab34")
        assert scene_item_state_for(canvas, free) == free_state
        assert scene_item_state_for(canvas, arrow) == arrow_state
        assert free.font() == free_font
        assert free.pos() == free_pos
        canvas.services.history_service.undo()
        canvas.services.history_service.redo()


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "radical", "circled_plus", "circled_minus"]
)
def test_rescaled_figure_pixels_match_saved_reopened_document(drawing, tmp_path, kind):
    canvas, atom_id = drawing
    add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind=kind)
    canvas.services.scene_view.geometry_controller.set_bond_length(60)
    before = snapshot_canvas_state_for(canvas)
    path = tmp_path / "rescaled.chemvas"
    assert save_canvas_to_file_for(canvas, str(path)) == []
    export_scene(
        canvas.scene(), str(tmp_path / "live.png"), fmt="png", margin=8, dpi=96
    )
    restored = build_canvas_view()
    try:
        restore_canvas_state_for(restored, read_document(path).state)
        assert snapshot_canvas_state_for(restored) == before
        assert len(mark_items_for(restored)) == 1
        export_scene(
            restored.scene(),
            str(tmp_path / "reopened.png"),
            fmt="png",
            margin=8,
            dpi=96,
        )
        assert QImage(str(tmp_path / "live.png")) == QImage(
            str(tmp_path / "reopened.png")
        )
    finally:
        restored.services.document.canvas_scene_reset_service.clear_scene()
        restored.close()


@pytest.mark.parametrize("initial", [0.5, 300.0, 20.123456789])
def test_actual_length_field_noop_then_typing_is_one_exact_undoable_rescale(
    drawing, initial
):
    canvas, atom_id = drawing
    add_mark_for_atom_for(canvas, atom_id, QPointF(20, 10), kind="plus")
    geometry = canvas.services.scene_view.geometry_controller
    geometry.set_bond_length(initial)
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    widget, spin = bond_length_input(initial, geometry.set_bond_length)
    widget.show()
    try:
        assert QTest.qWaitForWindowExposed(widget)
        spin.setFocus()
        QTest.keyClick(spin, Qt.Key.Key_Return)
        assert snapshot_canvas_state_for(canvas) == before
        history.verify_stack_snapshot(stacks)
        spin.selectAll()
        QTest.keyClicks(spin, "500")
        QTest.keyClick(spin, Qt.Key.Key_Return)
        assert snapshot_canvas_state_for(canvas)["settings"]["bond_length_px"] == 500
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
    finally:
        widget.close()
