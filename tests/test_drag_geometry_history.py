"""Drag history restores saved coordinates exactly, not by subtracting a delta."""

from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest

from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_mark_for,
    add_mark_for_atom_for,
)
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from tests.test_native_geometry_backlog import _plain_ring
from tests.test_native_geometry_backlog import app as app
from tests.test_native_geometry_backlog import canvas as canvas


def prepare(canvas):
    ids = [
        add_atom_for(canvas, "C", x, y)
        for x, y in [(-180.0, -52.666666666666664), (-140.0, -28.33333333333333)]
    ]
    add_bond_for(canvas, *ids)
    canvas.services.structure.structure_build_service.render_model()
    arrow = add_arrow_for(
        canvas,
        QPointF(10.0, -52.666666666666664),
        QPointF(90.0, -28.33333333333333),
        "arrow",
    )
    bound = add_mark_for_atom_for(canvas, ids[0], QPointF(-180.1, -75.3), kind="plus")
    free = add_mark_for(canvas, QPointF(20.1, 80.3), kind="minus")
    canvas.services.interaction.note_controller.create_text_note(
        QPointF(60.1, 40.3), "A note"
    )
    # Existing Redo must survive a cancelled drag, but a committed drag replaces it.
    extra = add_arrow_for(canvas, QPointF(130, 100), QPointF(170, 100), "arrow")
    history = canvas.services.history_service
    history.undo()
    assert extra.scene() is None
    assert history.can_redo()
    return set(ids), arrow, bound, free


def drag(canvas, tool_name, scope):
    ids, arrow, bound, free = prepare(canvas)
    canvas.services.input.tool_mode_controller.set_tool(tool_name)
    tool = canvas.services.tool_controller.active
    atom_ids = ids if scope in {"atoms", "mixed"} else set()
    items = [arrow, free] if scope == "mixed" else [arrow] if scope == "arrow" else []
    assert tool._begin_selection_drag(atom_ids, items, QPointF())
    return tool


def frame(tool, delta):
    # Several real move-kernel frames give a different floating-point history
    # from subtracting one total. Coordinates and the dirty digest stay exact.
    tool._apply_drag_delta(QPointF(17.1, -11.3))
    tool._apply_drag_delta(QPointF(delta[0] - 17.1, delta[1] + 11.3))


@pytest.mark.parametrize("tool_name", ["select", "move"])
@pytest.mark.parametrize("scope", ["atoms", "arrow", "mixed"])
@pytest.mark.parametrize("delta", [(46.6, -43.9), (-13.7, 28.1), (0.1, 0.3)])
def test_drag_undo_restores_exact_document_and_clean_digest(
    canvas, tool_name, scope, delta
):
    tool = drag(canvas, tool_name, scope)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    history = canvas.services.history_service
    length = len(history.state.history)
    frame(tool, delta)
    tool._commit_selection_drag()
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert len(history.state.history) == length + 1
    assert not history.can_redo()
    for _ in range(3):
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("finish", ["cancel", "return", "push-fail"])
def test_uncommitted_drag_preserves_existing_redo(canvas, finish):
    tool = drag(canvas, "select", "mixed")
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    frame(tool, (46.6, -43.9))
    if finish == "cancel":
        tool._cancel_selection_drag()
    elif finish == "return":
        tool._apply_drag_delta(-tool._total_delta)
        tool._commit_selection_drag()
    else:
        with mock.patch.object(history, "push", return_value=False):
            with pytest.raises(RuntimeError, match="did not commit"):
                tool._commit_selection_drag()
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("tool_name", ["select", "move"])
def test_actual_pointer_drag_roundtrip_is_exact(canvas, app, tool_name):
    prepare(canvas)
    select_all_scene_items_for(canvas)
    canvas.services.input.tool_mode_controller.set_tool(tool_name)
    canvas.scale(1.3, 1.3)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    start = canvas.mapFromScene(QPointF(-180.0, -52.666666666666664))
    end = start + QPoint(61, -57)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_direct_move_arrow_uses_exact_geometry(canvas):
    ids, arrow, bound, free = prepare(canvas)
    canvas.services.input.tool_mode_controller.set_tool("move")
    canvas.scene().clearSelection()
    tool = canvas.services.tool_controller.active
    point = arrow.sceneBoundingRect().center()
    event = SimpleNamespace(
        button=lambda: Qt.MouseButton.LeftButton,
        position=lambda: QPointF(canvas.mapFromScene(point)),
        modifiers=lambda: Qt.KeyboardModifier.NoModifier,
    )
    with mock.patch.object(tool.context, "item_at_event", return_value=arrow):
        assert tool.on_mouse_press(event)
    assert tool._drag_item is arrow
    assert not tool._drag_selection
    before = snapshot_canvas_state_for(canvas)
    frame(tool, (46.6, -43.9))
    tool._commit_direct_item_drag()
    after = snapshot_canvas_state_for(canvas)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_drag_restores_exact_depth_inventory(canvas):
    tool = drag(canvas, "select", "atoms")
    coords = atom_coords_3d_for(canvas)
    # Both a stored coordinate and an absent entry must keep their identities.
    coords[0] = (-180.0, -52.666666666666664, 0.0)
    before = dict(coords)
    frame(tool, (46.6, -43.9))
    tool._commit_selection_drag()
    after = dict(coords)
    assert before != after
    canvas.services.history_service.undo()
    assert atom_coords_3d_for(canvas) == before
    canvas.services.history_service.redo()
    assert atom_coords_3d_for(canvas) == after


@pytest.mark.parametrize("kind", ["atom", "bond"])
def test_direct_move_updates_ring_fill_and_restores_exact_scene(canvas, app, kind):
    ids, bonds = _plain_ring(canvas, angle=0.17)
    select_all_scene_items_for(canvas)
    canvas.services.scene_operations.canvas_color_mutation_service.apply_ring_fill_color_to_items(
        canvas.scene().selectedItems(), QColor("#336699"), 0.3
    )
    assert len(ring_items_for(canvas)) == 1
    canvas.scene().clearSelection()
    canvas.services.input.tool_mode_controller.set_tool("move")
    atom = canvas.model.atoms[ids[0]]
    point = QPointF(atom.x, atom.y)
    if kind == "bond":
        other = canvas.model.atoms[ids[1]]
        point = (point + QPointF(other.x, other.y)) / 2
    start = canvas.mapFromScene(point)
    end = start + QPoint(47, 29)
    before = snapshot_canvas_state_for(canvas)
    before_ring = scene_item_state_for(canvas, ring_items_for(canvas)[0])
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    tool = canvas.services.tool_controller.active
    assert tool._drag_item.data(0) == kind
    assert not tool._drag_selection
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    after = snapshot_canvas_state_for(canvas)
    after_ring = scene_item_state_for(canvas, ring_items_for(canvas)[0])
    assert after != before
    assert after_ring["points"] != before_ring["points"]
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert scene_item_state_for(canvas, ring_items_for(canvas)[0]) == before_ring
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert scene_item_state_for(canvas, ring_items_for(canvas)[0]) == after_ring
