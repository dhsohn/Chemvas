"""Actual Color controls preserve intent and independent annotation colors."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsTextItem, QToolButton

from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, visible_atom_item_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    active_tool_name_for_window,
    color_tool_for_window,
    services_for_window,
)
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from chemvas.ui.scene_item_state import mark_state_dict_for
from chemvas.ui.structure_mutation_access import add_atom_for
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _color_mode(window):
    QTest.qWait(1)
    action = window.ui_references.tool_actions["color"]
    button = next(
        b for b in window.findChildren(QToolButton) if b.defaultAction() is action
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.qWait(1)
    assert active_tool_name_for_window(window) == "color"


def _swatch(window, name):
    button = window.findChild(QToolButton, f"color_swatch_{name.lower()}")
    assert button is not None and button.isVisible()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.qWait(1)
    return button


def _click(canvas, point):
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(point)
    )
    QTest.qWait(1)


def _colors(canvas):
    return canvas.services.scene_operations.canvas_color_mutation_service


@pytest.mark.parametrize("direct", [True, False])
def test_no_swatch_never_repaints_a_loaded_colored_selection(drawing, tmp_path, direct):
    window, canvas = drawing
    atom_id = add_atom_for(canvas, "N", 0, 0)
    item = visible_atom_item_for(canvas, atom_id)
    _colors(canvas).apply_color_to_items([item], QColor("#008800"))
    actions = services_for_window(window).document_action_service
    path = tmp_path / "colored.chemvas"
    assert actions.save_canvas_to_path(window, str(path))
    assert actions.load_canvas_from_path(window, str(path))
    canvas = active_canvas_for_window(window)
    canvas.centerOn(0, 0)
    item = visible_atom_item_for(canvas, atom_id)
    item.setSelected(True)
    _color_mode(window)
    before = snapshot_canvas_state_for(canvas)
    selected = set(canvas.scene().selectedItems())
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    point = item.sceneBoundingRect().center() if direct else QPointF(110, 90)
    _click(canvas, point)
    after = snapshot_canvas_state_for(canvas)
    dirty_after = services_for_window(window).canvas_document_service.is_dirty(canvas)
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    assert after == before
    assert not dirty_after
    assert set(canvas.scene().selectedItems()) == selected
    history.verify_stack_snapshot(stacks)
    assert "choose a swatch" in window.statusBar().currentMessage()


def test_color_palette_reflects_only_the_actual_tool_color(drawing):
    window, canvas = drawing
    _color_mode(window)
    buttons = [
        b
        for b in window.findChildren(QToolButton)
        if b.objectName().startswith("color_swatch_")
    ]
    assert len(buttons) == 8
    assert all(b.isCheckable() for b in buttons)
    assert not any(b.isChecked() for b in buttons)
    for name in ("Red", "Blue", "Blue"):
        chosen = _swatch(window, name)
        assert [b for b in buttons if b.isChecked()] == [chosen]
        assert (
            color_tool_for_window(window).current_color
            in window.statusBar().currentMessage()
        )
        window.ui_references.tool_actions["select"].trigger()
        _color_mode(window)
        assert [b for b in buttons if b.isChecked()] == [chosen]
    assert not snapshot_canvas_state_for(canvas)["model"]["atoms"]
    second = services_for_window(window).canvas_document_service.new_canvas(window)
    assert second is not canvas
    _color_mode(window)
    assert not any(b.isChecked() for b in buttons)
    assert color_tool_for_window(window).current_color is None
    window.tab_references.canvas_tabs.setCurrentWidget(canvas)
    _color_mode(window)
    assert [b for b in buttons if b.isChecked()] == [chosen]


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "radical", "circled_plus", "circled_minus"]
)
@pytest.mark.parametrize("bound", [False, True])
def test_palette_colors_selected_marks_independently_with_one_undo(
    drawing, tmp_path, kind, bound
):
    window, canvas = drawing
    atom_id = add_atom_for(canvas, "N", 0, 0)
    point = QPointF(35, -25)
    item = (
        add_mark_for_atom_for(canvas, atom_id, point, kind=kind)
        if bound
        else add_mark_for(canvas, point, kind=kind)
    )
    item.setSelected(True)
    before = snapshot_canvas_state_for(canvas)
    atom_color = canvas.model.atoms[atom_id].color
    _color_mode(window)
    _swatch(window, "Blue")
    chosen = color_tool_for_window(window)._last_color
    assert item.data(1).get("color") == chosen
    actual = (
        item.defaultTextColor()
        if isinstance(item, QGraphicsTextItem)
        else (item.brush().color() if kind == "radical" else item.pen().color())
    )
    assert actual == QColor(chosen)
    assert canvas.model.atoms[atom_id].color == atom_color
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    # Changing the atom later never overwrites this mark's independent swatch.
    mark_before = mark_state_dict_for(canvas, item)
    _colors(canvas).apply_color_to_items(
        [visible_atom_item_for(canvas, atom_id)], QColor("#dd1122")
    )
    assert mark_state_dict_for(canvas, item) == mark_before
    history.undo()
    assert snapshot_canvas_state_for(canvas) == after
    session = canvas.services.document.canvas_document_session_service
    first, second = tmp_path / "colored.png", tmp_path / "reopened.png"
    session.export_figure(str(first), fmt="png")
    actions = services_for_window(window).document_action_service
    path = tmp_path / "colored-mark.chemvas"
    assert actions.save_canvas_to_path(window, str(path))
    assert actions.load_canvas_from_path(window, str(path))
    reopened = active_canvas_for_window(window)
    assert snapshot_canvas_state_for(reopened) == after
    reopened.services.document.canvas_document_session_service.export_figure(
        str(second), fmt="png"
    )
    assert not QImage(str(first)).isNull()
    assert QImage(str(first)) == QImage(str(second))


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "radical", "circled_plus", "circled_minus"]
)
@pytest.mark.parametrize("bound", [False, True])
def test_picked_swatch_direct_and_empty_click_target_marks(drawing, kind, bound):
    window, canvas = drawing
    atom_id = add_atom_for(canvas, "N", 0, 0)
    point = QPointF(35, -25)
    item = (
        add_mark_for_atom_for(canvas, atom_id, point, kind=kind)
        if bound
        else add_mark_for(canvas, point, kind=kind)
    )
    # A manually placed bound mark remains bound, but has no overlapping ink.
    move_item_for(canvas, item, 45, -25)
    _color_mode(window)
    _swatch(window, "Red")
    before = snapshot_canvas_state_for(canvas)
    _click(canvas, item.sceneBoundingRect().center())
    assert (
        mark_state_dict_for(canvas, item)["color"]
        == color_tool_for_window(window).current_color
    )
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    item.setSelected(True)
    _click(canvas, QPointF(130, 90))
    assert snapshot_canvas_state_for(canvas) == after
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "radical", "circled_plus", "circled_minus"]
)
@pytest.mark.parametrize("failure", ["false", "raise"])
def test_mark_color_publication_failure_restores_metadata_ink_and_history(
    drawing, monkeypatch, kind, failure
):
    _window, canvas = drawing
    first = add_mark_for(canvas, QPointF(20, 20), kind=kind)
    second = add_mark_for(canvas, QPointF(60, 20), kind=kind)
    second.setSelected(True)
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    before_state = [mark_state_dict_for(canvas, item) for item in (first, second)]

    def ink(item):
        return (
            (item.defaultTextColor(),)
            if isinstance(item, QGraphicsTextItem)
            else (item.pen(), item.brush())
        )

    before_ink = [ink(item) for item in (first, second)]

    def fail(_command):
        if failure == "false":
            return False
        raise RuntimeError("synthetic publication failure")

    with monkeypatch.context() as patch:
        patch.setattr(history, "push", fail)
        with pytest.raises(RuntimeError):
            _colors(canvas).apply_color_to_items([first, second], QColor("#123456"))
    assert snapshot_canvas_state_for(canvas) == before
    assert [
        mark_state_dict_for(canvas, item) for item in (first, second)
    ] == before_state
    assert [ink(item) for item in (first, second)] == before_ink
    assert second.isSelected()
    history.verify_stack_snapshot(stacks)
    _colors(canvas).apply_color_to_items([first, second], QColor("#123456"))
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before


def test_hidden_carbon_keeps_its_representation_and_explains_stored_color(drawing):
    window, canvas = drawing
    atom_id = add_atom_for(canvas, "C", 0, 0)
    item = atom_dots_for(canvas)[atom_id]
    before_brush = item.brush()
    _color_mode(window)
    _swatch(window, "Red")
    _click(canvas, QPointF(0, 0))
    assert (
        canvas.model.atoms[atom_id].color == color_tool_for_window(window)._last_color
    )
    assert item.brush() == before_brush
    assert "implicit carbon" in window.statusBar().currentMessage()
    assert "stored" in window.statusBar().currentMessage()


def test_deferred_palette_does_not_paint_a_different_canvas(drawing, monkeypatch):
    window, first = drawing
    documents = services_for_window(window).canvas_document_service
    second = documents.new_canvas(window)
    atom_id = add_atom_for(second, "N", 0, 0)
    visible_atom_item_for(second, atom_id).setSelected(True)
    window.tab_references.canvas_tabs.setCurrentWidget(first)
    _color_mode(window)
    pending = []
    # The same production callback used by an actual palette mouse click,
    # but retain its timer so the interleaving is deterministic.
    routing = services_for_window(window).tool_routing_service
    original = routing.apply_color_preset
    monkeypatch.setattr(
        routing,
        "apply_color_preset",
        lambda window, value: original(
            window,
            value,
            qtimer=SimpleNamespace(
                singleShot=lambda delay, callback: pending.append(callback)
            ),
        ),
    )
    _swatch(window, "Red")
    assert len(pending) == 1
    first_before = snapshot_canvas_state_for(first)
    first_stacks = first.services.history_service.capture_stack_snapshot()
    window.tab_references.canvas_tabs.setCurrentWidget(second)
    second_before = snapshot_canvas_state_for(second)
    second_stacks = second.services.history_service.capture_stack_snapshot()
    pending.pop()()
    second_after = snapshot_canvas_state_for(second)
    documents.mark_clean(second)
    assert snapshot_canvas_state_for(first) == first_before
    assert second_after == second_before
    first.services.history_service.verify_stack_snapshot(first_stacks)
    second.services.history_service.verify_stack_snapshot(second_stacks)
    assert color_tool_for_window(window).current_color is None
    assert "canvas changed" in window.statusBar().currentMessage()
    assert "choose a swatch" in window.statusBar().currentMessage()
