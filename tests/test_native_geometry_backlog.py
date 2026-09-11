"""Actual-canvas regression witnesses for input and perspective safety."""

import math
from copy import deepcopy
from itertools import combinations
from unittest import mock

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas_history_state import history_state_for
from chemvas.ui.canvas_scene_items_state import arrow_items_for, ring_items_for
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_access import attach_scene_item
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_style_access import restore_selection_from_ids_for
from chemvas.ui.structure_geometry_access import regular_ring_points_for_bond_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


@pytest.mark.parametrize("kind", ["line", "arrow"])
@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0])
@pytest.mark.parametrize("pixels", [1, 3])
def test_pointer_wobble_is_a_click_in_view_pixels(canvas, app, kind, zoom, pixels):
    canvas.services.input.tool_mode_controller.set_tool(kind)
    canvas.resetTransform()
    canvas.scale(zoom, zoom)
    start = canvas.mapFromScene(QPointF(0, 0))
    end = start + QPoint(pixels, 0)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    items = arrow_items_for(canvas)
    if kind == "arrow":
        assert items == []
    else:
        assert len(items) == 1
        data = items[0].data(2)
        assert data["end"] - data["start"] == QPointF(40.0, 0.0)


@pytest.mark.parametrize("noise", [-1e-12, 0.0, 1e-12])
@pytest.mark.parametrize("down", [False, True])
def test_vertical_arrow_label_side_is_stable_under_roundoff(canvas, noise, down):
    start, end = QPointF(0, 20), QPointF(noise, 100)
    if not down:
        start, end = end, start
    item = add_arrow_for(canvas, start, end, "line")
    canvas.services.scene_decoration.arrow_build_service.apply_arrow_labels(
        item, {"above": "A", "below": "B"}
    )
    children = {child.data(1): child for child in item.childItems()}
    assert children["above"].sceneBoundingRect().center().x() < 0
    assert children["below"].sceneBoundingRect().center().x() > 0


@pytest.mark.parametrize("style", ["wedge", "hash"])
@pytest.mark.parametrize("partial", [False, True])
def test_stereo_perspective_refusal_preserves_document_and_history(
    canvas, style, partial
):
    ids = [
        add_atom_for(canvas, element, x, y)
        for element, x, y in [
            ("C", 0, 0),
            ("C", 20, 0),
            ("O", -10, -17),
            ("C", -10, 17),
            ("C", -30, 17),
        ]
    ]
    for a, b in [(0, 1), (0, 2), (0, 3), (3, 4)]:
        add_bond_for(canvas, ids[a], ids[b])
    canvas.model.bonds[0].style = style
    canvas.services.structure.structure_build_service.render_model()
    select_all_scene_items_for(canvas)
    if partial:
        restore_selection_from_ids_for(canvas, {ids[4]}, set())
    errors = []
    callback_state_for(canvas).error = errors.append
    before = deepcopy(snapshot_canvas_state_for(canvas))
    mark_document_clean_for(canvas, before)
    state = history_state_for(canvas)
    stacks = (list(state.history), list(state.redo_stack))
    controller = canvas.services.interaction.selection_rotation_controller
    assert not controller.begin_selection_3d_rotation(
        axis_hint=2 if partial else None, press_pos=QPointF()
    )
    assert errors and "stereo" in errors[0].lower()
    assert "2D" in errors[0]
    assert snapshot_canvas_state_for(canvas) == before
    assert (state.history, state.redo_stack) == stacks
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))


def _plain_ring(canvas, size=6, angle=0.0, offset=0.0):
    ids = [
        add_atom_for(
            canvas,
            "C",
            offset + 20 * math.cos(angle + index * 2 * math.pi / size),
            20 * math.sin(angle + index * 2 * math.pi / size),
        )
        for index in range(size)
    ]
    bonds = [
        add_bond_for(canvas, ids[index], ids[(index + 1) % size])
        for index in range(size)
    ]
    canvas.services.structure.structure_build_service.render_model()
    return ids, bonds


@pytest.mark.parametrize("bond_index", range(6))
@pytest.mark.parametrize("angle", [0.0, math.radians(15)])
@pytest.mark.parametrize("size", [5, 6])
def test_graph_ring_fusion_chooses_unoccupied_side_without_fill(
    canvas, bond_index, angle, size
):
    _, bonds = _plain_ring(canvas, angle=angle)
    assert ring_items_for(canvas) == []
    bond = canvas.model.bonds[bonds[bond_index]]
    a, b = canvas.model.atoms[bond.a], canvas.model.atoms[bond.b]
    midpoint = QPointF((a.x + b.x) / 2, (a.y + b.y) / 2)
    result = regular_ring_points_for_bond_for(canvas, size, bonds[bond_index], midpoint)
    assert result is not None
    points, _ = result
    center = QPointF(
        sum(point.x() for point in points) / size,
        sum(point.y() for point in points) / size,
    )

    def side(point):
        return (b.x - a.x) * (point.y() - a.y) - (b.y - a.y) * (point.x() - a.x)

    assert side(center) * side(QPointF()) < 0


@pytest.mark.parametrize("size", [4, 5, 6])
@pytest.mark.parametrize("selection_kind", ["atoms", "bonds", "both"])
def test_ring_fill_materializes_selected_graph_cycle_in_one_undo(
    canvas, size, selection_kind
):
    ids, bonds = _plain_ring(canvas, size=size)
    restore_selection_from_ids_for(
        canvas,
        set(ids) if selection_kind in {"atoms", "both"} else set(),
        set(bonds) if selection_kind in {"bonds", "both"} else set(),
    )
    before = snapshot_canvas_state_for(canvas)
    history = canvas.runtime_state.history_service
    count = len(history_state_for(canvas).history)
    color = canvas.services.scene_operations.canvas_color_mutation_service
    color.apply_ring_fill_color_to_items(
        canvas.scene().selectedItems(), QColor("#ffcc00")
    )
    assert len(ring_items_for(canvas)) == 1
    assert set(ring_items_for(canvas)[0].data(2)) == set(ids)
    after = snapshot_canvas_state_for(canvas)
    assert after["model"] == before["model"]
    assert len(history_state_for(canvas).history) == count + 1
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    # Repeated application reuses the native ring instead of duplicating it.
    count = len(history_state_for(canvas).history)
    color.apply_ring_fill_color_to_items(
        canvas.scene().selectedItems(), QColor("#ffcc00")
    )
    assert len(ring_items_for(canvas)) == 1
    assert len(history_state_for(canvas).history) == count
    restore_canvas_state_for(canvas, after)
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("stage", ["second_attach", "history_push", "history_false"])
@pytest.mark.parametrize("selection_kind", ["both", "bonds"])
def test_ring_fill_failure_restores_exact_document_selection_and_stacks(
    canvas, stage, selection_kind
):
    first_atoms, first_bonds = _plain_ring(canvas)
    second_atoms, second_bonds = _plain_ring(canvas, offset=100)
    restore_selection_from_ids_for(
        canvas,
        set(first_atoms + second_atoms) if selection_kind == "both" else set(),
        set(first_bonds + second_bonds),
    )
    before = deepcopy(snapshot_canvas_state_for(canvas))
    history = canvas.runtime_state.history_service
    state = history_state_for(canvas)
    stacks = (list(state.history), list(state.redo_stack))
    selected = set(canvas.scene().selectedItems())
    scene_items = set(canvas.scene().items())
    service = canvas.services.scene_operations.canvas_color_mutation_service
    calls = 0

    def fail_second(view, item):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("ring attach failed")
        attach_scene_item(view, item)

    if stage == "second_attach":
        patcher = mock.patch(
            "chemvas.ui.canvas_color_mutation_service.attach_scene_item",
            side_effect=fail_second,
        )
    elif stage == "history_false":
        patcher = mock.patch.object(history, "push", return_value=False)
    else:
        patcher = mock.patch.object(
            history, "push", side_effect=RuntimeError("ring history failed")
        )
    with patcher, pytest.raises(RuntimeError, match="ring|history"):
        service.apply_ring_fill_color_to_items(
            canvas.scene().selectedItems(), QColor("#ffcc00")
        )
    assert snapshot_canvas_state_for(canvas) == before
    assert (state.history, state.redo_stack) == stacks
    assert set(canvas.scene().selectedItems()) == selected
    assert set(canvas.scene().items()) == scene_items


@pytest.mark.parametrize("size", [4, 6])
@pytest.mark.parametrize("selection_kind", ["atoms", "alternating_bonds", "mixed"])
def test_ring_fill_partial_selection_has_actionable_message_and_no_mutation(
    canvas, size, selection_kind
):
    ids, bonds = _plain_ring(canvas, size=size)
    if size == 6:
        for bond_id in bonds[::2]:
            canvas.model.bonds[bond_id].order = 2
        canvas.services.structure.structure_build_service.render_model()
    if selection_kind == "atoms":
        selected_atoms, selected_bonds = set(ids[:-1]), set()
    elif selection_kind == "alternating_bonds":
        # These endpoints cover every atom, but the ring bonds are incomplete.
        selected_atoms, selected_bonds = set(), set(bonds[::2])
    else:
        # Explicit atoms plus a selected bond's endpoints also cover the ring;
        # neither the atom selection nor the bond selection is complete.
        selected_atoms, selected_bonds = set(ids[2:]), {bonds[0]}
    restore_selection_from_ids_for(canvas, selected_atoms, selected_bonds)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    state = history_state_for(canvas)
    stacks = (list(state.history), list(state.redo_stack))
    selected = set(canvas.scene().selectedItems())
    scene_items = set(canvas.scene().items())
    errors = []
    callback_state_for(canvas).error = errors.append
    canvas.services.scene_operations.canvas_color_mutation_service.apply_ring_fill_color_to_items(
        canvas.scene().selectedItems(), QColor("#ffcc00")
    )
    assert errors and "complete ring" in errors[0]
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    assert (state.history, state.redo_stack) == stacks
    assert set(canvas.scene().selectedItems()) == selected
    assert set(canvas.scene().items()) == scene_items


def test_stereo_guard_does_not_block_disconnected_nonstereo_molecule(canvas):
    a = add_atom_for(canvas, "C", 0, 0)
    b = add_atom_for(canvas, "C", 20, 0)
    bond = add_bond_for(canvas, a, b)
    canvas.model.bonds[bond].style = "wedge"
    ids, _ = _plain_ring(canvas, offset=100)
    restore_selection_from_ids_for(canvas, set(ids), set())
    controller = canvas.services.interaction.selection_rotation_controller
    before = snapshot_canvas_state_for(canvas)
    assert controller.begin_selection_3d_rotation()
    controller.update_selection_3d_rotation(80, 0)
    controller.end_selection_3d_rotation()
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert after["model"]["atoms"][a] == before["model"]["atoms"][a]
    assert after["model"]["bonds"][bond] == before["model"]["bonds"][bond]
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.runtime_state.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("kind", ["line", "arrow"])
def test_drag_above_threshold_still_draws_and_roundtrips(canvas, app, kind):
    canvas.services.input.tool_mode_controller.set_tool(kind)
    start = canvas.mapFromScene(QPointF())
    end = start + QPoint(QApplication.startDragDistance() + 20, 0)
    before = snapshot_canvas_state_for(canvas)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert len(arrow_items_for(canvas)) == 1
    after = snapshot_canvas_state_for(canvas)
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.runtime_state.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("axis", [False, True])
@pytest.mark.parametrize("finish", ["no_motion", "undo", "push_failure"])
def test_first_perspective_keeps_absent_depth_absent_on_rollback(canvas, axis, finish):
    ids = [
        add_atom_for(canvas, "C", index * 20, (index % 2) * 10) for index in range(4)
    ]
    bonds = [add_bond_for(canvas, ids[index], ids[index + 1]) for index in range(3)]
    canvas.services.structure.structure_build_service.render_model()
    restore_selection_from_ids_for(canvas, {ids[3]} if axis else set(ids), set())
    before = snapshot_canvas_state_for(canvas)
    assert "perspective" not in before
    mark_document_clean_for(canvas, before)
    history = canvas.runtime_state.history_service
    state = history_state_for(canvas)
    stacks = (list(state.history), list(state.redo_stack))
    controller = canvas.services.interaction.selection_rotation_controller
    assert controller.begin_selection_3d_rotation(
        axis_hint=bonds[1] if axis else None, press_pos=QPointF(40, 0)
    )
    if finish != "no_motion":
        controller.update_selection_3d_rotation(80, 0)
    if finish == "push_failure":
        with (
            mock.patch.object(
                history, "push", side_effect=RuntimeError("publish failed")
            ),
            pytest.raises(RuntimeError, match="publish"),
        ):
            controller.end_selection_3d_rotation()
        assert (state.history, state.redo_stack) == stacks
    else:
        controller.end_selection_3d_rotation()
        if finish == "undo":
            after = snapshot_canvas_state_for(canvas)
            history.undo()
        else:
            assert (state.history, state.redo_stack) == stacks
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    if finish == "undo":
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("size", [5, 6])
def test_graph_ring_fusion_commit_preserves_anchor_and_roundtrips(canvas, size):
    ids, bonds = _plain_ring(canvas)
    before = snapshot_canvas_state_for(canvas)
    canvas.services.structure.structure_build_service.fuse_regular_ring_to_bond(
        bonds[0], size
    )
    after = snapshot_canvas_state_for(canvas)
    assert len(canvas.model.atoms) == 6 + size - 2
    for atom_id in ids:
        assert after["model"]["atoms"][atom_id] == before["model"]["atoms"][atom_id]
    assert after["model"]["bonds"][:6] == before["model"]["bonds"]
    assert all(
        math.hypot(a.x - b.x, a.y - b.y) > 1e-7
        for a, b in combinations(canvas.model.atoms.values(), 2)
    )
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.runtime_state.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_shared_interior_ring_edge_refuses_fusion_on_two_occupied_sides(canvas):
    points = [(-20, -10), (0, -10), (0, 10), (-20, 10), (20, 10), (20, -10)]
    ids = [add_atom_for(canvas, "C", *point) for point in points]
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (1, 5), (5, 4), (4, 2)]:
        add_bond_for(canvas, ids[a], ids[b])
    canvas.services.structure.structure_build_service.render_model()
    before = snapshot_canvas_state_for(canvas)
    assert regular_ring_points_for_bond_for(canvas, 4, 1, QPointF()) is None
    canvas.services.structure.structure_build_service.fuse_regular_ring_to_bond(1, 4)
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("smiles", ["C1CCCCC1", "C1CCNC1", "c1ccccc1"])
def test_actual_smiles_imported_ring_can_be_filled_without_graph_change(canvas, smiles):
    pytest.importorskip("rdkit")
    model = RDKitAdapter().smiles_to_2d(smiles, scale=20)
    assert model is not None
    canvas.model = model
    canvas.services.structure.structure_build_service.render_model()
    select_all_scene_items_for(canvas)
    assert ring_items_for(canvas) == []
    before = snapshot_canvas_state_for(canvas)
    canvas.services.scene_operations.canvas_color_mutation_service.apply_ring_fill_color_to_items(
        canvas.scene().selectedItems(), QColor("#ffff00")
    )
    assert len(ring_items_for(canvas)) == 1
    assert snapshot_canvas_state_for(canvas)["model"] == before["model"]
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
