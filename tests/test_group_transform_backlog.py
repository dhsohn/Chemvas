"""Whole-selection transforms preserve native group relationships."""

import math
from io import BytesIO
from itertools import pairwise
from unittest import mock

import pytest
from PIL import Image
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import image_state_from_bytes
from chemvas.features.selection import (
    HANDLE_SCREEN_PX,
    ROTATION_HANDLE_STEM_PX,
    ROTATION_HANDLE_TYPE,
)
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_group_state import group_state_for, register_group_for
from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.scene_decoration_access import (
    add_arrow_for,
    add_shape_for,
    add_ts_bracket_for,
)
from chemvas.ui.scene_group_operations import (
    expand_selection_to_groups_for,
    group_selection_for,
)
from chemvas.ui.scene_item_access import create_scene_item_from_state
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_outline_state import selection_outlines_for
from chemvas.ui.selection_style_access import restore_selection_from_ids_for
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
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _chain(canvas, *, offset=0):
    ids = [
        add_atom_for(canvas, "C", offset + index * 20, (index % 2) * 10)
        for index in range(4)
    ]
    for a, b in pairwise(ids):
        add_bond_for(canvas, a, b)
    canvas.services.structure.structure_build_service.render_model()
    return ids


def _decoration(canvas, kind):
    if kind == "note":
        return note_controller_for_access(canvas).create_text_note(
            QPointF(110, 70), "caption"
        )
    if kind == "shape":
        return add_shape_for(canvas, QRectF(110, 70, 30, 20), shape_kind="rect")
    if kind == "ts_bracket":
        return add_ts_bracket_for(canvas, QRectF(110, 70, 30, 20))
    stream = BytesIO()
    Image.new("RGB", (3, 2), (220, 30, 20)).save(stream, format="PNG")
    return create_scene_item_from_state(
        canvas, image_state_from_bytes(stream.getvalue(), x=110, y=70, width=30)
    )


def _turn(point, center):
    return QPointF(
        center.x() - (point.y() - center.y()), center.y() + point.x() - center.x()
    )


def _assert_point(actual, expected):
    assert (actual.x(), actual.y()) == pytest.approx((expected.x(), expected.y()))


@pytest.mark.parametrize("kind", ["note", "image", "shape", "ts_bracket"])
@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("drag", [False, True])
def test_rotation_orbits_every_upright_decoration_and_roundtrips(
    canvas, kind, grouped, drag
):
    ids = _chain(canvas)
    item = _decoration(canvas, kind)
    select_all_scene_items_for(canvas)
    if grouped:
        assert group_selection_for(canvas)
    controller = canvas.services.scene_operations.scene_transform_controller
    # The expected pivot includes the decoration, not just the molecule.
    center = controller._rotation_center(set(ids), [item])
    old_rect = item.sceneBoundingRect()
    before_item = scene_item_state_for(canvas, item)
    before = snapshot_canvas_state_for(canvas)
    if drag:
        session = controller.begin_rotation_drag(center + QPointF(100, 0))
        assert session is not None
        controller.update_rotation_drag(
            session, center + QPointF(100 * math.cos(math.pi / 6), 50)
        )
        controller.update_rotation_drag(session, center + QPointF(0, 100))
        command = controller.rotation_drag_command(session)
        assert command is not None
        canvas.runtime_state.history_service.push(command)
    else:
        controller.rotate_selected_items(90)
    _assert_point(item.sceneBoundingRect().center(), _turn(old_rect.center(), center))
    assert item.sceneBoundingRect().size() == old_rect.size()
    assert item.rotation() == 0
    after_item = scene_item_state_for(canvas, item)
    if kind == "image":
        assert after_item["data_base64"] == before_item["data_base64"]
    if kind == "note":
        assert after_item["text"] == before_item["text"]
    after = snapshot_canvas_state_for(canvas)
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.runtime_state.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("horizontal", [True, False])
def test_flip_uses_one_pivot_for_molecule_arrow_and_upright_item(canvas, horizontal):
    ids = _chain(canvas)
    image = _decoration(canvas, "image")
    arrow = add_arrow_for(canvas, QPointF(60, 30), QPointF(100, 30), "arrow")
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    controller = canvas.services.scene_operations.scene_transform_controller
    center = controller._rotation_center(set(ids), [arrow, image])
    old_image = image.sceneBoundingRect().center()
    old_arrow = scene_item_state_for(canvas, arrow)
    before = snapshot_canvas_state_for(canvas)
    controller.flip_selected_items(horizontal)
    expected = (
        QPointF(2 * center.x() - old_image.x(), old_image.y())
        if horizontal
        else QPointF(old_image.x(), 2 * center.y() - old_image.y())
    )
    _assert_point(image.sceneBoundingRect().center(), expected)
    after_arrow = scene_item_state_for(canvas, arrow)
    for key in ("start", "end"):
        x, y = old_arrow[key]
        assert after_arrow[key] == pytest.approx(
            (2 * center.x() - x, y) if horizontal else (x, 2 * center.y() - y)
        )
    for atom_id in ids:
        old = before["model"]["atoms"][atom_id]
        current = canvas.model.atoms[atom_id]
        assert current.x == pytest.approx(
            2 * center.x() - old["x"] if horizontal else old["x"]
        )
        assert current.y == pytest.approx(
            old["y"] if horizontal else 2 * center.y() - old["y"]
        )
    after = snapshot_canvas_state_for(canvas)
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.runtime_state.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_grouping_partial_molecule_records_and_moves_whole_component(canvas):
    ids = _chain(canvas)
    level = add_arrow_for(canvas, QPointF(100, 40), QPointF(140, 40), "line")
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    level.setSelected(True)
    before_group = snapshot_canvas_state_for(canvas)
    assert group_selection_for(canvas)
    group = next(iter(group_state_for(canvas).groups.values()))
    assert group.atom_ids == set(ids)
    grouped = snapshot_canvas_state_for(canvas)
    before_positions = {
        aid: (canvas.model.atoms[aid].x, canvas.model.atoms[aid].y) for aid in ids
    }
    canvas.services.scene_operations.scene_transform_controller.translate_selected_items(
        0, 4
    )
    for atom_id, (x, y) in before_positions.items():
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            x,
            y + 4,
        )
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == grouped
    canvas.runtime_state.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before_group
    restore_canvas_state_for(canvas, grouped)
    restore_selection_from_ids_for(canvas, set(), set())
    restored_level = next(iter(group_state_for(canvas).groups.values())).items[0]
    restored_level.setSelected(True)
    expand_selection_to_groups_for(canvas)
    canvas.services.scene_operations.scene_transform_controller.translate_selected_items(
        0, 4
    )
    for atom_id, (x, y) in before_positions.items():
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            x,
            y + 4,
        )


def test_direct_partial_atom_move_remains_a_reshape(canvas):
    ids = _chain(canvas)
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    before = snapshot_canvas_state_for(canvas)
    canvas.services.scene_operations.scene_transform_controller.translate_selected_items(
        0, 4
    )
    assert canvas.model.atoms[ids[0]].y == 4
    for atom_id in ids[1:]:
        assert canvas.model.atoms[atom_id].y == before["model"]["atoms"][atom_id]["y"]


def test_regroup_expands_absorbed_legacy_groups_to_component_closure(canvas):
    first = _chain(canvas)
    second = _chain(canvas, offset=200)
    unrelated = add_atom_for(canvas, "N", 500, 0)
    line = add_arrow_for(canvas, QPointF(150, 80), QPointF(190, 80), "line")
    other = add_arrow_for(canvas, QPointF(350, 80), QPointF(390, 80), "arrow")
    register_group_for(canvas, {first[0], second[0]}, [])
    register_group_for(canvas, {second[-1]}, [line])
    untouched_id = register_group_for(canvas, {unrelated}, [other])
    caption = _decoration(canvas, "shape")
    restore_selection_from_ids_for(canvas, {first[-1]}, set())
    caption.setSelected(True)
    before = snapshot_canvas_state_for(canvas)
    assert group_selection_for(canvas)
    state = group_state_for(canvas)
    assert len(state.groups) == 2
    assert state.groups[untouched_id].atom_ids == {unrelated}
    combined = next(group for gid, group in state.groups.items() if gid != untouched_id)
    assert combined.atom_ids == set(first + second)
    assert set(combined.items) == {caption, line}
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert not group_selection_for(canvas)


@pytest.mark.parametrize("kind", ["rotate", "flip"])
@pytest.mark.parametrize("phase", ["mutation", "push", "undo", "redo"])
def test_upright_group_transform_failure_is_atomic_and_retryable(canvas, kind, phase):
    _chain(canvas)
    for decoration in ("note", "image", "shape", "ts_bracket"):
        _decoration(canvas, decoration)
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    controller = canvas.services.scene_operations.scene_transform_controller
    history = canvas.services.history_service
    transform = (
        (lambda: controller.rotate_selected_items(90))
        if kind == "rotate"
        else (lambda: controller.flip_selected_items(True))
    )
    if phase in {"undo", "redo"}:
        transform()
        if phase == "redo":
            history.undo()
    before = snapshot_canvas_state_for(canvas)
    scene_items = set(canvas.scene().items())
    selection = set(canvas.scene().selectedItems())
    stacks = history.capture_stack_snapshot()
    if phase == "push":
        failure = mock.patch.object(history, "push", return_value=False)
    elif phase in {"undo", "redo"}:
        failure = mock.patch(
            "chemvas.ui.history_commands._apply_scene_item_state",
            side_effect=RuntimeError("item render failed"),
        )
    else:
        real_apply = controller._apply_scene_item_state

        def fail_after_mutating(item, state):
            real_apply(item, state)
            raise RuntimeError("item render failed after mutation")

        failure = mock.patch.object(
            controller, "_apply_scene_item_state", side_effect=fail_after_mutating
        )
    action = getattr(history, phase) if phase in {"undo", "redo"} else transform
    with failure, pytest.raises(RuntimeError):
        action()
    assert snapshot_canvas_state_for(canvas) == before
    assert set(canvas.scene().items()) == scene_items
    assert set(canvas.scene().selectedItems()) == selection
    history.verify_stack_snapshot(stacks)
    action()


@pytest.mark.parametrize(
    "failure_mode", ["mutation", "push_false", "push_error", "selection"]
)
def test_partial_molecule_group_failure_restores_exact_state(canvas, failure_mode):
    from chemvas.ui import scene_group_operations

    ids = _chain(canvas)
    shape = _decoration(canvas, "shape")
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    shape.setSelected(True)
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    before_scene = set(canvas.scene().items())
    before_selection = set(canvas.scene().selectedItems())
    stacks = history.capture_stack_snapshot()
    if failure_mode == "mutation":
        real_register = scene_group_operations.register_group_for

        def fail_after_register(*args, **kwargs):
            real_register(*args, **kwargs)
            raise RuntimeError("registration failed after mutation")

        failure = mock.patch.object(
            scene_group_operations,
            "register_group_for",
            side_effect=fail_after_register,
        )
    elif failure_mode == "selection":
        real_expand = scene_group_operations.expand_selection_to_groups_for

        def fail_after_expand(view):
            real_expand(view)
            raise RuntimeError("selection failed after publication")

        failure = mock.patch.object(
            scene_group_operations,
            "expand_selection_to_groups_for",
            side_effect=fail_after_expand,
        )
    elif failure_mode == "push_false":
        failure = mock.patch.object(history, "push", return_value=False)
    else:
        failure = mock.patch.object(
            history, "push", side_effect=RuntimeError("publication failed")
        )
    with failure, pytest.raises(RuntimeError):
        group_selection_for(canvas)
    assert snapshot_canvas_state_for(canvas) == before
    assert set(canvas.scene().items()) == before_scene
    assert set(canvas.scene().selectedItems()) == before_selection
    history.verify_stack_snapshot(stacks)
    assert group_selection_for(canvas)


def test_explicit_regroup_repairs_a_legacy_fragment_only_group(canvas):
    ids = _chain(canvas)
    register_group_for(canvas, {ids[0], ids[1]}, [])
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    before = snapshot_canvas_state_for(canvas)
    assert group_selection_for(canvas)
    assert next(iter(group_state_for(canvas).groups.values())).atom_ids == set(ids)
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert not group_selection_for(canvas)


@pytest.mark.parametrize("kind", ["note", "image", "shape", "ts_bracket"])
@pytest.mark.parametrize("outcome", ["commit", "cancel", "return"])
def test_real_rotation_handle_preserves_upright_group_and_baseline_redo(
    canvas, app, kind, outcome
):
    canvas.resize(800, 600)
    canvas.show()
    canvas.services.input.tool_mode_controller.set_tool("select")
    ids = _chain(canvas)
    item = _decoration(canvas, kind)
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    controller = canvas.services.scene_operations.scene_transform_controller
    history = canvas.services.history_service
    controller.translate_selected_items(7, 0)
    history.undo()
    app.processEvents()
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    center = controller._rotation_center(set(ids), [item])
    knobs = [
        item
        for item in selection_outlines_for(canvas)
        if item.data(1) == ROTATION_HANDLE_TYPE
    ]
    assert len(knobs) == 1
    start = canvas.mapFromScene(knobs[0].pos()) - QPoint(
        0, round(ROTATION_HANDLE_STEM_PX + HANDLE_SCREEN_PX / 2)
    )
    end = canvas.mapFromScene(_turn(canvas.mapToScene(start), center))
    errors = []
    callback_state_for(canvas).error = errors.append
    viewport = canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, end, 30)
    assert snapshot_canvas_state_for(canvas) != before
    if outcome == "cancel":
        QTest.keyClick(viewport, Qt.Key.Key_Escape)
    elif outcome == "return":
        QTest.mouseMove(viewport, start, 30)
        end = start
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert errors == []
    if outcome == "commit":
        after = snapshot_canvas_state_for(canvas)
        assert after != before
        assert item.rotation() == 0
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
    else:
        assert snapshot_canvas_state_for(canvas) == before
        history.verify_stack_snapshot(stacks)
