"""Cosmetic bond edits must not discard explicit unknown double-bond stereo."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import Bond
from chemvas.ui.bond_tool import BondTool
from chemvas.ui.canvas_callback_state import CanvasCallbackState
from chemvas.ui.canvas_chemdraw_shortcut_service import CanvasChemdrawShortcutService
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import services_for_window
from chemvas.ui.structure_mutation_access import add_bond_between_points_for
from tests.test_canvas_chemdraw_shortcut_service import _FakeKeyEvent
from tests.test_caps_lock_shortcuts import pointer as pointer
from tests.test_edit_target_integrity import _button, _click, _load, _tool
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing
from tests.test_structure_bond_build_service import _builder_for
from tests.test_structure_build_service import _FakeCanvas


def _target():
    notice = Mock()
    canvas = SimpleNamespace(
        model=SimpleNamespace(bonds=[Bond(0, 1, 2, style="double_either")]),
        runtime_state=SimpleNamespace(
            callback_state=CanvasCallbackState(error=notice),
            tool_settings_state=CanvasToolSettingsState(),
        ),
    )
    transform = Mock()
    return canvas, transform, notice


@pytest.mark.parametrize("style", ["bold_in", "bold_center", "bold_out", "dotted"])
def test_bond_tool_refuses_cosmetic_replacement_of_unknown_double(style):
    canvas, context, notice = _target()
    canvas.runtime_state.tool_settings_state.active_bond_style = style
    tool = BondTool(canvas, context=context)
    assert tool._apply_active_style_to_bond(0)
    context.apply_bond_style.assert_not_called()
    context.cycle_bond_style.assert_not_called()
    notice.assert_called_once()
    assert "Double" in notice.call_args.args[0]
    assert (canvas.model.bonds[0].style, canvas.model.bonds[0].order) == (
        "double_either",
        2,
    )


@pytest.mark.parametrize(
    "text,shift",
    [
        ("b", False),
        ("B", True),
        ("d", False),
        ("D", True),
        ("l", False),
        ("c", False),
        ("r", False),
    ],
)
def test_bond_shortcuts_refuse_cosmetic_replacement_of_unknown_double(text, shift):
    canvas, transform, notice = _target()
    service = CanvasChemdrawShortcutService(
        canvas,
        scene_transform_controller=transform,
        tool_mode_controller=Mock(),
        mark_scene_service=None,
    )
    event = _FakeKeyEvent(
        getattr(Qt.Key, f"Key_{text.upper()}"),
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier,
        text=text,
    )
    assert service.handle_bond_hotkey(event, 0)
    transform.apply_bond_style.assert_not_called()
    notice.assert_called_once()
    assert "Double" in notice.call_args.args[0]


@pytest.mark.parametrize(
    "style,order",
    [
        ("bold_in", 1),
        ("bold_out", 2),
        ("dotted", 1),
        ("dotted_double", 2),
        ("double_center", 2),
        ("double_outer", 2),
    ],
)
def test_draw_over_existing_unknown_double_refuses_before_recorded_mutation(
    style, order
):
    canvas = _FakeCanvas()
    builder = _builder_for(canvas)
    builder.add_bond_between_points(QPointF(0, 0), QPointF(10, 0), "double", 2)
    canvas.model.bonds[0].style = "double_either"
    canvas.services.selection.hit_testing_service.find_atom_near = Mock(
        side_effect=[0, 1]
    )
    canvas.runtime_state.callback_state = CanvasCallbackState(error=Mock())
    builder = _builder_for(canvas)
    builder.committer.begin_recorded_change = Mock(
        side_effect=AssertionError("must preflight")
    )
    before = (canvas.model.bonds[0].style, canvas.model.bonds[0].order)
    assert (
        builder.add_bond_between_points(QPointF(0, 0), QPointF(10, 0), style, order)
        is None
    )
    assert (canvas.model.bonds[0].style, canvas.model.bonds[0].order) == before
    builder.committer.begin_recorded_change.assert_not_called()
    canvas.runtime_state.callback_state.error.assert_called_once()


@pytest.mark.parametrize(
    "text,style,order",
    [
        ("1", "single", 1),
        ("2", "double", 2),
        ("3", "triple", 3),
        ("w", "wedge", 1),
        ("h", "hash", 1),
    ],
)
def test_explicit_bond_kind_shortcuts_remain_available(text, style, order):
    canvas, transform, notice = _target()
    service = CanvasChemdrawShortcutService(
        canvas,
        scene_transform_controller=transform,
        tool_mode_controller=Mock(),
        mark_scene_service=None,
    )
    assert service.handle_bond_hotkey(
        _FakeKeyEvent(getattr(Qt.Key, f"Key_{text.upper()}"), text=text), 0
    )
    transform.apply_bond_style.assert_called_once_with(0, style, order)
    notice.assert_not_called()


def _unknown_with_redo(drawing, tmp_path):
    window, canvas = drawing
    _load(canvas, style="double_either", order=2)
    canvas.services.scene_operations.scene_transform_controller.apply_bond_style(
        0, "single", 1
    )
    redo_state = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert services_for_window(window).document_action_service.save_canvas_to_path(
        window, str(tmp_path / "unknown-double.chemvas")
    )
    assert not window.isWindowModified()
    return (
        snapshot_canvas_state_for(canvas),
        history.capture_stack_snapshot(),
        redo_state,
    )


def _assert_refused(drawing, before, stacks, redo_state):
    window, canvas = drawing
    assert "Choose Double (2)" in window.statusBar().currentMessage()
    assert snapshot_canvas_state_for(canvas) == before
    assert not window.isWindowModified()
    history = canvas.services.history_service
    history.verify_stack_snapshot(stacks)
    history.redo()
    assert snapshot_canvas_state_for(canvas) == redo_state
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("tooltip", ["Bold bond (B)", "Dotted bond"])
def test_actual_toolbar_rejection_preserves_document_and_existing_redo(
    drawing, tmp_path, tooltip
):
    before, stacks, redo_state = _unknown_with_redo(drawing, tmp_path)
    window, canvas = drawing
    _tool(window, "bond")
    _button(window, tooltip)
    _click(canvas, QPointF())
    _assert_refused(drawing, before, stacks, redo_state)


@pytest.mark.parametrize(
    "key,shift",
    [
        ("B", False),
        ("B", True),
        ("D", False),
        ("D", True),
        ("L", False),
        ("C", False),
        ("R", False),
    ],
)
def test_actual_shortcut_rejection_preserves_document_and_existing_redo(
    drawing, tmp_path, pointer, key, shift
):
    before, stacks, redo_state = _unknown_with_redo(drawing, tmp_path)
    window, canvas = drawing
    _tool(window, "select")
    canvas.setFocus()
    # Reuse the existing injected cursor source: Wayland does not promise
    # pointer warping. Hit testing and QTest key dispatch remain real.
    pointer(canvas, QPointF())
    assert hover_state_for(canvas).bond_id == 0
    QTest.keyClick(
        canvas,
        getattr(Qt.Key, f"Key_{key}"),
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier,
    )
    QApplication.processEvents()
    _assert_refused(drawing, before, stacks, redo_state)


@pytest.mark.parametrize(
    "style,order",
    [
        ("bold_in", 1),
        ("bold_center", 2),
        ("bold_out", 2),
        ("dotted", 1),
        ("dotted_double", 2),
        ("dotted_double_outer", 2),
        ("double_center", 2),
        ("double_outer", 2),
    ],
)
def test_actual_draw_over_rejection_preserves_document_and_existing_redo(
    drawing, tmp_path, style, order
):
    before, stacks, redo_state = _unknown_with_redo(drawing, tmp_path)
    _window, canvas = drawing
    assert (
        add_bond_between_points_for(
            canvas, QPointF(-20, 0), QPointF(20, 0), style=style, order=order
        )
        is None
    )
    _assert_refused(drawing, before, stacks, redo_state)


@pytest.mark.parametrize("name,order", [("Single", 1), ("Double", 2), ("Triple", 3)])
def test_actual_explicit_bond_button_can_resolve_unknown_with_exact_undo(
    drawing, name, order
):
    window, canvas = drawing
    _load(canvas, style="double_either", order=2)
    _tool(window, "bond")
    _button(window, f"{name} bond ({order})")
    before = snapshot_canvas_state_for(canvas)
    _click(canvas, QPointF())
    assert (canvas.model.bonds[0].style, canvas.model.bonds[0].order) == (
        name.lower(),
        order,
    )
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
