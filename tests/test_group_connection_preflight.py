from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

"""Cross-group connections are refused before Qt edits or atom-label merges."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from chemvas.domain.document.state import (
    build_document_payload,
    extract_document_state,
)
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.molecule.structure_mutation_access import (
    add_bond_between_points_for,
    add_bond_for,
)
from chemvas.ui.scene.scene_group_operations import (
    GROUP_CONNECTION_MESSAGE,
    group_selection_for,
)
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import qt_errors as qt_errors


def _populate(canvas, *, overlap=False, grouping="different"):
    points = [(0, 0), (-20, 0), (0 if overlap else 40, 0), (60, 0)]
    ids = [
        canvas.services.canvas_atom_mutation_service.add_atom("C", x, y)
        for x, y in points
    ]
    for first, second in ((ids[0], ids[1]), (ids[2], ids[3])):
        canvas.bond_renderer.add_bond_graphics(add_bond_for(canvas, first, second))
    notes = [
        canvas.services.tool_controller.context.create_text_note(QPointF(x, 40), text)
        for x, text in ((-20, "first"), (40, "second"))
    ]
    if grouping == "same":
        register_group_for(
            canvas, set(ids), [require_scene_record_id(item) for item in notes]
        )
    else:
        register_group_for(
            canvas, set(ids[:2]), [require_scene_record_id(item) for item in notes[:1]]
        )
        if grouping == "different":
            register_group_for(
                canvas,
                set(ids[2:]),
                [require_scene_record_id(item) for item in notes[1:]],
            )
    return ids


def _stacks(canvas):
    history = canvas.services.history_service
    return list(history.state.history), list(history.state.redo_stack)


def _join(canvas, route):
    if route == "builder":
        return add_bond_between_points_for(
            canvas, QPointF(0, 0), QPointF(40, 0), "single", 1
        )
    canvas.services.tool_mode_controller.set_tool("bond")
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
    before, stacks = (
        canvas.services.canvas_document_session_service.snapshot_state(),
        _stacks(canvas),
    )
    _join(canvas, route)
    assert not qt_errors
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert _stacks(canvas) == stacks
    assert window.statusBar().currentMessage() == GROUP_CONNECTION_MESSAGE
    if route == "mouse":
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            pos=canvas.mapFromScene(QPointF(40, 0)),
        )
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        assert _stacks(canvas) == stacks
    select_all_scene_items_for(canvas)
    assert group_selection_for(canvas)
    regrouped = canvas.services.canvas_document_session_service.snapshot_state()
    _join(canvas, route)
    assert not qt_errors
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert len([bond for bond in canvas.model.bonds if bond is not None]) == 3
    assert len(canvas.runtime_state.group_state.groups) == 1
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == regrouped
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


def test_cross_group_overlapping_label_merge_refuses_before_element_or_graphics(
    drawing,
):
    window, canvas = drawing
    ids = _populate(canvas, overlap=True)
    before, stacks = (
        canvas.services.canvas_document_session_service.snapshot_state(),
        _stacks(canvas),
    )
    original_items = set(canvas.scene().items())
    canvas.services.atom_label_service.add_or_update_atom_label(ids[0], "N")
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert set(canvas.scene().items()) == original_items
    assert _stacks(canvas) == stacks
    assert window.statusBar().currentMessage() == GROUP_CONNECTION_MESSAGE


@pytest.mark.parametrize("text,allow_merge", [("C", True), ("", True), ("N", False)])
def test_nonmerging_label_edits_are_not_rejected(drawing, text, allow_merge):
    window, canvas = drawing
    ids = _populate(canvas, overlap=True)
    groups_before = canvas.services.canvas_document_session_service.snapshot_state()[
        "groups"
    ]
    canvas.services.atom_label_service.add_or_update_atom_label(
        ids[0], text, allow_merge=allow_merge
    )
    assert set(canvas.model.atoms) == set(ids)
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()["groups"]
        == groups_before
    )
    assert window.statusBar().currentMessage() != GROUP_CONNECTION_MESSAGE


@pytest.mark.parametrize("grouping", ["same", "one"])
def test_same_group_or_ungrouped_component_connection_is_allowed(drawing, grouping):
    _window, canvas = drawing
    ids = _populate(canvas, grouping=grouping)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    assert _join(canvas, "builder") == (ids[0], ids[2])
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert len(canvas.runtime_state.group_state.groups) == 1
    assert next(iter(canvas.runtime_state.group_state.groups.values())).atom_ids == set(
        ids
    )
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


def test_existing_bond_style_change_does_not_require_regroup(drawing):
    _window, canvas = drawing
    _populate(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    assert add_bond_between_points_for(
        canvas, QPointF(0, 0), QPointF(-20, 0), "double", 2
    ) == (0, 1)
    assert canvas.model.bonds[0].order == 2
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


@pytest.mark.parametrize("grouping,survivor", [("same", 0), ("one", 0), ("one", 2)])
def test_allowed_label_merge_preserves_group_membership_and_history(
    drawing, grouping, survivor
):
    _window, canvas = drawing
    ids = _populate(canvas, overlap=True, grouping=grouping)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    old_group = next(iter(canvas.runtime_state.group_state.groups.values()))
    original_items = list(old_group.item_ids)
    canvas.services.atom_label_service.add_or_update_atom_label(ids[survivor], "N")
    remaining = set(ids) - {ids[2 if survivor == 0 else 0]}
    assert set(canvas.model.atoms) == remaining
    group = next(iter(canvas.runtime_state.group_state.groups.values()))
    assert group.atom_ids == remaining
    assert group.item_ids == original_items
    after = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


@pytest.mark.parametrize("failure", ["exception", "refusal"])
def test_label_merge_publication_failure_restores_group_and_previous_redo(
    drawing, monkeypatch, failure
):
    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    add_bond_between_points_for(canvas, QPointF(100, 80), QPointF(120, 80), "single", 1)
    history = canvas.services.history_service
    history.undo()
    before, stacks = (
        canvas.services.canvas_document_session_service.snapshot_state(),
        _stacks(canvas),
    )
    with monkeypatch.context() as fault:

        def reject(_command):
            if failure == "exception":
                raise RuntimeError("injected history publication failure")
            return False

        fault.setattr(history, "push", reject)
        with pytest.raises((RuntimeError, ValueError)):
            canvas.services.atom_label_service.add_or_update_atom_label(0, "N")
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert _stacks(canvas) == stacks
    canvas.services.atom_label_service.add_or_update_atom_label(0, "N")
    assert next(iter(canvas.runtime_state.group_state.groups.values())).atom_ids == {
        0,
        1,
        3,
    }
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


def test_disabled_history_still_applies_label_merge_and_group_update(drawing):
    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    history = canvas.services.history_service
    history.set_enabled(False)
    stacks = _stacks(canvas)
    canvas.services.atom_label_service.add_or_update_atom_label(0, "N")
    assert set(canvas.model.atoms) == {0, 1, 3}
    assert next(iter(canvas.runtime_state.group_state.groups.values())).atom_ids == {
        0,
        1,
        3,
    }
    assert _stacks(canvas) == stacks
    history.set_enabled(True)


def test_explicit_group_mark_survives_merge_as_valid_document_item(drawing):
    from chemvas.ui.scene.scene_decoration_access import materialize_mark_for_atom_for

    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    mark = materialize_mark_for_atom_for(canvas, 2, QPointF(5, 5), kind="radical")
    assert mark is not None
    group = next(iter(canvas.runtime_state.group_state.groups.values()))
    group.item_ids.append(require_scene_record_id(mark))
    before = canvas.services.canvas_document_session_service.snapshot_state()
    extract_document_state(build_document_payload(before, 7))
    canvas.services.atom_label_service.add_or_update_atom_label(0, "N")
    assert (
        mark.data(3)
        in next(iter(canvas.runtime_state.group_state.groups.values())).item_ids
    )
    after = canvas.services.canvas_document_session_service.snapshot_state()
    extract_document_state(build_document_payload(after, 7))
    # Preserve the existing orphan-marker serialization rule, without assigning
    # a removed atom's radical/charge to the survivor as a new chemistry policy.
    assert after["marks"][0]["atom_id"] is None
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


def test_partial_group_publication_failure_rolls_back_label_merge(drawing, monkeypatch):
    from chemvas.ui.history import history_operations as history_commands

    _window, canvas = drawing
    _populate(canvas, overlap=True, grouping="same")
    before, stacks = (
        canvas.services.canvas_document_session_service.snapshot_state(),
        _stacks(canvas),
    )
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
            canvas.services.atom_label_service.add_or_update_atom_label(0, "N")
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
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
    from tests.gui_workflow_support import _click, _tool
    from tests.test_chair_fusion_workflows import _ring_button

    window, canvas = drawing
    ids = _populate(canvas)
    canvas.bond_renderer.add_bond_graphics(add_bond_for(canvas, ids[0], ids[2]))
    # Old partial groups remain a supported load state; do not migrate them.
    state = canvas.services.canvas_document_session_service.snapshot_state()
    restored = extract_document_state(build_document_payload(state, 7))
    canvas.services.canvas_document_session_service.restore_state(restored)
    before, stacks = (
        canvas.services.canvas_document_session_service.snapshot_state(),
        _stacks(canvas),
    )
    build = canvas.services.structure_build_service
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
            "chemvas.ui.tools.hover.QCursor.pos",
            lambda: canvas.viewport().mapToGlobal(point),
        )
        QTest.keyClick(canvas, Qt.Key.Key_6)
    assert not qt_errors
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert _stacks(canvas) == stacks
    assert window.statusBar().currentMessage() == GROUP_CONNECTION_MESSAGE
    if route == "template_button":
        _tool(window, "select")
        assert (
            canvas.services.canvas_document_session_service.snapshot_state() == before
        )
        assert _stacks(canvas) == stacks
