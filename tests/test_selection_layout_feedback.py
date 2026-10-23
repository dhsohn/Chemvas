from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.scene.scene_group_operations import group_selection_for
from chemvas.ui.window.main_window_ports import active_canvas_for_window


@pytest.fixture
def editor():
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    canvas.services.tool_mode_controller.set_tool("select")
    yield app, window, canvas
    window.services.canvas_document_service.mark_clean(canvas)
    window.close()
    window.deleteLater()
    app.processEvents()


def select(editor, *items):
    app, window, canvas = editor
    canvas.scene().clearSelection()
    for item in items:
        item.setSelected(True)
    app.processEvents()
    return window.services.status_service.status_context_texts()["selection"]


def assert_controls(window, count):
    controls = window.ui_references.layout_controls
    assert len(controls) == 16  # Eight toolbar buttons and eight menu actions.
    for control, minimum, hint in controls:
        assert control.isEnabled() == (count >= minimum)
        if count < minimum:
            assert f"at least {minimum} objects ({count} selected)" in control.toolTip()
        else:
            assert control.toolTip() == hint


def test_molecule_partial_selection_and_layout_thresholds(editor):
    _, window, canvas = editor
    assert select(editor) == "Selection: None"
    assert_controls(window, 0)
    atoms = [
        canvas.services.canvas_atom_mutation_service.add_atom("C", x, 0)
        for x in (0, 20, 40)
    ]
    add_bond_for(canvas, atoms[0], atoms[1])
    add_bond_for(canvas, atoms[1], atoms[2])
    atom = visible_atom_item_for(canvas, atoms[0])
    other_atom = visible_atom_item_for(canvas, atoms[2])
    assert select(editor, atom, other_atom) == "Selection: 1 molecule"
    assert_controls(window, 1)
    arrows = [
        canvas.services.scene_decoration_service.add_arrow(
            QPointF(x, 80), QPointF(x + 30, 80), "arrow"
        )
        for x in (0, 100)
    ]
    assert select(editor, atom, *arrows[:1]) == "Selection: 1 arrow, 1 molecule"
    assert_controls(window, 2)
    assert select(editor, atom, *arrows) == "Selection: 2 arrows, 1 molecule"
    assert_controls(window, 3)
    assert group_selection_for(canvas)
    # Grouping changes the layout count without changing the selected scene items.
    assert_controls(window, 1)
    assert (
        window.services.status_service.status_context_texts()["selection"]
        == "Selection: 1 group"
    )
    canvas.services.history_service.undo()
    assert_controls(window, 3)


def test_mark_owner_and_independent_layout_count(editor):
    _, window, canvas = editor
    owner = canvas.services.canvas_atom_mutation_service.add_atom("N", 0, 0)
    mark = add_mark_for_atom_for(canvas, owner, QPointF(12, -12), kind="plus")
    text = select(editor, mark)
    assert text.startswith("Selection: 1 mark | ")
    assert "owner" in window.services.status_service.selection_label.toolTip()
    assert_controls(window, 1)
    # Selecting the owner carries its mark with it; it is not a second object.
    text = select(editor, visible_atom_item_for(canvas, owner), mark)
    assert text.startswith("Selection: 1 molecule | ")
    assert_controls(window, 1)


def test_note_owned_selection_and_group_remain_one_unit(editor):
    app, window, canvas = editor
    note = canvas.services.note_controller.create_text_note(
        QPointF(0, 50), "conditions"
    )
    arrow = canvas.services.scene_decoration_service.add_arrow(
        QPointF(0, 80), QPointF(40, 80), "arrow"
    )
    select(editor, arrow)
    canvas.services.selection.select_note(note, additive=True)
    app.processEvents()
    assert (
        window.services.status_service.status_context_texts()["selection"]
        == "Selection: 1 arrow, 1 text"
    )
    assert_controls(window, 2)
    assert group_selection_for(canvas)
    app.processEvents()
    assert (
        window.services.status_service.status_context_texts()["selection"]
        == "Selection: 1 group"
    )
    assert_controls(window, 1)
