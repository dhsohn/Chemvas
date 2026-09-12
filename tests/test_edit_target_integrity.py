"""Named tools and visible captions target the edit the user actually chose."""

import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_scene_items_state import note_items_for, ring_items_for
from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.main_window_ports import (
    active_tool_name_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _tool(window, name):
    action = tool_action_for_window(window, name)
    button = next(
        button
        for button in window.findChildren(QToolButton)
        if button.defaultAction() is action
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _button(window, tooltip):
    button = next(
        button
        for button in window.findChildren(QToolButton)
        if button.toolTip() == tooltip
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def _click(canvas, pos):
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(pos)
    )
    QApplication.processEvents()


def _load(canvas, *, style="single", order=1, ring=False):
    atoms = (
        [
            {
                "id": i,
                "element": "C",
                "x": 20 * math.cos(i * math.pi / 3),
                "y": 20 * math.sin(i * math.pi / 3),
            }
            for i in range(6)
        ]
        if ring
        else [
            {"id": 0, "element": "C", "x": -20, "y": 0},
            {"id": 1, "element": "C", "x": 20, "y": 0},
        ]
    )
    bonds = (
        [{"a": i, "b": (i + 1) % 6, "order": 1} for i in range(6)]
        if ring
        else [{"a": 0, "b": 1, "order": order, "style": style}]
    )
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": atoms,
            "bonds": bonds,
        }
    )
    if ring:
        state["ring_fills"] = [
            {
                "points": [[atom["x"], atom["y"]] for atom in atoms],
                "atom_ids": list(range(6)),
                "color": "#ffffff",
                "alpha": 1.0,
            }
        ]
    canvas.services.document.canvas_document_session_service.apply_state(state)
    canvas.centerOn(0, 0)
    QApplication.processEvents()


@pytest.mark.parametrize("initial", [1, 2, 3])
@pytest.mark.parametrize(
    "requested,name", [(1, "Single"), (2, "Double"), (3, "Triple")]
)
def test_named_bond_button_applies_exact_order_and_repeated_click_is_noop(
    drawing, initial, requested, name
):
    window, canvas = drawing
    style = {1: "single", 2: "double", 3: "triple"}
    _load(canvas, style=style[initial], order=initial)
    _tool(window, "bond")
    _button(window, f"{name} bond ({requested})")
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    _click(canvas, QPointF())
    assert (canvas.model.bonds[0].style, canvas.model.bonds[0].order) == (
        style[requested],
        requested,
    )
    after = snapshot_canvas_state_for(canvas)
    if initial == requested:
        assert after == before
        history.verify_stack_snapshot(stacks)
    else:
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
    stacks = history.capture_stack_snapshot()
    _click(canvas, QPointF())
    assert snapshot_canvas_state_for(canvas) == after
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize(
    "style", ["double_center", "bold_in", "bold_center", "bold_out"]
)
def test_unsupported_dotted_overlay_gives_guidance_without_order_loss(drawing, style):
    window, canvas = drawing
    _load(canvas, style=style, order=2)
    _tool(window, "bond")
    _button(window, "Dotted bond")
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    _click(canvas, QPointF())
    assert "Dotted" in window.statusBar().currentMessage()
    assert "double" in window.statusBar().currentMessage()
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("tool", ["select", "delete"])
@pytest.mark.parametrize("zoom", [50, 100, 200, 400])
@pytest.mark.parametrize("point", ["center", "atom", "bond"])
def test_foreground_caption_receives_pointer_instead_of_underlying_molecule(
    drawing, tool, zoom, point
):
    window, canvas = drawing
    _load(canvas)
    note = note_controller_for_access(canvas).create_text_note(QPointF(-30, -6), "cat.")
    set_zoom_percent_for_window(window, zoom)
    canvas.centerOn(0, 0)
    _tool(window, tool)
    pos = {
        "center": note.sceneBoundingRect().center(),
        "atom": QPointF(-20, 0),
        "bond": QPointF(-10, 0),
    }[point]
    picked = canvas.services.selection.hit_testing_service.item_at_scene_pos(pos)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    _click(canvas, pos)
    assert snapshot_canvas_state_for(canvas)["model"] == before["model"]
    assert picked is note
    if tool == "select":
        assert (
            note in canvas.scene().selectedItems()
            or note in canvas.runtime_state.scene_items_state.selected_notes
        )
        assert not any(
            item.data(0) in {"atom", "bond"} for item in canvas.scene().selectedItems()
        )
        assert snapshot_canvas_state_for(canvas) == before
        history.verify_stack_snapshot(stacks)
    else:
        assert not note_items_for(canvas)
        after = snapshot_canvas_state_for(canvas)
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("prior_tool", ["delete", "bond", "select"])
def test_ring_fill_opens_as_safe_selection_command_and_preserves_fill_workflow(
    drawing, prior_tool
):
    window, canvas = drawing
    _load(canvas, ring=True)
    _tool(window, prior_tool)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    _tool(window, "ring_fill")
    action = tool_action_for_window(window, "ring_fill")
    _click(canvas, QPointF())
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)
    assert not action.isCheckable()
    assert active_tool_name_for_window(window) == "select"
    assert tool_action_for_window(window, "select").isChecked()
    assert (
        services_for_window(window).status_service.active_tool_status_text(window)
        == "Tool: Select"
    )
    assert "Ring Fill" in window.statusBar().currentMessage()
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    selected = set(canvas.scene().selectedItems())
    _tool(window, "ring_fill")
    assert set(canvas.scene().selectedItems()) == selected
    _button(window, "Ring Fill: Gray")
    assert len(ring_items_for(canvas)) == 1
    after = snapshot_canvas_state_for(canvas)
    assert after["ring_fills"][0]["color"] == "#d2d2d2"  # Existing 25% Gray tint.
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("foreground", [False, True])
def test_caption_pick_respects_direct_structure_ink_paint_order(drawing, foreground):
    _window, canvas = drawing
    _load(canvas)
    note = note_controller_for_access(canvas).create_text_note(QPointF(-30, -6), "cat.")
    note.setZValue(1 if foreground else -1)
    picked = canvas.services.selection.hit_testing_service.item_at_scene_pos(
        QPointF(-10, 0)
    )
    assert picked.data(0) == ("note" if foreground else "bond")


def test_note_guard_does_not_lift_background_image_above_a_bond(drawing):
    from chemvas.domain.document import image_state_from_bytes
    from chemvas.ui.scene_item_access import create_scene_item_from_state
    from tests.test_image_scene import image_bytes

    _window, canvas = drawing
    _load(canvas)
    image = create_scene_item_from_state(
        canvas, image_state_from_bytes(image_bytes(), x=-30, y=-10, width=60)
    )
    assert image.zValue() == -2
    picked = canvas.services.selection.hit_testing_service.item_at_scene_pos(QPointF())
    assert picked.data(0) == "bond"


@pytest.mark.parametrize("painted_dot", [False, True])
def test_visible_atom_ink_above_caption_remains_pickable(drawing, painted_dot):
    _window, canvas = drawing
    _load(canvas)
    if not painted_dot:
        state = snapshot_canvas_state_for(canvas)
        state["model"]["atoms"][0]["element"] = "O"
        canvas.services.document.canvas_document_session_service.apply_state(state)
    atom_item = visible_atom_item_for(canvas, 0)
    if painted_dot:
        atom_item.setBrush(QBrush(QColor("black")))
    note = note_controller_for_access(canvas).create_text_note(QPointF(-30, -6), "cat.")
    assert atom_item.zValue() > note.zValue()
    assert not atom_item.export_scene_bounding_rect().isEmpty()
    assert (
        canvas.services.selection.hit_testing_service.item_at_scene_pos(QPointF(-20, 0))
        is atom_item
    )


def test_edit_handle_above_caption_keeps_priority(drawing):
    _window, canvas = drawing
    arrow = add_arrow_for(canvas, QPointF(-20, 0), QPointF(20, 0), "arrow")
    note = note_controller_for_access(canvas).create_text_note(QPointF(-30, -6), "cat.")
    canvas.services.handles.handle_overlay_service.show_endpoint_handles(arrow)
    handle = active_handles_for(canvas)[0]
    assert handle.zValue() > note.zValue()
    pos = handle.sceneBoundingRect().center()
    assert (
        canvas.services.selection.hit_testing_service.item_at_scene_pos(pos) is handle
    )


@pytest.mark.parametrize(
    "requested,name", [(1, "Single"), (2, "Double"), (3, "Triple")]
)
def test_named_bond_buttons_keep_new_bond_drawing_and_undo(drawing, requested, name):
    window, canvas = drawing
    _tool(window, "bond")
    _button(window, f"{name} bond ({requested})")
    before = snapshot_canvas_state_for(canvas)
    start, end = (
        canvas.mapFromScene(QPointF(-20, 0)),
        canvas.mapFromScene(QPointF(20, 0)),
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    (bond,) = canvas.model.bonds
    assert (bond.style, bond.order) == (
        {1: "single", 2: "double", 3: "triple"}[requested],
        requested,
    )
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize(
    "style,expected",
    [
        ("double", "dotted_double"),
        ("double_outer", "dotted_double_outer"),
        ("dotted_double", "dotted_double"),
        ("dotted_double_outer", "dotted_double_outer"),
    ],
)
def test_supported_dotted_overlays_keep_order_and_repeated_click_is_noop(
    drawing, style, expected
):
    window, canvas = drawing
    _load(canvas, style=style, order=2)
    _tool(window, "bond")
    _button(window, "Dotted bond")
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    _click(canvas, QPointF())
    assert (canvas.model.bonds[0].style, canvas.model.bonds[0].order) == (expected, 2)
    after = snapshot_canvas_state_for(canvas)
    if style != expected:
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
    stacks = history.capture_stack_snapshot()
    _click(canvas, QPointF())
    assert snapshot_canvas_state_for(canvas) == after
    history.verify_stack_snapshot(stacks)
