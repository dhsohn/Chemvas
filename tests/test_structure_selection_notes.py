"""Structure selection selects a note through the note selection it draws."""

from itertools import pairwise
from unittest import mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_group_operations import group_selection_for
from chemvas.ui.selection.selection_queries import selected_ids_for
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


def _note(canvas, text="Keep me", x=0, y=0):
    return canvas.services.scene_item_controller.create_scene_item_from_state(
        {"kind": "note", "text": text, "x": x, "y": y}
    )


def _note_box_visible(note) -> bool:
    box = note.data(21)
    return bool(box is not None and box.isVisible())


def test_perspective_click_on_a_note_selects_what_delete_removes(canvas, app):
    # Perspective selects the structure under a press. For a note that used to
    # be a bare Qt flag: no box or outline showed, yet Delete removed the note.
    note = _note(canvas)
    canvas.centerOn(note)
    canvas.setFocus()
    canvas.services.tool_mode_controller.set_tool("perspective")
    app.processEvents()
    before = canvas.services.canvas_document_session_service.snapshot_state()

    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(note.sceneBoundingRect().center()),
    )
    app.processEvents()

    assert canvas.runtime_state.selection_state.selected_notes == [note]
    assert _note_box_visible(note)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before

    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    app.processEvents()
    assert canvas.runtime_state.note_items() == []
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


def test_structure_selection_of_a_note_publishes_the_note_selection_once(canvas):
    note = _note(canvas)
    other = _note(canvas, "Previous", x=0, y=80)
    canvas.services.selection.select_note(other)
    outline = canvas.services.selection.outline_service

    with mock.patch.object(
        outline, "update_selection_outline", wraps=outline.update_selection_outline
    ) as refresh:
        assert canvas.services.selection.select_structure_for_item(note)

    assert refresh.call_count == 1
    assert canvas.runtime_state.selection_state.selected_notes == [note]
    assert _note_box_visible(note)
    assert not _note_box_visible(other)
    assert not canvas.scene().selectedItems()


def test_structure_selection_of_a_grouped_note_selects_its_group(canvas):
    ids = [
        canvas.services.canvas_atom_mutation_service.add_atom("C", i * 20, i % 2 * 15)
        for i in range(3)
    ]
    for first, second in pairwise(ids):
        add_bond_for(canvas, first, second)
    canvas.services.structure_build_service.render_model()
    note = _note(canvas, "Label", x=0, y=60)
    assert canvas.services.selection.select_all()
    assert group_selection_for(canvas)
    canvas.services.selection.clear()

    assert canvas.services.selection.select_structure_for_item(note)

    assert canvas.runtime_state.selection_state.selected_notes == [note]
    assert _note_box_visible(note)
    assert selected_ids_for(canvas)[0] == set(ids)
