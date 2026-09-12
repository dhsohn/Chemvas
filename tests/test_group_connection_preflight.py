"""Cross-group connections are refused before Qt edits or atom-label merges."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from chemvas.domain.document.state import build_document_payload, extract_document_state
from chemvas.ui.atom_label_access import atom_label_service
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_group_state import group_state_for, register_group_for
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.scene_group_operations import (
    GROUP_CONNECTION_MESSAGE,
    group_selection_for,
)
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import (
    add_atom_for,
    add_bond_between_points_for,
    add_bond_for,
)
from tests.test_active_gesture_document_edits import qt_errors as qt_errors
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _populate(canvas, *, overlap=False, grouping="different"):
    points = [(0, 0), (-20, 0), (0 if overlap else 40, 0), (60, 0)]
    ids = [add_atom_for(canvas, "C", x, y) for x, y in points]
    for first, second in ((ids[0], ids[1]), (ids[2], ids[3])):
        add_bond_graphics_for(canvas, add_bond_for(canvas, first, second))
    notes = [
        canvas.services.tool_controller.context.create_text_note(QPointF(x, 40), text)
        for x, text in ((-20, "first"), (40, "second"))
    ]
    if grouping == "same":
        register_group_for(canvas, set(ids), notes)
    else:
        register_group_for(canvas, set(ids[:2]), notes[:1])
        if grouping == "different":
            register_group_for(canvas, set(ids[2:]), notes[1:])
    return ids


def _stacks(canvas):
    history = canvas.services.history_service
    return list(history.state.history), list(history.state.redo_stack)


def _join(canvas, route):
    if route == "builder":
        return add_bond_between_points_for(
            canvas, QPointF(0, 0), QPointF(40, 0), "single", 1
        )
    canvas.services.input.tool_mode_controller.set_tool("bond")
    viewport = canvas.viewport()
    QTest.mousePress(
        viewport, Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF(0, 0))
    )
    QTest.mouseMove(viewport, canvas.mapFromScene(QPointF(40, 0)))
    QTest.mouseRelease(
        viewport, Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF(40, 0))
    )


@pytest.mark.parametrize("route", ["builder", "mouse"])
def test_cross_group_bond_refuses_then_explicit_regroup_allows_retry(
    drawing, qt_errors, route
):
    window, canvas = drawing
    _populate(canvas)
    # Retain a real previous Redo while refusing the attempted connection.
    add_bond_between_points_for(canvas, QPointF(100, 80), QPointF(120, 80), "single", 1)
    history = canvas.services.history_service
    history.undo()
    before, stacks = snapshot_canvas_state_for(canvas), _stacks(canvas)
    _join(canvas, route)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == before
    assert _stacks(canvas) == stacks
    assert window.statusBar().currentMessage() == GROUP_CONNECTION_MESSAGE
    if route == "mouse":
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            pos=canvas.mapFromScene(QPointF(40, 0)),
        )
        assert snapshot_canvas_state_for(canvas) == before
        assert _stacks(canvas) == stacks
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    regrouped = snapshot_canvas_state_for(canvas)
    _join(canvas, route)
    assert not qt_errors
    after = snapshot_canvas_state_for(canvas)
    assert len([bond for bond in canvas.model.bonds if bond is not None]) == 3
    assert len(group_state_for(canvas).groups) == 1
    history.undo()
    assert snapshot_canvas_state_for(canvas) == regrouped
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_cross_group_overlapping_label_merge_refuses_before_element_or_graphics(
    drawing,
):
    window, canvas = drawing
    ids = _populate(canvas, overlap=True)
    before, stacks = snapshot_canvas_state_for(canvas), _stacks(canvas)
    original_items = set(canvas.scene().items())
    atom_label_service(canvas).add_or_update_atom_label(ids[0], "N")
    assert snapshot_canvas_state_for(canvas) == before
    assert set(canvas.scene().items()) == original_items
    assert _stacks(canvas) == stacks
    assert window.statusBar().currentMessage() == GROUP_CONNECTION_MESSAGE


@pytest.mark.parametrize("text,allow_merge", [("C", True), ("", True), ("N", False)])
def test_nonmerging_label_edits_are_not_rejected(drawing, text, allow_merge):
    window, canvas = drawing
    ids = _populate(canvas, overlap=True)
    groups_before = snapshot_canvas_state_for(canvas)["groups"]
    atom_label_service(canvas).add_or_update_atom_label(
        ids[0], text, allow_merge=allow_merge
    )
    assert set(canvas.model.atoms) == set(ids)
    assert snapshot_canvas_state_for(canvas)["groups"] == groups_before
    assert window.statusBar().currentMessage() != GROUP_CONNECTION_MESSAGE


@pytest.mark.parametrize("grouping", ["same", "one"])
def test_same_group_or_ungrouped_component_connection_is_allowed(drawing, grouping):
    _window, canvas = drawing
    ids = _populate(canvas, grouping=grouping)
    before = snapshot_canvas_state_for(canvas)
    assert _join(canvas, "builder") == (ids[0], ids[2])
    after = snapshot_canvas_state_for(canvas)
    assert len(group_state_for(canvas).groups) == 1
    assert next(iter(group_state_for(canvas).groups.values())).atom_ids == set(ids)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_existing_bond_style_change_does_not_require_regroup(drawing):
    _window, canvas = drawing
    _populate(canvas)
    before = snapshot_canvas_state_for(canvas)
    assert add_bond_between_points_for(
        canvas, QPointF(0, 0), QPointF(-20, 0), "double", 2
    ) == (0, 1)
    assert canvas.model.bonds[0].order == 2
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("grouping,survivor", [("same", 0), ("one", 0), ("one", 2)])
def test_allowed_label_merge_preserves_group_membership_and_history(
    drawing, grouping, survivor
):
    _window, canvas = drawing
    ids = _populate(canvas, overlap=True, grouping=grouping)
    before = snapshot_canvas_state_for(canvas)
    old_group = next(iter(group_state_for(canvas).groups.values()))
    original_items = list(old_group.items)
    atom_label_service(canvas).add_or_update_atom_label(ids[survivor], "N")
    remaining = set(ids) - {ids[2 if survivor == 0 else 0]}
    assert set(canvas.model.atoms) == remaining
    group = next(iter(group_state_for(canvas).groups.values()))
    assert group.atom_ids == remaining
    assert group.items == original_items
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("failure", ["exception", "refusal"])
def test_label_merge_publication_failure_restores_group_and_previous_redo(
    drawing, monkeypatch, failure
):
    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    add_bond_between_points_for(canvas, QPointF(100, 80), QPointF(120, 80), "single", 1)
    history = canvas.services.history_service
    history.undo()
    before, stacks = snapshot_canvas_state_for(canvas), _stacks(canvas)
    with monkeypatch.context() as fault:

        def reject(_command):
            if failure == "exception":
                raise RuntimeError("injected history publication failure")
            return False

        fault.setattr(history, "push", reject)
        with pytest.raises((RuntimeError, ValueError)):
            atom_label_service(canvas).add_or_update_atom_label(0, "N")
    assert snapshot_canvas_state_for(canvas) == before
    assert _stacks(canvas) == stacks
    atom_label_service(canvas).add_or_update_atom_label(0, "N")
    assert next(iter(group_state_for(canvas).groups.values())).atom_ids == {0, 1, 3}
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


def test_disabled_history_still_applies_label_merge_and_group_update(drawing):
    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    history = canvas.services.history_service
    history.set_enabled(False)
    stacks = _stacks(canvas)
    atom_label_service(canvas).add_or_update_atom_label(0, "N")
    assert set(canvas.model.atoms) == {0, 1, 3}
    assert next(iter(group_state_for(canvas).groups.values())).atom_ids == {0, 1, 3}
    assert _stacks(canvas) == stacks
    history.set_enabled(True)


def test_explicit_group_mark_survives_merge_as_valid_document_item(drawing):
    from chemvas.ui.scene_decoration_access import materialize_mark_for_atom_for

    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    mark = materialize_mark_for_atom_for(canvas, 2, QPointF(5, 5), kind="radical")
    assert mark is not None
    group = next(iter(group_state_for(canvas).groups.values()))
    group.items.append(mark)
    before = snapshot_canvas_state_for(canvas)
    extract_document_state(build_document_payload(before, 7))
    atom_label_service(canvas).add_or_update_atom_label(0, "N")
    assert mark in next(iter(group_state_for(canvas).groups.values())).items
    after = snapshot_canvas_state_for(canvas)
    extract_document_state(build_document_payload(after, 7))
    # Preserve the existing orphan-marker serialization rule, without assigning
    # a removed atom's radical/charge to the survivor as a new chemistry policy.
    assert after["marks"][0]["atom_id"] is None
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_partial_group_publication_failure_rolls_back_label_merge(drawing, monkeypatch):
    from chemvas.ui import history_commands

    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    before, stacks = snapshot_canvas_state_for(canvas), _stacks(canvas)
    restore = history_commands.restore_group_for
    calls = []

    def fail_after_restore(*args):
        restore(*args)
        calls.append(args[1])
        if len(calls) == 1:
            raise RuntimeError("injected group restore failure")

    with monkeypatch.context() as fault:
        fault.setattr(history_commands, "restore_group_for", fail_after_restore)
        with pytest.raises(RuntimeError, match="injected group restore failure"):
            atom_label_service(canvas).add_or_update_atom_label(0, "N")
    assert snapshot_canvas_state_for(canvas) == before
    assert _stacks(canvas) == stacks


@pytest.mark.parametrize(
    "route",
    [
        "sprout",
        "acetyl",
        "dimethyl",
        "regular",
        "chair",
        "benzene",
        "template_button",
        "hotkey",
    ],
)
def test_legacy_split_groups_refuse_growth_before_mutation(
    drawing, qt_errors, monkeypatch, route
):
    from tests.test_chair_fusion_workflows import _ring_button
    from tests.test_note_editing_workflows import _click, _tool

    window, canvas = drawing
    ids = _populate(canvas)
    add_bond_graphics_for(canvas, add_bond_for(canvas, ids[0], ids[2]))
    # Old partial groups remain a supported load state; do not migrate them.
    state = snapshot_canvas_state_for(canvas)
    restored = extract_document_state(build_document_payload(state, 7))
    restore_canvas_state_for(canvas, restored)
    before, stacks = snapshot_canvas_state_for(canvas), _stacks(canvas)
    build = canvas.services.structure.structure_build_service
    if route == "sprout":
        build.sprout_bond_from_atom(1, style="single", order=1)
    elif route == "acetyl":
        build.sprout_acetyl_from_atom(1)
    elif route == "dimethyl":
        build.sprout_dimethyl_from_atom(1)
    elif route == "regular":
        build.fuse_regular_ring_to_bond(0, 6)
    elif route == "chair":
        build.fuse_chair_to_bond(0)
    elif route == "benzene":
        build.fuse_benzene_to_bond(0)
    elif route == "template_button":
        _ring_button(window, "Cyclohexane (Chair)")
        _click(canvas, QPointF(-10, 0))
    else:
        _tool(window, "select")
        point = canvas.mapFromScene(QPointF(-10, 0))
        QTest.mouseMove(canvas.viewport(), point)
        monkeypatch.setattr(
            "chemvas.ui.hover.QCursor.pos", lambda: canvas.viewport().mapToGlobal(point)
        )
        QTest.keyClick(canvas, Qt.Key.Key_6)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == before
    assert _stacks(canvas) == stacks
    assert window.statusBar().currentMessage() == GROUP_CONNECTION_MESSAGE
    if route == "template_button":
        _tool(window, "select")
        assert snapshot_canvas_state_for(canvas) == before
        assert _stacks(canvas) == stacks
