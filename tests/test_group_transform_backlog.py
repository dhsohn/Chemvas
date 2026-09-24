from chemvas.ui.annotations.projections import resolve_projection
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

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
from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_decoration_access import (
    add_shape_for,
    add_ts_bracket_for,
)
from chemvas.ui.scene.scene_group_operations import group_selection_for
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from chemvas.ui.selection.selection_style_access import restore_selection_from_ids_for
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
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _chain(canvas, *, offset=0):
    ids = [
        canvas.services.canvas_atom_mutation_service.add_atom(
            "C", offset + index * 20, (index % 2) * 10
        )
        for index in range(4)
    ]
    for a, b in pairwise(ids):
        add_bond_for(canvas, a, b)
    canvas.services.structure_build_service.render_model()
    return ids


def _decoration(canvas, kind):
    if kind == "note":
        return canvas.services.note_controller.create_text_note(
            QPointF(110, 70), "caption"
        )
    if kind == "shape":
        return add_shape_for(canvas, QRectF(110, 70, 30, 20), shape_kind="rect")
    if kind == "ts_bracket":
        return add_ts_bracket_for(canvas, QRectF(110, 70, 30, 20))
    stream = BytesIO()
    Image.new("RGB", (3, 2), (220, 30, 20)).save(stream, format="PNG")
    return canvas.services.scene_item_controller.create_scene_item_from_state(
        image_state_from_bytes(stream.getvalue(), x=110, y=70, width=30)
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
def test_rotation_transforms_decorations_and_roundtrips(canvas, kind, grouped, drag):
    ids = _chain(canvas)
    item = _decoration(canvas, kind)
    select_all_scene_items_for(canvas)
    if grouped:
        assert group_selection_for(canvas)
    controller = canvas.services.scene_transform_controller
    # The expected pivot includes the decoration, not just the molecule.
    center = controller._rotation_center(set(ids), [item])
    old_rect = item.sceneBoundingRect()
    before_item = scene_item_state_for(canvas, item)
    before = canvas.services.canvas_document_session_service.snapshot_state()
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
    if kind == "note":
        assert item.sceneBoundingRect().width() == pytest.approx(old_rect.height())
        assert item.sceneBoundingRect().height() == pytest.approx(old_rect.width())
        assert item.rotation() == 90
    else:
        assert item.sceneBoundingRect().size() == old_rect.size()
        assert item.rotation() == 0
    after_item = scene_item_state_for(canvas, item)
    if kind == "image":
        assert after_item["data_base64"] == before_item["data_base64"]
    if kind == "note":
        assert after_item["text"] == before_item["text"]
    after = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.runtime_state.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.runtime_state.history_service.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


@pytest.mark.parametrize("horizontal", [True, False])
def test_flip_uses_one_pivot_for_molecule_arrow_and_upright_item(canvas, horizontal):
    ids = _chain(canvas)
    image = _decoration(canvas, "image")
    arrow = canvas.services.scene_decoration_service.add_arrow(
        QPointF(60, 30), QPointF(100, 30), "arrow"
    )
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    controller = canvas.services.scene_transform_controller
    center = controller._rotation_center(set(ids), [arrow, image])
    old_image = image.sceneBoundingRect().center()
    old_arrow = scene_item_state_for(canvas, arrow)
    before = canvas.services.canvas_document_session_service.snapshot_state()
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
    after = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.runtime_state.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.runtime_state.history_service.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


def test_grouping_partial_molecule_records_and_moves_whole_component(canvas):
    ids = _chain(canvas)
    level = canvas.services.scene_decoration_service.add_arrow(
        QPointF(100, 40), QPointF(140, 40), "line"
    )
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    level.setSelected(True)
    before_group = canvas.services.canvas_document_session_service.snapshot_state()
    assert group_selection_for(canvas)
    group = next(iter(canvas.runtime_state.group_state.groups.values()))
    assert group.atom_ids == set(ids)
    grouped = canvas.services.canvas_document_session_service.snapshot_state()
    before_positions = {
        aid: (canvas.model.atoms[aid].x, canvas.model.atoms[aid].y) for aid in ids
    }
    canvas.services.scene_transform_controller.translate_selected_items(0, 4)
    for atom_id, (x, y) in before_positions.items():
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            x,
            y + 4,
        )
    canvas.runtime_state.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == grouped
    canvas.runtime_state.history_service.undo()
    assert (
        canvas.services.canvas_document_session_service.snapshot_state() == before_group
    )
    canvas.services.canvas_document_session_service.restore_state(grouped)
    restore_selection_from_ids_for(canvas, set(), set())
    restored_level = resolve_projection(
        canvas, next(iter(canvas.runtime_state.group_state.groups.values())).item_ids[0]
    )
    restored_level.setSelected(True)
    canvas.services.selection.expand_selection_to_groups()
    canvas.services.scene_transform_controller.translate_selected_items(0, 4)
    for atom_id, (x, y) in before_positions.items():
        assert (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y) == (
            x,
            y + 4,
        )


def test_direct_partial_atom_move_remains_a_reshape(canvas):
    ids = _chain(canvas)
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    before = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.services.scene_transform_controller.translate_selected_items(0, 4)
    assert canvas.model.atoms[ids[0]].y == 4
    for atom_id in ids[1:]:
        assert canvas.model.atoms[atom_id].y == before["model"]["atoms"][atom_id]["y"]


def test_regroup_expands_absorbed_legacy_groups_to_component_closure(canvas):
    first = _chain(canvas)
    second = _chain(canvas, offset=200)
    unrelated = canvas.services.canvas_atom_mutation_service.add_atom("N", 500, 0)
    line = canvas.services.scene_decoration_service.add_arrow(
        QPointF(150, 80), QPointF(190, 80), "line"
    )
    other = canvas.services.scene_decoration_service.add_arrow(
        QPointF(350, 80), QPointF(390, 80), "arrow"
    )
    register_group_for(
        canvas, {first[0], second[0]}, [require_scene_record_id(item) for item in []]
    )
    register_group_for(
        canvas, {second[-1]}, [require_scene_record_id(item) for item in [line]]
    )
    untouched_id = register_group_for(
        canvas, {unrelated}, [require_scene_record_id(item) for item in [other]]
    )
    caption = _decoration(canvas, "shape")
    restore_selection_from_ids_for(canvas, {first[-1]}, set())
    caption.setSelected(True)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    assert group_selection_for(canvas)
    state = canvas.runtime_state.group_state
    assert len(state.groups) == 2
    assert state.groups[untouched_id].atom_ids == {unrelated}
    combined = next(group for gid, group in state.groups.items() if gid != untouched_id)
    assert combined.atom_ids == set(first + second)
    assert set(combined.item_ids) == {caption.data(3), line.data(3)}
    after = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    assert not group_selection_for(canvas)


@pytest.mark.parametrize("kind", ["rotate", "flip"])
@pytest.mark.parametrize("phase", ["mutation", "push", "undo", "redo"])
def test_upright_group_transform_failure_is_atomic_and_retryable(canvas, kind, phase):
    _chain(canvas)
    for decoration in ("note", "image", "shape", "ts_bracket"):
        _decoration(canvas, decoration)
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    controller = canvas.services.scene_transform_controller
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
    before = canvas.services.canvas_document_session_service.snapshot_state()
    scene_items = set(canvas.scene().items())
    selection = set(canvas.scene().selectedItems())
    stacks = history.capture_stack_snapshot()
    if phase == "push":
        failure = mock.patch.object(history, "push", return_value=False)
    elif phase in {"undo", "redo"}:
        failure = mock.patch.object(
            canvas.services.scene_item_controller,
            "apply_scene_item_state",
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
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert set(canvas.scene().items()) == scene_items
    assert set(canvas.scene().selectedItems()) == selection
    history.verify_stack_snapshot(stacks)
    action()


@pytest.mark.parametrize(
    "failure_mode", ["mutation", "push_false", "push_error", "selection"]
)
def test_partial_molecule_group_failure_restores_exact_state(canvas, failure_mode):
    from chemvas.ui.scene import scene_group_operations

    ids = _chain(canvas)
    shape = _decoration(canvas, "shape")
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    shape.setSelected(True)
    history = canvas.services.history_service
    before = canvas.services.canvas_document_session_service.snapshot_state()
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
        real_expand = canvas.services.selection.expand_selection_to_groups

        def fail_after_expand():
            real_expand()
            raise RuntimeError("selection failed after publication")

        failure = mock.patch.object(
            canvas.services.selection,
            "expand_selection_to_groups",
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
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert set(canvas.scene().items()) == before_scene
    assert set(canvas.scene().selectedItems()) == before_selection
    history.verify_stack_snapshot(stacks)
    assert group_selection_for(canvas)


def test_explicit_regroup_repairs_a_legacy_fragment_only_group(canvas):
    ids = _chain(canvas)
    register_group_for(
        canvas, {ids[0], ids[1]}, [require_scene_record_id(item) for item in []]
    )
    restore_selection_from_ids_for(canvas, {ids[0]}, set())
    before = canvas.services.canvas_document_session_service.snapshot_state()
    assert group_selection_for(canvas)
    assert next(iter(canvas.runtime_state.group_state.groups.values())).atom_ids == set(
        ids
    )
    after = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    assert not group_selection_for(canvas)


@pytest.mark.parametrize("kind", ["note", "image", "shape", "ts_bracket"])
@pytest.mark.parametrize("outcome", ["commit", "cancel", "return"])
def test_real_rotation_handle_preserves_group_and_baseline_redo(
    canvas, app, kind, outcome
):
    canvas.resize(800, 600)
    canvas.show()
    canvas.services.tool_mode_controller.set_tool("select")
    ids = _chain(canvas)
    item = _decoration(canvas, kind)
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    controller = canvas.services.scene_transform_controller
    history = canvas.services.history_service
    controller.translate_selected_items(7, 0)
    history.undo()
    app.processEvents()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    stacks = history.capture_stack_snapshot()
    center = controller._rotation_center(set(ids), [item])
    knobs = [
        item
        for item in canvas.runtime_state.selection_state.outlines
        if item.data(1) == ROTATION_HANDLE_TYPE
    ]
    assert len(knobs) == 1
    start = canvas.mapFromScene(knobs[0].pos()) - QPoint(
        0, round(ROTATION_HANDLE_STEM_PX + HANDLE_SCREEN_PX / 2)
    )
    end = canvas.mapFromScene(_turn(canvas.mapToScene(start), center))
    errors = []
    canvas.runtime_state.callback_state.error = errors.append
    viewport = canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, end, 30)
    assert canvas.services.canvas_document_session_service.snapshot_state() != before
    if outcome == "cancel":
        QTest.keyClick(viewport, Qt.Key.Key_Escape)
    elif outcome == "return":
        QTest.mouseMove(viewport, start, 30)
        end = start
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert errors == []
    if outcome == "commit":
        after = canvas.services.canvas_document_session_service.snapshot_state()
        assert after != before
        assert item.rotation() == (pytest.approx(90, abs=1) if kind == "note" else 0)
        history.undo()
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        history.redo()
        assert canvas.services.canvas_document_session_service.snapshot_state() == after
    else:
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        history.verify_stack_snapshot(stacks)
