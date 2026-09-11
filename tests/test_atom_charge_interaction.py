from __future__ import annotations

from itertools import combinations
from unittest import mock

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document
from chemvas.domain.document import deserialize_model_state
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_scene_items_state import mark_items_for
from chemvas.ui.input_view_access import set_zoom_for
from chemvas.ui.mark_item_access import mark_center_for
from chemvas.ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(700, 500)
    view.show()
    app.processEvents()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()


def load(canvas, element="N", *, order=1, zoom=4):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": -20, "y": 0},
                {"id": 1, "element": "C", "x": 0, "y": 0},
                {"id": 2, "element": element, "x": 20, "y": 0},
            ],
            "bonds": [
                {"a": 0, "b": 1, "order": 1},
                {"a": 1, "b": 2, "order": order},
            ],
        }
    )
    canvas.services.document.canvas_document_session_service.apply_state(state)
    set_zoom_for(canvas, zoom)
    canvas.centerOn(10, 0)
    QApplication.processEvents()


def snapshot(canvas):
    return canvas.services.document.canvas_document_session_service.snapshot_state()


def shortcut(canvas, text, *, pos=None):
    pos = QPointF(20, 0) if pos is None else pos
    canvas.services.hover.update_hover_highlight(pos)
    event = QKeyEvent(
        QEvent.Type.KeyPress, ord(text), Qt.KeyboardModifier.NoModifier, text
    )
    assert canvas.services.input.chemdraw_shortcut_service.handle_shortcut(event)


def click(canvas, pos):
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        canvas.mapFromScene(pos),
    )
    QApplication.processEvents()


def assert_one_step_undo(canvas, before, after):
    canvas.services.history_service.undo()
    assert snapshot(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot(canvas) == after


@pytest.mark.parametrize("element,x", [("O", 10), ("N", 12), ("Cl", 10)])
@pytest.mark.parametrize("order", [1, 2])
@pytest.mark.parametrize("zoom", [0.5, 4])
def test_visible_bond_is_not_hidden_by_label_input_box(canvas, element, x, order, zoom):
    load(canvas, element, order=order, zoom=zoom)
    pos = QPointF(x, 0)
    item = canvas.services.selection.hit_testing_service.item_at_scene_pos(pos)
    assert (item.data(0), item.data(1)) == ("bond", 1)
    preferred = canvas.services.selection.selection_controller.preferred_structure_hit_at_scene_pos(
        pos
    )
    assert (preferred.kind, preferred.id) == ("bond", 1)
    atom = canvas.services.selection.hit_testing_service.item_at_scene_pos(
        QPointF(20, 0)
    )
    assert (atom.data(0), atom.data(1)) == ("atom", 2)


@pytest.mark.parametrize("tool", ["select", "color", "delete"])
def test_real_pointer_edit_targets_bond_and_undo_keeps_heteroatom(canvas, tool):
    load(canvas, "O")
    before = snapshot(canvas)
    canvas.services.input.tool_mode_controller.set_tool(tool)
    if tool == "color":
        canvas.services.tool_controller.tools["color"].set_color("#336699")
    click(canvas, QPointF(10, 0))
    assert len(canvas.model.atoms) == 3
    if tool == "select":
        selected = canvas.scene().selectedItems()
        assert any(item.data(0) == "bond" and item.data(1) == 1 for item in selected)
        assert not any(item.data(0) == "atom" for item in selected)
    elif tool == "color":
        assert canvas.model.bonds[1].color == "#336699"
        assert canvas.model.atoms[2].color == "#000000"
        assert_one_step_undo(canvas, before, snapshot(canvas))
    else:
        assert canvas.model.bonds[1] is None
        assert_one_step_undo(canvas, before, snapshot(canvas))


def test_bond_shortcut_changes_order_without_sprouting_acetyl(canvas):
    load(canvas, "O")
    before = snapshot(canvas)
    shortcut(canvas, "2", pos=QPointF(10, 0))
    assert len(canvas.model.atoms) == 3
    assert canvas.model.bonds[1].order == 2
    assert_one_step_undo(canvas, before, snapshot(canvas))


@pytest.mark.parametrize("element", ["CO2Me", "NH2", "NH2-stacked", "Cl"])
def test_full_label_ink_stays_pickable_without_changing_export_geometry(
    canvas, element
):
    load(canvas, "NH2" if element == "NH2-stacked" else element)
    item = atom_items_for(canvas)[2]
    if element == "NH2-stacked":
        item.set_stack_anchor("N", hydrogens_below=True)
        item.setPos(QPointF(20, 0) - item.anchor_center())
    before = item.export_scene_bounding_rect(), item.glyph_path()
    ink = item.glyph_path()
    for polygon in ink.toSubpathPolygons():
        point = polygon.boundingRect().center()
        assert item.contains(point)
        picked = canvas.services.selection.hit_testing_service.item_at_scene_pos(
            item.mapToScene(point)
        )
        assert picked is item
    assert (item.export_scene_bounding_rect(), item.glyph_path()) == before


@pytest.mark.parametrize("element", ["C", "N"])
@pytest.mark.parametrize("tool", ["select", "delete"])
def test_bound_charge_can_be_picked_without_editing_its_atom(canvas, element, tool):
    load(canvas, element)
    add_mark_for_atom_for(canvas, 2, QPointF(20, 0), kind="plus")
    before = snapshot(canvas)
    mark = mark_items_for(canvas)[0]
    center = mark_center_for(canvas, mark)
    canvas.services.input.tool_mode_controller.set_tool(tool)
    click(canvas, center)
    assert len(canvas.model.atoms) == 3
    if tool == "select":
        assert mark.isSelected()
        assert not any(
            item.data(0) in {"atom", "bond"} for item in canvas.scene().selectedItems()
        )
    else:
        assert not mark_items_for(canvas)
        assert canvas.model.atom_annotations == {}
        assert_one_step_undo(canvas, before, snapshot(canvas))


@pytest.mark.parametrize("text", ["++++++", "------", "+-", "-+"])
def test_charge_shortcuts_are_visible_and_each_step_is_exactly_undoable(canvas, text):
    load(canvas)
    for char in text:
        before = snapshot(canvas)
        shortcut(canvas, char)
        after = snapshot(canvas)
        assert_one_step_undo(canvas, before, after)
    assert canvas.model.atom_annotations.get(2, {}).get(
        "formal_charge", 0
    ) == text.count("+") - text.count("-")
    assert len(mark_items_for(canvas)) == abs(text.count("+") - text.count("-"))
    rects = [
        item.mapToScene(item.glyph_path()).boundingRect()
        for item in mark_items_for(canvas)
    ]
    assert all(not a.intersects(b) for a, b in combinations(rects, 2))


def test_charge_cancels_last_opposite_mark_preserving_manual_radical_and_free_marks(
    canvas,
):
    load(canvas)
    first = add_mark_for_atom_for(canvas, 2, QPointF(10, -10), kind="minus")
    radical = add_mark_for_atom_for(canvas, 2, QPointF(30, 10), kind="radical")
    last = add_mark_for_atom_for(canvas, 2, QPointF(30, -10), kind="minus")
    plus = add_mark_for_atom_for(canvas, 2, QPointF(10, 10), kind="plus")
    free = add_mark_for(canvas, QPointF(70, 20), kind="minus")
    before = snapshot(canvas)
    shortcut(canvas, "+")
    assert mark_items_for(canvas) == [first, radical, plus, free]
    assert last.scene() is None
    assert_one_step_undo(canvas, before, snapshot(canvas))
    assert deserialize_model_state(snapshot(canvas)["model"]).atom_annotations == {
        2: {"radical_electrons": 1}
    }


@pytest.mark.parametrize("has_opposite", [False, True])
def test_failed_charge_history_publication_restores_exact_state(canvas, has_opposite):
    load(canvas)
    if has_opposite:
        add_mark_for_atom_for(canvas, 2, QPointF(20, 0), kind="minus")
    before = snapshot(canvas)
    items = list(mark_items_for(canvas))
    with mock.patch.object(
        canvas.services.history_service,
        "push",
        side_effect=RuntimeError("publication failed"),
    ):
        with pytest.raises(RuntimeError, match="publication failed"):
            shortcut(canvas, "+")
    assert snapshot(canvas) == before
    assert mark_items_for(canvas) == items


@pytest.mark.parametrize("element", ["C", "N"])
def test_select_then_drag_bound_charge_preserves_atom_and_exact_undo(canvas, element):
    load(canvas, element)
    add_mark_for_atom_for(canvas, 2, QPointF(20, 0), kind="plus")
    mark = mark_items_for(canvas)[0]
    center = mark_center_for(canvas, mark)
    before = snapshot(canvas)
    canvas.services.input.tool_mode_controller.set_tool("select")
    click(canvas, center)
    assert mark.isSelected()
    start = canvas.mapFromScene(center)
    end = (
        start + canvas.mapFromScene(QPointF(25, 0)) - canvas.mapFromScene(QPointF(0, 0))
    )
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    QTest.mouseMove(canvas.viewport(), end, delay=30)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
    )
    QApplication.processEvents()
    assert mark_center_for(canvas, mark).x() == pytest.approx(center.x() + 25)
    assert snapshot(canvas)["model"] == before["model"]
    assert mark.data(1)["atom_id"] == 2
    assert_one_step_undo(canvas, before, snapshot(canvas))


@pytest.mark.parametrize("element", ["C", "O", "N", "NH2"])
@pytest.mark.parametrize("zoom", [0.5, 4])
def test_mark_preview_and_click_bind_at_own_charge_position_but_keep_free_symbols(
    canvas, element, zoom
):
    load(canvas, element, zoom=zoom)
    marks = canvas.services.scene_decoration.canvas_mark_scene_service
    pos = marks.mark_center_for_pointer(QPointF(20, 0), 2, kind="minus")
    canvas.services.input.tool_mode_controller.set_mark_kind("minus")
    canvas.services.hover.update_hover_highlight(pos)
    assert hover_state_for(canvas).atom_id == 2
    before = snapshot(canvas)
    click(canvas, pos)
    assert mark_items_for(canvas)[0].data(1)["atom_id"] == 2
    assert canvas.model.atom_annotations[2]["formal_charge"] == -1
    assert_one_step_undo(canvas, before, snapshot(canvas))
    free_pos = QPointF(100, 100)
    canvas.services.hover.update_hover_highlight(free_pos)
    assert hover_state_for(canvas).atom_id is None
    click(canvas, free_pos)
    assert mark_items_for(canvas)[-1].data(1)["atom_id"] is None


@pytest.mark.parametrize("kind,text", [("circled_minus", "+"), ("circled_plus", "-")])
def test_shortcut_cancels_circled_charge_in_one_undoable_step(canvas, kind, text):
    load(canvas)
    add_mark_for_atom_for(canvas, 2, QPointF(30, -10), kind=kind)
    before = snapshot(canvas)
    shortcut(canvas, text)
    assert not mark_items_for(canvas)
    assert canvas.model.atom_annotations == {}
    assert_one_step_undo(canvas, before, snapshot(canvas))


def test_charge_layout_survives_save_reopen_without_reflowing_manual_marks(
    canvas, tmp_path
):
    load(canvas)
    owner = canvas.services.scene_decoration.canvas_mark_scene_service
    expected = owner.mark_center_for_pointer(QPointF(20, 0), 2, kind="plus")
    shortcut(canvas, "+")
    assert mark_center_for(canvas, mark_items_for(canvas)[0]) == expected
    manual = add_mark_for_atom_for(canvas, 2, QPointF(10, 10), kind="radical")
    manual_state = dict(manual.data(1))
    for _ in range(5):
        shortcut(canvas, "+")
    assert manual.data(1) == manual_state
    before = snapshot(canvas)
    path = tmp_path / "charges.chemvas"
    session = canvas.services.document.canvas_document_session_service
    assert session.save_to_file(str(path)) == []
    session.apply_state(read_document(path).state)
    assert snapshot(canvas) == before


def test_mark_preview_and_click_bind_at_long_alias_glyph_edge(canvas):
    load(canvas, "CO2Me")
    label = atom_items_for(canvas)[2]
    rect = label.glyph_path().boundingRect()
    pos = label.mapToScene(QPointF(rect.right() - 0.1, rect.center().y()))
    assert pos.x() > 30
    canvas.services.input.tool_mode_controller.set_mark_kind("minus")
    canvas.services.hover.update_hover_highlight(pos)
    assert hover_state_for(canvas).atom_id == 2
    click(canvas, pos)
    assert mark_items_for(canvas)[0].data(1)["atom_id"] == 2
    assert canvas.model.atom_annotations[2]["formal_charge"] == -1


@pytest.mark.parametrize("has_opposite", [False, True])
def test_charge_shortcut_rejects_disabled_history_and_restores_exact_state(
    canvas, has_opposite
):
    load(canvas)
    if has_opposite:
        add_mark_for_atom_for(canvas, 2, QPointF(20, 0), kind="minus")
    history = canvas.services.history_service
    history.state.enabled = False
    before = snapshot(canvas)
    items = list(mark_items_for(canvas))
    stacks = history.capture_stack_snapshot()
    with pytest.raises(RuntimeError, match="record charge"):
        shortcut(canvas, "+")
    assert snapshot(canvas) == before
    assert mark_items_for(canvas) == items
    history.verify_stack_snapshot(stacks)
