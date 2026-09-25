"""Escape cancels Perspective while ordinary tool switches still commit."""

from itertools import pairwise
from unittest import mock

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.molecule.structure_mutation_access import add_bond_for
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
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _start_drag(canvas, app, *, cached, axis):
    ids = [
        canvas.services.canvas_atom_mutation_service.add_atom("C", x, y)
        for x, y in ((0.0, 0.0), (20.0, 0.0), (30.0, 17.0), (50.0, 17.0))
    ]
    for first, second in pairwise(ids):
        add_bond_for(canvas, first, second)
    canvas.services.structure_build_service.render_model()
    canvas.services.selection.select_all()
    rotation = canvas.services.selection_rotation_controller
    if cached:
        assert rotation.begin_selection_3d_rotation()
        rotation.update_selection_3d_rotation(35, 10)
        rotation.end_selection_3d_rotation()
    history = canvas.services.history_service
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(100, 100), QPointF(140, 100), "line"
    )
    history.undo()
    assert history.can_redo()
    canvas.services.selection.select_all()
    canvas.services.tool_mode_controller.set_tool("perspective")
    app.processEvents()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    coords = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
    assert bool(coords) == cached
    stacks = history.capture_stack_snapshot()
    selected = set(canvas.scene().selectedItems())
    atom = canvas.model.atoms[ids[0]]
    start_scene = QPointF(atom.x, atom.y)
    if axis:
        first, second = (canvas.model.atoms[atom_id] for atom_id in ids[1:3])
        start_scene = QPointF((first.x + second.x) / 2, (first.y + second.y) / 2)
    start = canvas.mapFromScene(start_scene)
    end = start + QPoint(65, 20)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), start + QPoint(30, 10))
    QTest.mouseMove(canvas.viewport(), end)
    app.processEvents()
    assert rotation.rotation.mode == ("bond" if axis else "rigid")
    assert canvas.services.canvas_document_session_service.snapshot_state() != before
    return before, coords, stacks, selected, end


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("axis", [False, True])
@pytest.mark.parametrize("ending", ["escape", "switch"])
def test_perspective_escape_cancels_but_tool_switch_commits(
    canvas, app, cached, axis, ending
):
    before, coords, stacks, selected, end = _start_drag(
        canvas, app, cached=cached, axis=axis
    )
    history = canvas.services.history_service
    if ending == "escape":
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
    else:
        canvas.services.tool_mode_controller.set_tool("select")
    app.processEvents()
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert canvas.services.tool_controller.active.name == "select"
    if ending == "escape":
        assert after == before
        assert dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d) == coords
        history.verify_stack_snapshot(stacks)
    else:
        assert after != before
        assert not history.can_redo()
    after_stacks = history.capture_stack_snapshot()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    assert set(canvas.scene().selectedItems()) == selected
    history.verify_stack_snapshot(after_stacks)
    if ending == "switch":
        history.undo()
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
    else:
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        history.verify_stack_snapshot(stacks)
        canvas.services.tool_mode_controller.set_tool("perspective")
        atom = next(iter(canvas.model.atoms.values()))
        start = canvas.mapFromScene(QPointF(atom.x, atom.y))
        next_end = start + QPoint(30, 15)
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), next_end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=next_end)
        app.processEvents()
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() != before
        )
        history.undo()
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )


def test_perspective_cancel_failure_does_not_later_commit(canvas, app):
    before, coords, stacks, _selected, end = _start_drag(
        canvas, app, cached=False, axis=False
    )
    tool = canvas.services.tool_controller.active
    rotation = canvas.services.selection_rotation_controller
    preview = rotation._rotation_preview_authority
    restore = preview.restore

    def restore_then_fail(*_args):
        restore()
        raise RuntimeError("cancel observer failed")

    with mock.patch.object(type(preview), "restore", restore_then_fail):
        with pytest.raises(RuntimeError, match="cancel observer failed"):
            tool.cancel_active_rotation()
    assert not tool._rotating
    assert rotation._rotation_preview_authority is None
    assert not rotation.rotation.atom_ids
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d) == coords
    canvas.services.history_service.verify_stack_snapshot(stacks)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(stacks)
