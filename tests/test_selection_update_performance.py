"""Bound repeat work on real selection operations, not wall-clock budgets."""

import json
from itertools import pairwise
from unittest import mock

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.molecule.structure_mutation_access import add_atom_for, add_bond_for
from chemvas.ui.scene import scene_geometry as glyph_geometry
from chemvas.ui.scene.scene_item_access import create_scene_item_from_state
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from chemvas.ui.selection.selection_queries import selected_ids_for
from chemvas.ui.selection.selection_state import selected_notes_for, selection_state_for
from chemvas.ui.selection.selection_update_batch import batch_selection_updates
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


def _chain(canvas, count=18, *, labels=False):
    before_atom = canvas.model.next_atom_id
    before_bond = len(canvas.model.bonds)
    ids = [
        add_atom_for(
            canvas, "O" if labels and i in {0, count - 1} else "C", i * 20, i % 2 * 15
        )
        for i in range(count)
    ]
    for a, b in pairwise(ids):
        add_bond_for(canvas, a, b)
    canvas.services.canvas_history_recording_service.record_additions(
        before_atom, before_bond, None
    )
    canvas.services.structure_build_service.render_model()
    return ids


def _outline(canvas):
    return canvas.services.selection.outline_service


@pytest.mark.parametrize("count", [1, 12])
def test_select_all_builds_outline_once_with_notes(canvas, count):
    _chain(canvas)
    notes = [
        create_scene_item_from_state(
            canvas, {"kind": "note", "text": f"Step {i}", "x": i * 40, "y": 60}
        )
        for i in range(count)
    ]
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service.capture_stack_snapshot()
    outline = _outline(canvas)
    with mock.patch.object(
        outline, "selection_path_for_bond", wraps=outline.selection_path_for_bond
    ) as paths:
        assert select_all_scene_items_for(canvas)
    assert paths.call_count == len(canvas.model.bonds)
    assert set(notes) == set(selected_notes_for(canvas))
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(history)


@pytest.mark.parametrize("count", [4, 18])
def test_selected_addition_undo_does_not_build_decreasing_outlines(canvas, count):
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    _chain(canvas, count)
    drawn = snapshot_canvas_state_for(canvas)
    assert select_all_scene_items_for(canvas)
    outline = _outline(canvas)
    history = canvas.services.history_service
    with mock.patch.object(
        outline, "selection_path_for_bond", wraps=outline.selection_path_for_bond
    ) as paths:
        history.undo()
    assert paths.call_count == 0
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    assert not canvas.scene().selectedItems()
    assert not canvas.scene().signalsBlocked()
    assert not selection_state_for(canvas).suspend_outline
    history.redo()
    assert snapshot_canvas_state_for(canvas) == drawn


@pytest.mark.parametrize("kind", ["rotate", "flip", "knob"])
def test_transform_builds_outline_once_per_frame(canvas, kind):
    _chain(canvas, 6, labels=True)
    assert select_all_scene_items_for(canvas)
    outline = _outline(canvas)
    controller = canvas.services.scene_transform_controller
    with mock.patch.object(
        outline, "selection_path_for_bond", wraps=outline.selection_path_for_bond
    ) as paths:
        if kind == "rotate":
            controller.rotate_selected_items(15)
        elif kind == "flip":
            controller.flip_selected_items(True)
        else:
            session = controller.begin_rotation_drag(QPointF(120, 0))
            assert session is not None
            controller.update_rotation_drag(session, QPointF(120, 30))
    assert paths.call_count == len(canvas.model.bonds)


def test_rotation_reuses_unchanged_glyph_clearance_geometry(canvas):
    _chain(canvas, 6, labels=True)
    assert select_all_scene_items_for(canvas)
    controller = canvas.services.scene_transform_controller
    controller.rotate_selected_items(5)
    with mock.patch.object(
        glyph_geometry,
        "_glyph_clearance_path",
        wraps=glyph_geometry._glyph_clearance_path,
    ) as envelopes:
        for _ in range(3):
            controller.rotate_selected_items(5)
    assert envelopes.call_count == 0


@pytest.mark.parametrize("fail", [False, True])
def test_nested_batch_restores_prior_flags_without_early_repaint(canvas, fail):
    _chain(canvas, 4)
    style = selection_state_for(canvas)
    style.suspend_outline = True
    canvas.scene().blockSignals(True)
    outline = _outline(canvas)
    with mock.patch.object(outline, "update_selection_outline") as refresh:
        if fail:
            with pytest.raises(RuntimeError, match="selection failed"):
                with batch_selection_updates(canvas):
                    with batch_selection_updates(canvas):
                        raise RuntimeError("selection failed")
        else:
            with batch_selection_updates(canvas):
                assert select_all_scene_items_for(canvas)
    assert style.suspend_outline
    assert canvas.scene().signalsBlocked()
    # Calls from note/command owners may be suppressed by the existing flag;
    # these atom-only operations have no reason even to request a refresh.
    refresh.assert_not_called()
    style.suspend_outline = False
    canvas.scene().blockSignals(False)


@pytest.mark.parametrize("phase", ["remove", "refresh"])
def test_failed_undo_batch_preserves_exact_scene_stacks_and_retry(canvas, phase):
    _chain(canvas, 6)
    assert select_all_scene_items_for(canvas)
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    selected = set(canvas.scene().selectedItems())
    scene_items = set(canvas.scene().items())
    stacks = history.capture_stack_snapshot()
    if phase == "remove":
        owner = canvas.services.canvas_atom_mutation_service
        original = owner.remove_atom_only
        calls = 0

        def fail(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("batch failed")
            return original(*args, **kwargs)

        patch = mock.patch.object(owner, "remove_atom_only", side_effect=fail)
    else:
        patch = mock.patch.object(
            _outline(canvas),
            "clear_selection_outlines",
            side_effect=RuntimeError("batch failed"),
        )
    with patch, pytest.raises(RuntimeError, match="batch failed"):
        history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert set(canvas.scene().selectedItems()) == selected
    assert set(canvas.scene().items()) == scene_items
    history.verify_stack_snapshot(stacks)
    assert not canvas.scene().signalsBlocked()
    assert not selection_state_for(canvas).suspend_outline
    history.undo()
    assert not canvas.model.atoms
    history.redo()
    assert snapshot_canvas_state_for(canvas) == before


def test_actual_selected_paste_undo_is_bounded_and_redo_exact(canvas):
    _chain(canvas, 18)
    create_scene_item_from_state(
        canvas, {"kind": "note", "text": "Synthetic step", "x": 10, "y": 60}
    )
    assert select_all_scene_items_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    controller = canvas.services.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    assert payload is not None
    assert controller.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    pasted = snapshot_canvas_state_for(canvas)
    assert len(canvas.model.atoms) == 36
    history = canvas.services.history_service
    outline = _outline(canvas)
    with mock.patch.object(
        outline, "selection_path_for_bond", wraps=outline.selection_path_for_bond
    ) as paths:
        history.undo()
    assert paths.call_count == 0
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    history.redo()
    assert snapshot_canvas_state_for(canvas) == pasted


def _paste_fixture(canvas, note_count):
    atom_ids = set(_chain(canvas))
    notes = [
        create_scene_item_from_state(
            canvas, {"kind": "note", "text": f"Step {i}", "x": i * 40, "y": 60}
        )
        for i in range(note_count)
    ]
    assert select_all_scene_items_for(canvas)
    controller = canvas.services.scene_clipboard_controller
    payload = controller.selection_payload_for_clipboard()
    assert payload is not None
    # Use only the in-memory provider, including when this file runs natively.
    return controller, lambda: (payload, json.dumps(payload)), atom_ids, notes


@pytest.mark.parametrize("note_count", [0, 1, 12])
def test_forward_paste_builds_one_outline_and_keeps_exact_history(canvas, note_count):
    controller, provider, original_atoms, original_notes = _paste_fixture(
        canvas, note_count
    )
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    outline = _outline(canvas)
    with (
        mock.patch.object(
            controller, "_clipboard", side_effect=AssertionError("OS clipboard")
        ),
        mock.patch.object(
            outline, "update_selection_outline", wraps=outline.update_selection_outline
        ) as refresh,
        mock.patch.object(
            outline, "selection_path_for_bond", wraps=outline.selection_path_for_bond
        ) as paths,
    ):
        assert controller.paste_selection_from_clipboard(payload_provider=provider)
    assert refresh.call_count == 1
    assert paths.call_count == 17
    assert len(canvas.model.atoms) == 36
    assert len(canvas.model.bonds) == 34
    assert selected_ids_for(canvas)[0] == set(canvas.model.atoms) - original_atoms
    assert len(selected_notes_for(canvas)) == note_count
    assert not set(original_notes).intersection(selected_notes_for(canvas))
    pasted = snapshot_canvas_state_for(canvas)
    assert document_is_dirty_for(canvas, pasted)
    after_stacks = history.capture_stack_snapshot()
    assert len(after_stacks.history) == len(stacks.history) + 1
    history.verify_stack_snapshot(
        stacks, history=(*stacks.history, after_stacks.history[-1])
    )
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, before)
    history.verify_stack_snapshot(stacks, redo_stack=(after_stacks.history[-1],))
    history.redo()
    assert snapshot_canvas_state_for(canvas) == pasted
    history.verify_stack_snapshot(after_stacks)


@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("suspended", [False, True])
def test_forward_paste_preserves_outer_selection_batch(canvas, blocked, suspended):
    controller, provider, _, _ = _paste_fixture(canvas, 3)
    style = selection_state_for(canvas)
    style.suspend_outline = suspended
    canvas.scene().blockSignals(blocked)
    outline = _outline(canvas)
    try:
        with mock.patch.object(
            outline, "update_selection_outline", wraps=outline.update_selection_outline
        ) as refresh:
            assert controller.paste_selection_from_clipboard(payload_provider=provider)
        assert style.suspend_outline is suspended
        assert canvas.scene().signalsBlocked() is blocked
        assert refresh.call_count == (0 if suspended else 1)
        assert len(selected_notes_for(canvas)) == 3
    finally:
        style.suspend_outline = False
        canvas.scene().blockSignals(False)


@pytest.mark.parametrize(
    "phase, nested", [("note", False), ("note", True), ("refresh", False)]
)
def test_failed_forward_paste_restores_exact_scene_stacks_and_retry(
    canvas, phase, nested
):
    controller, provider, _, _ = _paste_fixture(canvas, 3)
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    selected = set(canvas.scene().selectedItems())
    notes = list(selected_notes_for(canvas))
    scene_items = set(canvas.scene().items())
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    clipboard = canvas.runtime_state.scene_clipboard_state
    paste_state = (clipboard.paste_source_json, clipboard.paste_count)
    style = selection_state_for(canvas)
    style.suspend_outline = nested
    canvas.scene().blockSignals(nested)
    selection = canvas.services.selection
    owner, method = (
        (selection, "select_note")
        if phase == "note"
        else (_outline(canvas), "update_selection_outline")
    )
    original = getattr(owner, method)
    error = RuntimeError("paste selection failed after mutation")
    calls = 0

    def fail_after_mutation(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == (2 if phase == "note" else 1):
            assert len(canvas.model.atoms) == 36
            raise error
        return result

    try:
        with mock.patch.object(owner, method, side_effect=fail_after_mutation):
            with pytest.raises(RuntimeError) as caught:
                controller.paste_selection_from_clipboard(payload_provider=provider)
        assert style.suspend_outline is nested
        assert canvas.scene().signalsBlocked() is nested
    finally:
        style.suspend_outline = False
        canvas.scene().blockSignals(False)
    assert caught.value is error
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, before)
    assert set(canvas.scene().selectedItems()) == selected
    assert list(selected_notes_for(canvas)) == notes
    assert set(canvas.scene().items()) == scene_items
    assert (clipboard.paste_source_json, clipboard.paste_count) == paste_state
    history.verify_stack_snapshot(stacks)
    assert not canvas.scene().signalsBlocked()
    assert not selection_state_for(canvas).suspend_outline
    assert controller.paste_selection_from_clipboard(payload_provider=provider)
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


def test_batch_refresh_publishes_final_selection_info_once(canvas):
    _chain(canvas, 8)
    info = canvas.runtime_state.selection_info_state
    observations = []
    info.callback = lambda *_: observations.append(len(canvas.model.atoms))
    assert select_all_scene_items_for(canvas)
    assert observations == [8]
    observations.clear()
    canvas.services.history_service.undo()
    assert observations == [0]
    assert info.signature is None
    assert info.pending_signature is None
    assert info.cache == ("", "")


def test_real_canvas_keys_and_rotation_knob_keep_exact_history(canvas, app, tmp_path):
    from chemvas.features.selection import ROTATION_HANDLE_TYPE

    _chain(canvas, 6, labels=True)
    for i in range(4):
        create_scene_item_from_state(
            canvas, {"kind": "note", "text": f"Step {i}", "x": i * 40, "y": 70}
        )
    canvas.resize(800, 600)
    canvas.show()
    canvas.centerOn(50, 20)
    canvas.setFocus()
    app.processEvents()
    canvas.services.tool_mode_controller.set_tool("select")
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(selected_notes_for(canvas)) == 4
    assert canvas.grab().save(str(tmp_path / "selected-before.png"))
    knob = next(
        item for item in canvas.scene().items() if item.data(1) == ROTATION_HANDLE_TYPE
    )
    start = canvas.mapFromScene(knob.sceneBoundingRect().center())
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    for delta in (10, 20, 30):
        QTest.mouseMove(canvas.viewport(), start + QPoint(delta, 5))
    QTest.mouseRelease(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(30, 5)
    )
    app.processEvents()
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert canvas.grab().save(str(tmp_path / "rotated-after.png"))
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, before)
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
